import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingRecommendationResponse
from app.services.graph import reasoning_graph
from app.services.mcp_client import mcp_client
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
            "rag_context": [],
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


@router.get(
    "/mcp/tools",
    summary="Discover tools from Model Context Protocol (MCP) server",
    description="Acts as an MCP client to dynamically discover infrastructure tools exposed by the MCP server."
)
async def list_mcp_tools() -> Dict[str, Any]:
    """Queries MCP server over SSE and returns the discovered tool catalog."""
    tools = await mcp_client.list_available_tools()
    return {
        "mcp_server_url": mcp_client.mcp_url,
        "tools_discovered_count": len(tools),
        "tools": tools
    }


@router.post(
    "/evaluate-scaling-mcp",
    response_model=ScalingRecommendationResponse,
    summary="Evaluate scaling enriched with live MCP cluster telemetry",
    description="Enriches input telemetry with real-time MCP pod metrics and recent logs before invoking the reasoning agent."
)
async def evaluate_scaling_with_mcp(payload: ClusterMetricsPayload) -> ScalingRecommendationResponse:
    """Enriches payload with live MCP cluster metrics and evaluates scaling."""
    try:
        # Query MCP for live cluster metrics and recent logs
        mcp_cluster_info = await mcp_client.get_cluster_telemetry(
            namespace=payload.namespace,
            workload_name=payload.workload_name
        )
        recent_logs = await mcp_client.fetch_pod_logs(
            namespace=payload.namespace,
            workload_name=payload.workload_name,
            tail_lines=15
        )

        initial_state = {
            "payload": payload,
            "target_cpu": settings.target_cpu_percent,
            "latency_threshold_ms": settings.latency_spike_threshold_ms,
            "analysis": {
                "mcp_enrichment": {
                    "cluster_status": mcp_cluster_info.get("status"),
                    "ready_replicas": mcp_cluster_info.get("ready_replicas", payload.current_replicas),
                    "pods_sampled": recent_logs.get("pods_sampled", 0)
                }
            },
            "rag_context": [],
            "recommendation": None,
            "errors": []
        }

        result = await reasoning_graph.ainvoke(initial_state)
        rec = result.get("recommendation")
        if rec is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate MCP-enriched scaling recommendation"
            )

        if mcp_cluster_info.get("status") in ("success", "mock_success"):
            rec.reasoning = f"[Enriched via MCP Server] {rec.reasoning}"

        return rec
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in /evaluate-scaling-mcp: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP evaluation error: {str(exc)}"
        )
