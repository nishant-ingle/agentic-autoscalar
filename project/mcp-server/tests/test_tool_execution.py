import pytest
from app.server import mcp_server


@pytest.mark.asyncio
async def test_call_get_cluster_metrics():
    """Verify tool call for get_cluster_metrics executes cleanly."""
    res = await mcp_server.call_tool(
        name="get_cluster_metrics",
        arguments={"namespace": "workload-system", "workload_name": "target-workload"}
    )
    assert not res.is_error
    data = res.structured_content.get("result", res.structured_content)
    assert data is not None
    assert data.get("status") in ("success", "mock_success", "warning")
    assert data.get("namespace") == "workload-system"
    assert data.get("workload_name") == "target-workload"


@pytest.mark.asyncio
async def test_call_query_prometheus_range():
    """Verify tool call for query_prometheus_range executes cleanly."""
    res = await mcp_server.call_tool(
        name="query_prometheus_range",
        arguments={
            "query": "workload_http_requests_total",
            "time_window_seconds": 60,
            "step": "15s"
        }
    )
    assert not res.is_error
    data = res.structured_content.get("result", res.structured_content)
    assert data is not None
    assert data.get("status") in ("success", "mock_success", "warning")


@pytest.mark.asyncio
async def test_call_fetch_recent_logs():
    """Verify tool call for fetch_recent_logs executes cleanly."""
    res = await mcp_server.call_tool(
        name="fetch_recent_logs",
        arguments={
            "namespace": "workload-system",
            "workload_name": "target-workload",
            "tail_lines": 10
        }
    )
    assert not res.is_error
    data = res.structured_content.get("result", res.structured_content)
    assert data is not None
    assert data.get("status") in ("success", "mock_success", "warning")
