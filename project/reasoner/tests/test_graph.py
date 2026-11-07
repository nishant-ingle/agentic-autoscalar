import pytest
from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingAction
from app.services.graph import reasoning_graph


@pytest.mark.asyncio
async def test_reasoning_graph_scale_up():
    payload = ClusterMetricsPayload(
        namespace="workload-system",
        workload_name="target-workload",
        current_replicas=2,
        min_replicas=1,
        max_replicas=5,
        cpu_utilization_percent=92.0,  # Far exceeds 65% target
        memory_utilization_percent=60.0,
        http_requests_per_second=350.0,
        http_p99_latency_ms=280.0,  # Exceeds 250ms threshold
        error_rate_percent=0.0
    )

    state = {
        "payload": payload,
        "target_cpu": 65.0,
        "latency_threshold_ms": 250.0,
        "analysis": {},
        "recommendation": None,
        "errors": []
    }

    result = await reasoning_graph.ainvoke(state)
    rec = result.get("recommendation")

    assert rec is not None
    assert rec.target_replicas > 2
    assert rec.target_replicas <= 5
    assert rec.action == ScalingAction.SCALE_UP
    assert len(rec.reasoning) > 10


@pytest.mark.asyncio
async def test_reasoning_graph_scale_down():
    payload = ClusterMetricsPayload(
        namespace="workload-system",
        workload_name="target-workload",
        current_replicas=4,
        min_replicas=1,
        max_replicas=5,
        cpu_utilization_percent=15.0,  # Very low CPU
        memory_utilization_percent=20.0,
        http_requests_per_second=10.0,
        http_p99_latency_ms=12.0,
        error_rate_percent=0.0
    )

    state = {
        "payload": payload,
        "target_cpu": 65.0,
        "latency_threshold_ms": 250.0,
        "analysis": {},
        "recommendation": None,
        "errors": []
    }

    result = await reasoning_graph.ainvoke(state)
    rec = result.get("recommendation")

    assert rec is not None
    assert rec.target_replicas < 4
    assert rec.target_replicas >= 1
    assert rec.action == ScalingAction.SCALE_DOWN


@pytest.mark.asyncio
async def test_reasoning_graph_maintain():
    payload = ClusterMetricsPayload(
        namespace="workload-system",
        workload_name="target-workload",
        current_replicas=2,
        min_replicas=1,
        max_replicas=5,
        cpu_utilization_percent=64.0,  # Right at the 65% target
        memory_utilization_percent=45.0,
        http_requests_per_second=120.0,
        http_p99_latency_ms=45.0,
        error_rate_percent=0.0
    )

    state = {
        "payload": payload,
        "target_cpu": 65.0,
        "latency_threshold_ms": 250.0,
        "analysis": {},
        "recommendation": None,
        "errors": []
    }

    result = await reasoning_graph.ainvoke(state)
    rec = result.get("recommendation")

    assert rec is not None
    assert rec.target_replicas == 2
    assert rec.action == ScalingAction.MAINTAIN
