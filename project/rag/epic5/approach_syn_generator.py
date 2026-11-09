"""
Epic 5: Synthetic SRE Runbook & Incident Generator (Approach 1 - approach_syn).

Generates vector embeddings for synthetic SRE incident runbooks and populates
the PostgreSQL pgvector database for real-time operational retrieval by the LLM reasoner.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Prefer local Hugging Face cache and suppress remote checks if already downloaded
if os.environ.get("HF_HUB_OFFLINE") is None:
    # If the user has cached the model locally, default to offline mode to avoid remote warnings
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
    if cache_dir.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import psycopg2
from psycopg2.extras import execute_values
import yaml

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]

# Fallback embedding dimension for default model (all-MiniLM-L6-v2)
DEFAULT_EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


def _expand_env_vars(raw: str) -> str:
    """Expand ${VAR:-default} and ${VAR} patterns in YAML strings."""
    pattern = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return pattern.sub(_replace, raw)


def load_config(config_path: Path | str) -> Dict[str, Any]:
    """Load configuration YAML with environment variable substitution."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    expanded = _expand_env_vars(raw_text)
    data = yaml.safe_load(expanded) or {}

    mode = data.get("mode")
    if mode != "synthetic":
        raise ValueError(
            f"Invalid mode '{mode}' in config {path}. "
            "approach_syn_generator requires 'mode: synthetic'."
        )
    return data


def get_db_connection(config: Dict[str, Any]) -> psycopg2.extensions.connection:
    """Establish and return a connection to the PostgreSQL database."""
    db_cfg = config.get("database", {})
    host = os.environ.get("PGHOST", db_cfg.get("host", "localhost"))
    port = int(os.environ.get("PGPORT", db_cfg.get("port", 5432)))
    dbname = os.environ.get("PGDATABASE", db_cfg.get("dbname", "agentic_autoscalar_db"))
    user = os.environ.get("PGUSER", db_cfg.get("user", "agentic_autoscalar"))
    password = os.environ.get("PGPASSWORD", db_cfg.get("password", "agentic_autoscalar"))

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )
    conn.autocommit = False
    return conn


def init_database(conn: psycopg2.extensions.connection, embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> None:
    """
    Ensure the pgvector extension and rag_documents table exist.
    Creates an HNSW index on the embedding vector for fast cosine similarity search.
    """
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS rag_documents (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding VECTOR({embedding_dim}) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        # Create HNSW index for cosine distance if not already present
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rag_documents_embedding_hnsw
            ON rag_documents USING hnsw (embedding vector_cosine_ops);
            """
        )
    conn.commit()


def load_incidents_from_yaml(yaml_path: Path | str) -> List[Dict[str, str]]:
    """Load synthetic incident records from YAML schema."""
    path = Path(yaml_path)
    if not path.is_file():
        raise FileNotFoundError(f"Synthetic schema file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    incidents = data.get("incidents", [])
    if not incidents:
        raise ValueError(f"No incident records found in {path}")
    return incidents


def generate_embeddings(
    texts: List[str],
    model_name: str = DEFAULT_MODEL_NAME,
    model_instance: Optional[Any] = None,
) -> List[List[float]]:
    """Generate dense embedding vectors using SentenceTransformer."""
    if model_instance is None:
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers is not installed.")
        model = SentenceTransformer(model_name)
    else:
        model = model_instance

    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return [vec.tolist() for vec in vectors]


def bulk_insert_documents(
    conn: psycopg2.extensions.connection,
    documents: List[Dict[str, Any]],
) -> int:
    """Bulk-insert embedded documents into rag_documents."""
    if not documents:
        return 0

    rows = []
    for doc in documents:
        # Format list of floats as pgvector string representation "[0.12, 0.45, ...]"
        vec_str = "[" + ",".join(str(f) for f in doc["embedding"]) + "]"
        rows.append((doc["title"], doc["content"], vec_str))

    sql = """
        INSERT INTO rag_documents (title, content, embedding)
        VALUES %s
        RETURNING id;
    """
    with conn.cursor() as cur:
        result = execute_values(cur, sql, rows, fetch=True)
        inserted_count = len(result)
    conn.commit()
    return inserted_count


def search_similar_documents(
    conn: psycopg2.extensions.connection,
    query_vector: List[float],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Query rag_documents using cosine distance (<=>)."""
    vec_str = "[" + ",".join(str(f) for f in query_vector) + "]"
    sql = """
        SELECT id, title, content, (embedding <=> %s::vector) AS distance
        FROM rag_documents
        ORDER BY distance ASC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (vec_str, limit))
        rows = cur.fetchall()

    return [
        {"id": row[0], "title": row[1], "content": row[2], "distance": float(row[3])}
        for row in rows
    ]


def run_pipeline(
    config_path: Optional[Path | str] = None,
    conn: Optional[psycopg2.extensions.connection] = None,
    clean_existing: bool = False,
) -> int:
    """Execute the end-to-end synthetic RAG ingestion pipeline."""
    base_dir = Path(__file__).resolve().parent
    cfg_file = Path(config_path) if config_path else (base_dir / "config.yaml")

    config = load_config(cfg_file)
    schema_filename = config.get("synthetic", {}).get("schema_path", "synthetic_epic5.yaml")
    schema_path = base_dir / schema_filename if not Path(schema_filename).is_absolute() else Path(schema_filename)

    model_name = config.get("embedding", {}).get("model_name", DEFAULT_MODEL_NAME)
    dimension = int(config.get("embedding", {}).get("dimension", DEFAULT_EMBEDDING_DIM))

    should_close_conn = False
    if conn is None:
        conn = get_db_connection(config)
        should_close_conn = True

    try:
        init_database(conn, embedding_dim=dimension)

        if clean_existing:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE rag_documents RESTART IDENTITY;")
            conn.commit()

        incidents = load_incidents_from_yaml(schema_path)
        texts_to_embed = [
            f"Title: {inc['title']}. Content: {inc['content']}"
            for inc in incidents
        ]

        print(f"[*] Embedding {len(texts_to_embed)} incidents using {model_name}...")
        embeddings = generate_embeddings(texts_to_embed, model_name=model_name)

        docs = []
        for inc, emb in zip(incidents, embeddings):
            docs.append({
                "title": inc["title"],
                "content": inc["content"],
                "embedding": emb,
            })

        count = bulk_insert_documents(conn, docs)
        print(f"[✓] Successfully inserted {count} documents into rag_documents table.")
        return count
    finally:
        if should_close_conn and conn is not None:
            conn.close()


def main() -> None:
    """CLI entrypoint."""
    cfg_arg = sys.argv[1] if len(sys.argv) > 1 else None
    inserted = run_pipeline(config_path=cfg_arg)
    print(f"[✓] Pipeline complete. {inserted} records loaded.")


if __name__ == "__main__":
    main()
