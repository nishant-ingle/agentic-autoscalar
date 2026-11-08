import pytest
from app.server import mcp_server


@pytest.mark.asyncio
async def test_tools_list_registration():
    """Verify all required tools are registered following standard MCP initialization."""
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]

    assert "get_cluster_metrics" in tool_names
    assert "query_prometheus_range" in tool_names
    assert "fetch_recent_logs" in tool_names
    assert "execute_cluster_action" in tool_names


@pytest.mark.asyncio
async def test_tools_schema_definitions():
    """Verify MCP tools adhere to strict JSON Schema definitions."""
    tools = await mcp_server.list_tools()
    tools_by_name = {t.name: t for t in tools}

    # Verify get_cluster_metrics schema
    metrics_tool = tools_by_name["get_cluster_metrics"]
    assert metrics_tool.description is not None
    assert "namespace" in metrics_tool.input_schema.get("properties", {})
    assert "workload_name" in metrics_tool.input_schema.get("properties", {})

    # Verify query_prometheus_range schema
    prom_tool = tools_by_name["query_prometheus_range"]
    assert "query" in prom_tool.input_schema.get("properties", {})
    assert "time_window_seconds" in prom_tool.input_schema.get("properties", {})
    assert "query" in prom_tool.input_schema.get("required", [])

    # Verify fetch_recent_logs schema
    log_tool = tools_by_name["fetch_recent_logs"]
    assert "tail_lines" in log_tool.input_schema.get("properties", {})
