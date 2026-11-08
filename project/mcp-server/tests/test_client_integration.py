import asyncio
import pytest
import uvicorn
from mcp.client.streamable_http import streamable_http_client
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from app.server import create_app


@pytest.mark.asyncio
async def test_end_to_end_mcp_client_streamable_http():
    """Verify modern Streamable HTTP transport (/mcp) completes handshake and calls tools."""
    test_port = 8994
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=test_port, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    for _ in range(25):
        if server.started:
            break
        await asyncio.sleep(0.04)

    try:
        mcp_endpoint = f"http://127.0.0.1:{test_port}/mcp"
        async with streamable_http_client(mcp_endpoint) as (read, write):
            async with ClientSession(read, write) as session:
                # 1. Standard MCP Protocol Handshake
                init_result = await session.initialize()
                assert init_result is not None
                assert init_result.server_info.name == "k8s-metrics-mcp-server"

                # 2. Dynamic Tool Discovery (tools/list)
                tools_response = await session.list_tools()
                tool_names = [t.name for t in tools_response.tools]
                assert "get_cluster_metrics" in tool_names
                assert "query_prometheus_range" in tool_names

                # 3. Protocol Tool Invocation (tools/call)
                call_result = await session.call_tool(
                    "get_cluster_metrics",
                    {"namespace": "workload-system", "workload_name": "target-workload"}
                )
                assert not call_result.is_error
                assert call_result.structured_content is not None
                data = call_result.structured_content.get("result", call_result.structured_content)
                assert data.get("namespace") == "workload-system"
    finally:
        server.should_exit = True
        await server_task


@pytest.mark.asyncio
async def test_end_to_end_mcp_client_legacy_sse():
    """Verify legacy SSE transport (/sse) remains fully supported for backward compatibility."""
    test_port = 8995
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=test_port, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    for _ in range(25):
        if server.started:
            break
        await asyncio.sleep(0.04)

    try:
        sse_endpoint = f"http://127.0.0.1:{test_port}/sse"
        async with sse_client(sse_endpoint) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                assert init_result is not None
                assert init_result.server_info.name == "k8s-metrics-mcp-server"

                tools_response = await session.list_tools()
                tool_names = [t.name for t in tools_response.tools]
                assert "get_cluster_metrics" in tool_names

                call_result = await session.call_tool(
                    "get_cluster_metrics",
                    {"namespace": "workload-system", "workload_name": "target-workload"}
                )
                assert not call_result.is_error
                data = call_result.structured_content.get("result", call_result.structured_content)
                assert data.get("namespace") == "workload-system"
    finally:
        server.should_exit = True
        await server_task
