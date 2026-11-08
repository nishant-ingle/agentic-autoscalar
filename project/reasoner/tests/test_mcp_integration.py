import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_mcp_tools_discovery_endpoint():
    """Verify Reasoner exposes /mcp/tools endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/mcp/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools_discovered_count" in data
        assert "tools" in data


@pytest.mark.asyncio
async def test_evaluate_scaling_mcp_endpoint():
    """Verify Reasoner successfully runs /evaluate-scaling-mcp."""
    payload = {
        "timestamp": "2026-11-07T20:00:00Z",
        "workload_name": "target-workload",
        "namespace": "workload-system",
        "current_replicas": 2,
        "min_replicas": 1,
        "max_replicas": 10,
        "cpu_utilization_percent": 88.5,
        "memory_utilization_percent": 55.0,
        "http_requests_per_second": 320.0,
        "http_p99_latency_ms": 110.0,
        "error_rate_percent": 0.05
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/evaluate-scaling-mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "SCALE_UP"
        assert data["target_replicas"] > 2
        assert "target_replicas" in data
