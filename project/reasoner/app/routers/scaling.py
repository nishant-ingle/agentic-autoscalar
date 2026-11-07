import logging
from fastapi import APIRouter, HTTPException, status
from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingRecommendationResponse
from app.services.graph import reasoning_graph
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Scaling"])


@router.post(
    "/evaluate-scaling",
    response_model=ScalingRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate cluster telemetry and recommend scaling action",
    description="Processes incoming cluster telemetry through a LangGraph reasoning agent, producing structured scaling proposals."
)
async def evaluate_scaling(payload: ClusterMetricsPayload) -> ScalingRecommendationResponse:
    try:
        initial_state = {
            "payload": payload,
            "target_cpu": settings.target_cpu_percent,
            "latency_threshold_ms": settings.latency_spike_threshold_ms,
            "analysis": {},
            "recommendation": None,
            "errors": []
        }

        # Invoke the LangGraph StateMachine asynchronously
        result = await reasoning_graph.ainvoke(initial_state)
        recommendation = result.get("recommendation")

        if recommendation is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate scaling recommendation"
            )

        if recommendation.is_fallback:
            logger.warning(
                "DECISION RESULT: [DEFAULTED TO HARDCODED VALUES] Workload: %s/%s | Action: %s | Target: %d | Source: %s | Driver: %s",
                payload.namespace,
                payload.workload_name,
                recommendation.action.value,
                recommendation.target_replicas,
                recommendation.model_used,
                recommendation.primary_metric_driver
            )
        else:
            logger.info(
                "DECISION RESULT: [LLM CALLED SUCCESSFULLY] Workload: %s/%s | Action: %s | Target: %d | Source: %s | Driver: %s",
                payload.namespace,
                payload.workload_name,
                recommendation.action.value,
                recommendation.target_replicas,
                recommendation.model_used,
                recommendation.primary_metric_driver
            )

        return recommendation

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in /evaluate-scaling: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal reasoning error: {str(exc)}"
        )
