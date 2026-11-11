import json
import logging
import time
from typing import AsyncIterator, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingRecommendationResponse
from app.services.graph import reasoning_graph, build_streaming_llm
from app.services.mcp_client import mcp_client
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Scaling"])


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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
        graph_t0 = time.perf_counter()
        result = await reasoning_graph.ainvoke(initial_state)
        graph_latency_ms = (time.perf_counter() - graph_t0) * 1000
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

        logger.info(
            "⏱ [LATENCY] Total graph: %.1fms | is_fallback=%s | workload=%s/%s",
            graph_latency_ms, recommendation.is_fallback, payload.namespace, payload.workload_name
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


@router.post(
    "/evaluate-scaling/stream",
    summary="Stream LLM reasoning tokens in real-time (SSE)",
    description=(
        "Runs the same LangGraph pipeline as /evaluate-scaling but streams LLM tokens "
        "as Server-Sent Events. The final event contains the complete structured decision. "
        "Intended for monitoring dashboards and debugging — the Go operator uses the "
        "non-streaming endpoint."
    ),
    response_class=StreamingResponse,
)
async def evaluate_scaling_stream(payload: ClusterMetricsPayload) -> StreamingResponse:
    """SSE endpoint: streams LLM reasoning tokens then emits the final structured decision."""

    async def _event_generator() -> AsyncIterator[str]:
        t0 = time.perf_counter()

        # ── Phase 1: build the same state the graph uses ──────────────────────
        llm = build_streaming_llm()
        if llm is None:
            yield _sse("error", {"message": "No LLM configured; streaming unavailable"})
            return

        from app.services.graph import analyze_telemetry_node, ReasonerState
        from app.services.heuristic import calculate_heuristic_scaling
        from langchain_core.messages import SystemMessage, HumanMessage

        state: ReasonerState = {
            "payload": payload,
            "target_cpu": settings.target_cpu_percent,
            "latency_threshold_ms": settings.latency_spike_threshold_ms,
            "analysis": {},
            "rag_context": [],
            "recommendation": None,
            "errors": [],
        }

        # ── Phase 2: RAG + telemetry analysis (synchronous node) ──────────────
        rag_t0 = time.perf_counter()
        updates = analyze_telemetry_node(state)
        state.update(updates)
        rag_ms = (time.perf_counter() - rag_t0) * 1000
        yield _sse("rag_complete", {
            "rag_latency_ms": round(rag_ms, 1),
            "runbooks_retrieved": len(state["rag_context"]),
        })

        # ── Phase 3: stream LLM tokens ────────────────────────────────────────
        from app.services.graph import _build_messages
        system_msg, human_msg = _build_messages(state)
        messages = [SystemMessage(content=system_msg), HumanMessage(content=human_msg)]

        llm_t0 = time.perf_counter()
        token_count = 0
        full_text = ""
        try:
            async for chunk in llm.astream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    full_text += token
                    token_count += 1
                    yield _sse("token", {"text": token})

            llm_ms = (time.perf_counter() - llm_t0) * 1000
            yield _sse("llm_complete", {
                "llm_latency_ms": round(llm_ms, 1),
                "tokens_streamed": token_count,
            })
            logger.info(
                "⏱ [STREAM] RAG=%.1fms | LLM=%.1fms | tokens=%d | workload=%s/%s",
                rag_ms, llm_ms, token_count, payload.namespace, payload.workload_name,
            )

        except Exception as exc:
            logger.warning("Streaming LLM failed (%s); falling back to heuristic.", exc)
            yield _sse("error", {"message": str(exc)})
            rec = calculate_heuristic_scaling(
                payload=payload,
                target_cpu=settings.target_cpu_percent,
                latency_threshold_ms=settings.latency_spike_threshold_ms,
                fallback_reason=f"Stream error: {exc}",
            )
            yield _sse("decision", rec.model_dump(mode="json"))
            yield _sse("done", {"total_ms": round((time.perf_counter() - t0) * 1000, 1)})
            return

        # ── Phase 4: emit the full structured decision via the standard graph ──
        # Re-use the non-streaming graph so structured_output parsing is reliable.
        graph_t0 = time.perf_counter()
        result = await reasoning_graph.ainvoke(state)
        rec = result.get("recommendation")
        graph_ms = (time.perf_counter() - graph_t0) * 1000

        if rec is None:
            yield _sse("error", {"message": "Graph produced no recommendation"})
        else:
            yield _sse("decision", rec.model_dump(mode="json"))

        total_ms = (time.perf_counter() - t0) * 1000
        yield _sse("done", {
            "total_ms": round(total_ms, 1),
            "rag_ms": round(rag_ms, 1),
            "llm_stream_ms": round(llm_ms, 1),
            "graph_structured_ms": round(graph_ms, 1),
        })

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


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
