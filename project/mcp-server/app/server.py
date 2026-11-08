import logging
from typing import Dict, Any, Optional
from starlette.responses import JSONResponse
from starlette.routing import Route
from mcp.server.mcpserver import MCPServer

from app.config import settings
from app.k8s_client import k8s_client
from app.prom_client import prom_client
from app.security import enforce_read_only, SecurityViolationError

logger = logging.getLogger(__name__)

# Initialize official MCP Server instance
mcp_server = MCPServer(
    name=settings.mcp_server_name,
    version=settings.mcp_server_version,
    instructions="Standard Model Context Protocol Server providing read-only Kubernetes cluster telemetry and Prometheus metrics."
)


# ==============================================================================
# MCP Protocol Tools Registration
# ==============================================================================

@mcp_server.tool(
    name="get_cluster_metrics",
    description="Retrieves live Kubernetes workload metrics including desired/ready replicas, pod lifecycle status, and restart counts."
)
def get_cluster_metrics(
    namespace: str = "workload-system",
    workload_name: str = "target-workload"
) -> Dict[str, Any]:
    """Inspects target deployment and active pods within authorized namespace."""
    enforce_read_only("get_cluster_metrics")
    return k8s_client.get_workload_metrics(namespace=namespace, workload_name=workload_name)


@mcp_server.tool(
    name="query_prometheus_range",
    description="Queries Prometheus timeseries telemetry over a historical time window with statistical aggregation."
)
async def query_prometheus_range(
    query: str,
    time_window_seconds: int = 300,
    step: str = "15s"
) -> Dict[str, Any]:
    """Executes a PromQL range query to fetch timeseries metrics and summary statistics."""
    enforce_read_only(query)
    return await prom_client.query_range(
        query=query,
        start_seconds_ago=time_window_seconds,
        step=step
    )


@mcp_server.tool(
    name="fetch_recent_logs",
    description="Fetches recent stdout/stderr log entries from workload pods to diagnose latency spikes or container crashes."
)
def fetch_recent_logs(
    namespace: str = "workload-system",
    workload_name: str = "target-workload",
    tail_lines: int = 50,
    container: Optional[str] = None
) -> Dict[str, Any]:
    """Safely retrieves sanitized pod log lines from target deployment."""
    enforce_read_only("fetch_recent_logs")
    return k8s_client.fetch_recent_logs(
        namespace=namespace,
        workload_name=workload_name,
        tail_lines=tail_lines,
        container=container
    )


@mcp_server.tool(
    name="execute_cluster_action",
    description="Security guard tool: any mutating or write cluster command requested is strictly intercepted and blocked."
)
def execute_cluster_action(
    action: str,
    target: str = "default"
) -> Dict[str, Any]:
    """Security boundary test tool: blocks all write/mutating cluster modifications."""
    try:
        enforce_read_only(action)
        return {
            "status": "denied",
            "message": "Only read-only operations are supported by design."
        }
    except SecurityViolationError as err:
        return {
            "status": "blocked",
            "security_error": str(err),
            "is_forbidden": True
        }


# ==============================================================================
# Starlette ASGI Application Supporting Modern Streamable HTTP & Legacy SSE
# ==============================================================================

async def health_endpoint(request) -> JSONResponse:
    """Readiness/Liveness probe endpoint."""
    return JSONResponse({
        "status": "UP",
        "service": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "transports": {
            "primary": "StreamableHTTP (/mcp)",
            "legacy": "SSE (/sse)"
        },
        "endpoints": {
            "streamable_http": "/mcp",
            "sse": "/sse",
            "messages": "/messages",
            "info": "/info",
            "healthz": "/healthz"
        }
    })


async def info_endpoint(request) -> JSONResponse:
    """Metadata inspection endpoint listing registered MCP tools."""
    tools = await mcp_server.list_tools()
    tool_list = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema
        }
        for t in tools
    ]
    return JSONResponse({
        "server_name": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "primary_transport": "StreamableHTTP",
        "primary_endpoint": "/mcp",
        "legacy_transport": "SSE",
        "legacy_endpoint": "/sse",
        "read_only_mode": settings.read_only_mode,
        "tools_count": len(tool_list),
        "tools": tool_list
    })


def create_app():
    """Builds the Starlette ASGI application with both modern Streamable HTTP and legacy SSE.

    DNS rebinding protection is disabled on the MCP transports and TrustedHostMiddleware
    allows all hosts so that in-cluster Kubernetes DNS FQDNs
    (e.g. mcp-server.workload-system.svc.cluster.local) are accepted and do not return 421.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from mcp.server.transport_security import TransportSecuritySettings

    # Disable DNS rebinding protection in MCP transport so internal Kubernetes
    # service names (e.g., mcp-server.workload-system.svc.cluster.local) are accepted.
    transport_sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    streamable_app = mcp_server.streamable_http_app(transport_security=transport_sec)
    sse_app = mcp_server.sse_app(transport_security=transport_sec)

    app = Starlette(
        routes=[
            *streamable_app.routes,  # Modern Streamable HTTP endpoint: /mcp
            *sse_app.routes,         # Legacy SSE endpoints: /sse, /messages
            Route("/healthz", health_endpoint, methods=["GET"]),
            Route("/info", info_endpoint, methods=["GET"])
        ],
        middleware=[
            # Accept any Host header - required for Kubernetes in-cluster DNS FQDNs
            # (e.g. mcp-server.workload-system.svc.cluster.local) which uvicorn
            # would otherwise reject with HTTP 421 Misdirected Request.
            Middleware(TrustedHostMiddleware, allowed_hosts=["*"])
        ],
        lifespan=streamable_app.router.lifespan_context
    )
    return app


asgi_app = create_app()
