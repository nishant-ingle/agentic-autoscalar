import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_evaluate_scaling_success_scale_up():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "namespace": "workload-system",
            "workload_name": "target-workload",
            "current_replicas": 2,
            "min_replicas": 1,
            "max_replicas": 5,
            "cpu_utilization_percent": 90.0,
            "memory_utilization_percent": 60.0,
            "http_requests_per_second": 300.0,
            "http_p99_latency_ms": 320.0,
            "error_rate_percent": 0.0
        }

        res = await client.post("/evaluate-scaling", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["workload_name"] == "target-workload"
        assert data["namespace"] == "workload-system"
        assert data["current_replicas"] == 2
        assert data["target_replicas"] > 2
        assert data["target_replicas"] <= 5
        assert data["action"] == "SCALE_UP"
        assert len(data["reasoning"]) > 0
        assert "confidence_score" in data
        assert "primary_metric_driver" in data


@pytest.mark.asyncio
async def test_evaluate_scaling_rejects_malformed_payload_http_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing required fields
        res1 = await client.post("/evaluate-scaling", json={"namespace": "workload-system"})
        assert res1.status_code == 422
        body1 = res1.json()
        assert body1["error"] == "Unprocessable Entity"
        assert len(body1["details"]) > 0

        # 2. Invalid replica bounds (max < min)
        malformed_bounds = {
            "namespace": "workload-system",
            "workload_name": "target-workload",
            "current_replicas": 2,
            "min_replicas": 5,
            "max_replicas": 2,
            "cpu_utilization_percent": 50.0,
            "memory_utilization_percent": 50.0,
            "http_requests_per_second": 50.0,
            "http_p99_latency_ms": 50.0
        }
        res2 = await client.post("/evaluate-scaling", json=malformed_bounds)
        assert res2.status_code == 422

        # 3. Negative metrics
        negative_metrics = {
            "namespace": "workload-system",
            "workload_name": "target-workload",
            "current_replicas": 2,
            "min_replicas": 1,
            "max_replicas": 5,
            "cpu_utilization_percent": -10.0,
            "memory_utilization_percent": 50.0,
            "http_requests_per_second": 50.0,
            "http_p99_latency_ms": 50.0
        }
        res3 = await client.post("/evaluate-scaling", json=negative_metrics)
        assert res3.status_code == 422
