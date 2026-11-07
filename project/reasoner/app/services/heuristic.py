import math
from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingRecommendationResponse, ScalingAction


def calculate_heuristic_scaling(
    payload: ClusterMetricsPayload,
    target_cpu: float = 65.0,
    latency_threshold_ms: float = 250.0,
    fallback_reason: str = "Deterministic SRE heuristic applied"
) -> ScalingRecommendationResponse:
    """
    Computes a deterministic rule-based scaling recommendation following
    standard Kubernetes HPA proportional math and latency safeguard thresholds.
    """
    current = max(1, payload.current_replicas)
    min_reps = payload.min_replicas
    max_reps = payload.max_replicas

    # 1. Base CPU proportional scaling: desired = ceil(current * (observed / target))
    if payload.cpu_utilization_percent > 0:
        ratio = payload.cpu_utilization_percent / target_cpu
        desired_by_cpu = math.ceil(current * ratio)
    else:
        desired_by_cpu = current

    # 2. Latency / traffic surge check
    latency_driver = False
    if payload.http_p99_latency_ms > latency_threshold_ms:
        latency_driver = True
        # Under latency pressure, ensure at least one additional replica if not capped
        desired_by_cpu = max(desired_by_cpu, current + 1)

    # 3. Guard against aggressive downscaling if error rate is non-zero
    if payload.error_rate_percent > 2.0 and desired_by_cpu < current:
        desired_by_cpu = current

    # 4. Clamp within configured boundaries [min_replicas, max_replicas]
    clamped_target = max(min_reps, min(max_reps, desired_by_cpu))

    # 5. Determine action
    if clamped_target > current:
        action = ScalingAction.SCALE_UP
        if latency_driver:
            driver = "P99_LATENCY"
            reason = (
                f"{fallback_reason}: P99 latency of {payload.http_p99_latency_ms:.1f}ms exceeds "
                f"threshold ({latency_threshold_ms}ms) with CPU at {payload.cpu_utilization_percent:.1f}%. "
                f"Scaling up from {current} to {clamped_target} replicas to relieve throughput bottleneck."
            )
        else:
            driver = "CPU_UTILIZATION"
            reason = (
                f"{fallback_reason}: CPU utilization of {payload.cpu_utilization_percent:.1f}% exceeds target "
                f"({target_cpu}%). Proportional scale up calculated from {current} to {clamped_target} replicas."
            )
    elif clamped_target < current:
        action = ScalingAction.SCALE_DOWN
        driver = "LOW_RESOURCE_DEMAND"
        reason = (
            f"{fallback_reason}: CPU utilization ({payload.cpu_utilization_percent:.1f}%) and latency "
            f"({payload.http_p99_latency_ms:.1f}ms) are comfortably below thresholds. "
            f"Safely consolidating workload from {current} to {clamped_target} replicas."
        )
    else:
        action = ScalingAction.MAINTAIN
        driver = "STEADY_STATE"
        reason = (
            f"{fallback_reason}: Telemetry (CPU: {payload.cpu_utilization_percent:.1f}%, "
            f"Latency: {payload.http_p99_latency_ms:.1f}ms) reflects balanced operating margin. "
            f"Maintaining current replica count of {current}."
        )

    return ScalingRecommendationResponse(
        workload_name=payload.workload_name,
        namespace=payload.namespace,
        current_replicas=payload.current_replicas,
        target_replicas=clamped_target,
        action=action,
        reasoning=reason,
        confidence_score=0.95,
        primary_metric_driver=driver,
        is_fallback=True,
        model_used="deterministic-heuristic"
    )
