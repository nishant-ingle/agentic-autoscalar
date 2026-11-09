"""
Integration and Unit Tests for Epic 5 Synthetic Generator (approach_syn_generator).

Tests:
1. Config validation (validates mode: synthetic enforcement).
2. Database initialization and table creation.
3. YAML schema parsing and structure validation.
4. Embedding generation and vector dimension verification.
5. Bulk insertion and pgvector cosine similarity retrieval (<=> operator).
6. End-to-end pipeline execution with environment overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator
import pytest
import psycopg2

from epic5.approach_syn_generator import (
    bulk_insert_documents,
    generate_embeddings,
    get_db_connection,
    init_database,
    load_config,
    load_incidents_from_yaml,
    run_pipeline,
    search_similar_documents,
    DEFAULT_EMBEDDING_DIM,
)


@pytest.fixture(scope="session")
def db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Connect to PostgreSQL for integration testing.
    Uses environment variables (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
    or falls back to local dev credentials.
    """
    config = {
        "database": {
            "host": os.environ.get("PGHOST", "localhost"),
            "port": int(os.environ.get("PGPORT", "5432")),
            "dbname": os.environ.get("PGDATABASE", "agentic_autoscalar_db"),
            "user": os.environ.get("PGUSER", "agentic_autoscalar"),
            "password": os.environ.get("PGPASSWORD", "agentic_autoscalar"),
        }
    }
    conn = get_db_connection(config)
    yield conn
    conn.close()


@pytest.fixture
def clean_rag_table(db_connection: psycopg2.extensions.connection) -> None:
    """Ensure the rag_documents table is initialized and empty before each test."""
    init_database(db_connection, embedding_dim=DEFAULT_EMBEDDING_DIM)
    with db_connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE rag_documents RESTART IDENTITY;")
    db_connection.commit()


def test_load_config_valid() -> None:
    """Verify that a valid configuration file with 'mode: synthetic' loads cleanly."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "epic5"
    config_file = base_dir / "config.yaml"
    config = load_config(config_file)
    assert config.get("mode") == "synthetic"
    assert "database" in config
    assert "embedding" in config


def test_load_config_invalid_mode(tmp_path: Path) -> None:
    """Verify that load_config rejects any mode other than 'synthetic'."""
    invalid_cfg = tmp_path / "invalid_config.yaml"
    invalid_cfg.write_text("mode: unsupported_mode\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid mode 'unsupported_mode'"):
        load_config(invalid_cfg)


def test_load_incidents_from_yaml() -> None:
    """Verify that the synthetic incident schema loads expected incident items."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "epic5"
    schema_file = base_dir / "synthetic_epic5.yaml"
    incidents = load_incidents_from_yaml(schema_file)

    assert isinstance(incidents, list)
    assert len(incidents) >= 5
    for item in incidents:
        assert "id" in item
        assert "title" in item
        assert "content" in item
        assert len(item["content"].strip()) > 0


def test_init_database_and_vector_table(db_connection: psycopg2.extensions.connection) -> None:
    """Verify that init_database creates pgvector extension and rag_documents table."""
    init_database(db_connection, embedding_dim=DEFAULT_EMBEDDING_DIM)
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'rag_documents'
            );
            """
        )
        exists = cur.fetchone()[0]
        assert exists is True


def test_generate_embeddings_dimension() -> None:
    """Verify that embedding generation produces correct 384-dim vectors."""
    sample_texts = ["High CPU spike detected on target microservice."]
    embeddings = generate_embeddings(sample_texts, model_name="all-MiniLM-L6-v2")
    assert len(embeddings) == 1
    assert len(embeddings[0]) == DEFAULT_EMBEDDING_DIM
    assert all(isinstance(v, float) for v in embeddings[0])


def test_bulk_insert_and_similarity_retrieval(
    db_connection: psycopg2.extensions.connection,
    clean_rag_table: None,
) -> None:
    """
    Test bulk insertion and verify that a cosine distance (<=>) query returns
    the semantically closest incident.
    """
    # 1. Prepare two distinct test documents
    docs_to_insert = [
        {
            "title": "CPU Overload Crisis",
            "content": "Heavy compute workload caused 100% CPU thread saturation and latency spikes.",
            "embedding": generate_embeddings(["Heavy compute workload caused 100% CPU thread saturation."])[0],
        },
        {
            "title": "Memory Leak Anomaly",
            "content": "Out of memory crash due to memory accumulation in cache without eviction.",
            "embedding": generate_embeddings(["Out of memory crash due to memory accumulation in cache."])[0],
        },
    ]

    count = bulk_insert_documents(db_connection, docs_to_insert)
    assert count == 2

    # 2. Query for CPU incident
    cpu_query = "Excessive CPU consumption thread pool starvation"
    cpu_query_vec = generate_embeddings([cpu_query])[0]
    results = search_similar_documents(db_connection, cpu_query_vec, limit=1)

    assert len(results) == 1
    assert results[0]["title"] == "CPU Overload Crisis"
    assert results[0]["distance"] < 0.60


def test_run_pipeline_end_to_end(
    db_connection: psycopg2.extensions.connection,
    clean_rag_table: None,
) -> None:
    """Verify end-to-end execution of the run_pipeline function."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "epic5"
    config_file = base_dir / "config.yaml"

    inserted_count = run_pipeline(config_path=config_file, conn=db_connection, clean_existing=True)
    assert inserted_count >= 5

    # Verify rows in database
    with db_connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM rag_documents;")
        total_rows = cur.fetchone()[0]
        assert total_rows == inserted_count
