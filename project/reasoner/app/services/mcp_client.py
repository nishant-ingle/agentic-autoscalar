import logging
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from mcp.client.streamable_http import streamable_http_client
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from app.config import settings

logger = logging.getLogger(__name__)


class MCPReasonerClient:
    """Client for discovering and executing tools on the Kubernetes MCP Server.
    
    Defaults to modern Streamable HTTP transport (/mcp), with automatic backward
    compatibility for legacy SSE transport (/sse).
    """

    def __init__(self, mcp_url: Optional[str] = None):
        self.mcp_url = mcp_url or getattr(settings, "mcp_server_url", "http://localhost:8001/mcp")

    @asynccontextmanager
    async def _get_transport(self, url: str):
        """Selects Streamable HTTP or legacy SSE transport based on endpoint URL."""
        if url.rstrip("/").endswith("/sse"):
            logger.debug("Connecting via legacy MCP SSE transport: %s", url)
            async with sse_client(url) as streams:
                yield streams
        else:
            logger.debug("Connecting via modern Streamable HTTP transport: %s", url)
            async with streamable_http_client(url) as streams:
                yield streams

    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """Connects to MCP server, handshakes, and returns registered tools."""
        try:
            async with self._get_transport(self.mcp_url) as (read, write):
                async with ClientSession(read, write) as session:
                    init_res = await session.initialize()
                    logger.info(
                        "Connected to MCP Server: %s (v%s) via %s",
                        init_res.server_info.name,
                        init_res.server_info.version,
                        "SSE" if "/sse" in self.mcp_url else "Streamable HTTP"
                    )
                    tools_resp = await session.list_tools()
                    return [
                        {
                            "name": t.name,
                            "description": t.description,
                            "input_schema": t.input_schema
                        }
                        for t in tools_resp.tools
                    ]
        except Exception as exc:
            logger.warning("Could not discover tools from MCP server at %s: %s", self.mcp_url, exc)
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a specific tool on the MCP server via the protocol client layer."""
        try:
            async with self._get_transport(self.mcp_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(tool_name, arguments)
                    if res.is_error:
                        return {"status": "error", "tool": tool_name, "error": "Tool returned error state"}
                    structured = res.structured_content or {}
                    # MCP wraps tool return under 'result'
                    return structured.get("result", structured)
        except Exception as exc:
            logger.error("Failed to execute tool '%s' on MCP server (%s): %s", tool_name, self.mcp_url, exc)
            return {"status": "error", "tool": tool_name, "error": str(exc)}

    async def get_cluster_telemetry(
        self,
        namespace: str = "workload-system",
        workload_name: str = "target-workload"
    ) -> Dict[str, Any]:
        """Convenience method querying get_cluster_metrics over MCP protocol."""
        return await self.call_tool(
            "get_cluster_metrics",
            {"namespace": namespace, "workload_name": workload_name}
        )

    async def fetch_pod_logs(
        self,
        namespace: str = "workload-system",
        workload_name: str = "target-workload",
        tail_lines: int = 20
    ) -> Dict[str, Any]:
        """Convenience method querying fetch_recent_logs over MCP protocol."""
        return await self.call_tool(
            "fetch_recent_logs",
            {"namespace": namespace, "workload_name": workload_name, "tail_lines": tail_lines}
        )


mcp_client = MCPReasonerClient()
