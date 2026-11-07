from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class PodMetricItem(BaseModel):
    pod_name: str = Field(..., description="Name of the pod")
    cpu_millicores: float = Field(..., ge=0, description="CPU usage in millicores")
    memory_megabytes: float = Field(..., ge=0, description="Memory consumption in MB")
    ready: bool = Field(True, description="Whether pod passes readiness probes")


class ClusterMetricsPayload(BaseModel):
    """Incoming cluster telemetry payload collected by the operator / Prometheus."""
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of metric observation in UTC"
    )
    namespace: str = Field(..., min_length=1, description="Kubernetes namespace of target workload")
    workload_name: str = Field(..., min_length=1, description="Deployment name of target workload")
    current_replicas: int = Field(..., ge=0, description="Current number of active replicas")
    min_replicas: int = Field(..., ge=1, description="Minimum allowed replicas")
    max_replicas: int = Field(..., ge=1, description="Maximum allowed replicas")
    cpu_utilization_percent: float = Field(
        ..., ge=0.0, description="Observed average CPU utilization as a percentage"
    )
    memory_utilization_percent: float = Field(
        ..., ge=0.0, description="Observed average Memory utilization as a percentage"
    )
    http_requests_per_second: float = Field(
        ..., ge=0.0, description="Aggregated HTTP requests per second"
    )
    http_p99_latency_ms: float = Field(
        ..., ge=0.0, description="Observed P99 HTTP latency in milliseconds"
    )
    error_rate_percent: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Percentage of 5xx HTTP responses"
    )
    pod_metrics: Optional[List[PodMetricItem]] = Field(
        default=None, description="Optional per-pod granular metrics"
    )

    @model_validator(mode="after")
    def validate_replica_bounds(self) -> "ClusterMetricsPayload":
        if self.max_replicas < self.min_replicas:
            raise ValueError(
                f"max_replicas ({self.max_replicas}) cannot be less than min_replicas ({self.min_replicas})"
            )
        return self
