import pytest
from pydantic import ValidationError
from app.schemas.telemetry import ClusterMetricsPayload, PodMetricItem
from app.schemas.recommendation import ScalingRecommendationResponse, ScalingAction


def test_valid_cluster_metrics_payload():
    payload = ClusterMetricsPayload(
        namespace="workload-system",
        workload_name="target-workload",
        current_replicas=2,
        min_replicas=1,
        max_replicas=5,
        cpu_utilization_percent=78.5,
        memory_utilization_percent=55.0,
        http_requests_per_second=240.0,
        http_p99_latency_ms=180.0,
        error_rate_percent=0.5
    )
    assert payload.workload_name == "target-workload"
    assert payload.current_replicas == 2
    assert payload.cpu_utilization_percent == 78.5


def test_invalid_replica_bounds_rejected():
    with pytest.raises(ValidationError) as exc_info:
        ClusterMetricsPayload(
            namespace="workload-system",
            workload_name="target-workload",
            current_replicas=2,
            min_replicas=5,
            max_replicas=2,  # max < min
            cpu_utilization_percent=50.0,
            memory_utilization_percent=50.0,
            http_requests_per_second=100.0,
            http_p99_latency_ms=50.0
        )
    assert "max_replicas" in str(exc_info.value)


def test_negative_metrics_rejected():
    with pytest.raises(ValidationError):
        ClusterMetricsPayload(
            namespace="workload-system",
            workload_name="target-workload",
            current_replicas=-1,  # negative current replicas
            min_replicas=1,
            max_replicas=5,
            cpu_utilization_percent=50.0,
            memory_utilization_percent=50.0,
            http_requests_per_second=10.0,
            http_p99_latency_ms=20.0
        )


def test_scaling_recommendation_schema():
    rec = ScalingRecommendationResponse(
        workload_name="target-workload",
        namespace="workload-system",
        current_replicas=2,
        target_replicas=4,
        action=ScalingAction.SCALE_UP,
        reasoning="CPU utilization reached 85%, scaling up to meet demand.",
        confidence_score=0.92,
        primary_metric_driver="CPU_UTILIZATION"
    )
    assert rec.action == ScalingAction.SCALE_UP
    assert rec.target_replicas == 4
    assert rec.confidence_score == 0.92
