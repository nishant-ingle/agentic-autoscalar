from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ScalingAction(str, Enum):
    SCALE_UP = "SCALE_UP"
    SCALE_DOWN = "SCALE_DOWN"
    MAINTAIN = "MAINTAIN"


class ScalingRecommendationResponse(BaseModel):
    """Outgoing reasoned scaling recommendation from the agent."""
    workload_name: str = Field(..., description="Target workload identifier")
    namespace: str = Field(..., description="Target namespace")
    current_replicas: int = Field(..., ge=0, description="Current replica count before decision")
    target_replicas: int = Field(..., ge=1, description="Recommended target replica count")
    action: ScalingAction = Field(..., description="Proposed scaling action: SCALE_UP, SCALE_DOWN, or MAINTAIN")
    reasoning: str = Field(..., min_length=10, description="Detailed analytical justification for decision")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the scaling recommendation (0.0 - 1.0)"
    )
    primary_metric_driver: str = Field(
        default="METRICS_AGGREGATE",
        description="Key metric triggering the decision (e.g. CPU_UTILIZATION, P99_LATENCY, STEADY_STATE)"
    )
    operational_runbooks_retrieved: int = Field(
        default=0,
        ge=0,
        description="Number of relevant SRE incident runbooks retrieved from pgvector operational memory"
    )
    is_fallback: bool = Field(
        default=False, description="Whether fallback heuristic reasoning was engaged due to LLM error/timeout"
    )
    model_used: Optional[str] = Field(
        default=None, description="Model identifier used to produce recommendation"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of decision generation in UTC"
    )
