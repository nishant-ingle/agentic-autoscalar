import asyncio
import logging
from typing import TypedDict, Optional, Dict, Any, List
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.telemetry import ClusterMetricsPayload
from app.schemas.recommendation import ScalingRecommendationResponse, ScalingAction
from app.services.heuristic import calculate_heuristic_scaling
from app.services.llm_factory import get_chat_model
from app.config import settings

logger = logging.getLogger(__name__)


class ReasonerState(TypedDict):
    payload: ClusterMetricsPayload
    target_cpu: float
    latency_threshold_ms: float
    analysis: Dict[str, Any]
    recommendation: Optional[ScalingRecommendationResponse]
    errors: List[str]


def analyze_telemetry_node(state: ReasonerState) -> Dict[str, Any]:
    """Node 1: Evaluates raw metrics and computes operational analysis."""
    payload = state["payload"]
    target_cpu = state.get("target_cpu", 65.0)
    latency_thresh = state.get("latency_threshold_ms", 250.0)

    cpu_ratio = payload.cpu_utilization_percent / target_cpu if target_cpu > 0 else 1.0
    latency_breach = payload.http_p99_latency_ms > latency_thresh
    high_error_rate = payload.error_rate_percent > 2.0

    analysis = {
        "cpu_ratio": round(cpu_ratio, 2),
        "is_cpu_high": payload.cpu_utilization_percent > (target_cpu * 1.15),
        "is_cpu_low": payload.cpu_utilization_percent < (target_cpu * 0.40),
        "is_latency_critical": latency_breach,
        "is_error_critical": high_error_rate,
        "urgency": "HIGH" if (latency_breach or high_error_rate or cpu_ratio > 1.4) else "NORMAL"
    }

    return {"analysis": analysis}


async def reasoning_node(state: ReasonerState) -> Dict[str, Any]:
    """Node 2: Invokes LLM with structured output or hands off to fallback."""
    payload = state["payload"]
    analysis = state.get("analysis", {})
    target_cpu = state.get("target_cpu", 65.0)

    llm = get_chat_model(
        provider=settings.llm_provider,
        model_name=settings.llm_model,
        temperature=settings.llm_temperature
    )
    if llm is None:
        logger.info("No LLM available or mock selected; routing to deterministic fallback.")
        return {"recommendation": None, "errors": ["No active LLM credentials configured"]}

    system_prompt = (
        "You are an expert Autonomous Site Reliability Engineer (SRE) managing a Kubernetes workload.\n"
        "Analyze the provided cluster telemetry, workload bounds, and performance targets.\n"
        "Your task is to generate a structured scaling recommendation following these rules:\n"
        "1. Strictly enforce target_replicas between min_replicas and max_replicas inclusive.\n"
        "2. If CPU utilization > target CPU or P99 latency > threshold, scale up to prevent degraded user experience.\n"
        "3. If CPU is significantly underutilized (< 40% of target) and traffic is idle, scale down conservatively by at least 1 replica to conserve infrastructure resources.\n"
        "4. If telemetry is balanced within healthy operational bounds, maintain current replicas.\n"
        "5. Provide rigorous analytical reasoning explaining the quantitative driver behind your decision."
    )

    human_prompt = (
        f"Workload: {payload.namespace}/{payload.workload_name}\n"
        f"Current Replicas: {payload.current_replicas}\n"
        f"Allowed Range: [{payload.min_replicas}, {payload.max_replicas}]\n"
        f"Target CPU Utilization: {target_cpu}%\n"
        f"Observed CPU Utilization: {payload.cpu_utilization_percent:.1f}%\n"
        f"Observed Memory Utilization: {payload.memory_utilization_percent:.1f}%\n"
        f"Observed Throughput (RPS): {payload.http_requests_per_second:.1f}\n"
        f"Observed P99 Latency: {payload.http_p99_latency_ms:.1f}ms\n"
        f"Error Rate: {payload.error_rate_percent:.1f}%\n"
        f"Pre-Analysis: {analysis}\n\n"
        f"Provide your scaling decision."
    )

    try:
        structured_llm = llm.with_structured_output(ScalingRecommendationResponse)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]

        # Enforce configurable timeout on LLM reasoning call (default 15s)
        res: ScalingRecommendationResponse = await asyncio.wait_for(
            structured_llm.ainvoke(messages),
            timeout=settings.timeout_seconds
        )

        # Enforce hard safety bounds on model output
        clamped_replicas = max(payload.min_replicas, min(payload.max_replicas, res.target_replicas))
        if clamped_replicas != res.target_replicas:
            res.reasoning += f" (Adjusted to respect strict safety boundary: {clamped_replicas})"
            res.target_replicas = clamped_replicas

        # Re-verify action enum consistency
        if res.target_replicas > payload.current_replicas:
            res.action = ScalingAction.SCALE_UP
        elif res.target_replicas < payload.current_replicas:
            res.action = ScalingAction.SCALE_DOWN
        else:
            res.action = ScalingAction.MAINTAIN

        res.is_fallback = False
        res.model_used = getattr(llm, "model_name", getattr(llm, "model", "llm-structured-agent"))
        logger.info(
            "✔ [LLM CALL SUCCESSFUL] Model: '%s' | Action: %s | Target Replicas: %d (Current: %d) | Confidence: %.2f",
            res.model_used,
            res.action.value,
            res.target_replicas,
            payload.current_replicas,
            res.confidence_score
        )
        return {"recommendation": res, "errors": []}

    except asyncio.TimeoutError:
        logger.warning("LLM call timed out after %.1f seconds; defaulting to hardcoded fallback engine.", settings.timeout_seconds)
        return {"recommendation": None, "errors": [f"Model timeout (>{settings.timeout_seconds:.0f}s)"]}
    except Exception as exc:
        logger.warning("LLM structured output failed (%s); defaulting to hardcoded fallback engine.", exc)
        return {"recommendation": None, "errors": [str(exc)]}


