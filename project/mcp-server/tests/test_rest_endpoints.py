import pytest
from httpx import AsyncClient, ASGITransport
from app.server import asgi_app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    """Verify standard /healthz endpoint returns 200 OK and valid status."""
    transport = ASGITransport(app=asgi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert data["service"] == "k8s-metrics-mcp-server"


@pytest.mark.asyncio
async def test_info_endpoint():
    """Verify /info endpoint returns server metadata and tool catalog."""
    transport = ASGITransport(app=asgi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["server_name"] == "k8s-metrics-mcp-server"
        assert data["tools_count"] >= 4
        tool_names = [t["name"] for t in data["tools"]]
        assert "get_cluster_metrics" in tool_names
        assert "query_prometheus_range" in tool_names
