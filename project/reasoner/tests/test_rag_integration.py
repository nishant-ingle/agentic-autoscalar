"""
Unit and integration tests for Epic 5 pgvector Operational Memory integration in Reasoner.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.rag_retriever import OperationalMemoryRetriever, rag_retriever
from app.schemas.telemetry import ClusterMetricsPayload
from app.services.graph import analyze_telemetry_node


def test_rag_retriever_query_parsing():
    """Verify retriever query execution with mocked db and model."""
    retriever = OperationalMemoryRetriever()
    
    mock_model = MagicMock()
    # Mock return 384 dimensional list
    mock_model.encode.return_value = [[0.1] * 384]

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (1, "INC-CPU-SPIKE-001", "CPU surge incident runbook", 0.3541)
    ]
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=None)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch.object(retriever, "_get_embedding_model", return_value=mock_model), \
         patch.object(retriever, "_get_db_connection", return_value=mock_conn):
        results = retriever.retrieve_relevant_runbooks("High CPU utilization", top_k=1)
        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["title"] == "INC-CPU-SPIKE-001"
        assert results[0]["distance"] == 0.3541


def test_analyze_telemetry_node_populates_rag_context():
    """Verify that analyze_telemetry_node invokes rag_retriever and populates state."""
    payload = ClusterMetricsPayload(
        workload_name="test-target",
        namespace="workload-system",
        current_replicas=2,
        min_replicas=1,
        max_replicas=10,
        cpu_utilization_percent=92.5,
        memory_utilization_percent=60.0,
        http_requests_per_second=250.0,
        http_p99_latency_ms=850.0,
        error_rate_percent=0.5
    )

    state = {
        "payload": payload,
        "target_cpu": 65.0,
        "latency_threshold_ms": 250.0,
        "analysis": {},
        "rag_context": [],
        "recommendation": None,
        "errors": []
    }

    mock_results = [
        {"id": 1, "title": "Flash Traffic Surge", "content": "Scale 2.5x", "distance": 0.42}
    ]

    with patch.object(rag_retriever, "retrieve_relevant_runbooks", return_value=mock_results):
        res = analyze_telemetry_node(state)
        assert "rag_context" in res
        assert len(res["rag_context"]) == 1
        assert res["rag_context"][0]["title"] == "Flash Traffic Surge"