def fallback_node(state: ReasonerState) -> Dict[str, Any]:
    """Node 3: Executes deterministic fallback logic if LLM reasoning is absent or failed."""
    payload = state["payload"]
    target_cpu = state.get("target_cpu", 65.0)
    latency_thresh = state.get("latency_threshold_ms", 250.0)
    errors = state.get("errors", [])
    
    fallback_reason = "Deterministic SRE baseline"
    if errors:
        fallback_reason = f"Safety fallback engaged ({errors[0]})"

    logger.warning(
        "⚠ [DEFAULTED TO HARDCODED VALUES] Fallback Reason: '%s' | Workload: %s/%s | CPU: %.1f%% | Latency: %.1fms",
        fallback_reason,
        payload.namespace,
        payload.workload_name,
        payload.cpu_utilization_percent,
        payload.http_p99_latency_ms
    )

    recommendation = calculate_heuristic_scaling(
        payload=payload,
        target_cpu=target_cpu,
        latency_threshold_ms=latency_thresh,
        fallback_reason=fallback_reason
    )
    return {"recommendation": recommendation}


def should_fallback(state: ReasonerState) -> str:
    """Conditional edge router: checks if recommendation was successfully generated."""
    if state.get("recommendation") is not None:
        return "end"
    return "fallback"


def build_reasoning_graph():
    """Constructs and compiles the LangGraph StateMachine."""
    builder = StateGraph(ReasonerState)

    builder.add_node("analyze_telemetry", analyze_telemetry_node)
    builder.add_node("reasoning", reasoning_node)
    builder.add_node("fallback", fallback_node)

    builder.add_edge(START, "analyze_telemetry")
    builder.add_edge("analyze_telemetry", "reasoning")

    builder.add_conditional_edges(
        "reasoning",
        should_fallback,
        {
            "end": END,
            "fallback": "fallback"
        }
    )
    builder.add_edge("fallback", END)

    return builder.compile()


# Global compiled graph instance
reasoning_graph = build_reasoning_graph()
