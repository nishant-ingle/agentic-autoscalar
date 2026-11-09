"""
Operational RAG Memory Client for FastAPI Reasoner (Epic 5 - pgvector integration).

Queries pgvector for semantically relevant incident post-mortems and SRE runbooks
to enrich the agentic reasoning prompt before scaling decisions are rendered.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from sentence_transformers import SentenceTransformer
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
    SentenceTransformer = None  # type: ignore[assignment]

from app.config import settings

logger = logging.getLogger(__name__)


class OperationalMemoryRetriever:
    """Retriever for SRE runbooks and past incident memory stored in pgvector."""

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._enabled = settings.rag_enabled

    def _get_embedding_model(self) -> Optional[Any]:
        if not self._enabled:
            return None
        if self._model is None and SentenceTransformer is not None:
            try:
                # Ensure local offline mode is respected
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
                self._model = SentenceTransformer(settings.embedding_model_name)
            except Exception as exc:
                logger.warning("Could not initialize SentenceTransformer for RAG: %s", exc)
                return None
        return self._model

    def _get_db_connection(self) -> Optional[Any]:
        if psycopg2 is None:
            return None
        try:
            return psycopg2.connect(
                host=settings.pg_host,
                port=settings.pg_port,
                dbname=settings.pg_database,
                user=settings.pg_user,
                password=settings.pg_password,
                connect_timeout=3,
            )
        except Exception as exc:
            logger.warning("Could not connect to PostgreSQL pgvector: %s", exc)
            return None

    def retrieve_relevant_runbooks(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Embed the input query and retrieve top_k semantically nearest documents
        using cosine distance (<=>) from rag_documents.
        """
        if not self._enabled:
            return []

        model = self._get_embedding_model()
        if model is None:
            return []

        conn = self._get_db_connection()
        if conn is None:
            return []

        k = top_k or settings.rag_top_k
        try:
            # 1. Generate query vector
            encoded = model.encode([query], convert_to_numpy=True, show_progress_bar=False)[0]
            query_vector = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
            vec_str = "[" + ",".join(str(f) for f in query_vector) + "]"

            # 2. Query pgvector table
            sql = """
                SELECT id, title, content, (embedding <=> %s::vector) AS distance
                FROM rag_documents
                ORDER BY distance ASC
                LIMIT %s;
            """
            with conn.cursor() as cur:
                cur.execute(sql, (vec_str, k))
                rows = cur.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "title": row[1],
                    "content": row[2],
                    "distance": round(float(row[3]), 4),
                })
            return results

        except Exception as exc:
            logger.warning("Failed to retrieve operational memory from pgvector: %s", exc)
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass


# Global singleton retriever
rag_retriever = OperationalMemoryRetriever()
