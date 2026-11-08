import logging
import time
from typing import Dict, Any, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Asynchronous client for querying Prometheus metrics."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")
        self.timeout = 10.0

    async def query_instant(self, query: str) -> Dict[str, Any]:
        """Executes an instant PromQL query (/api/v1/query)."""
        url = f"{self.base_url}/api/v1/query"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params={"query": query})
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "success":
                    return {"status": "error", "error": data.get("error", "Unknown Prometheus error")}
                return {
                    "status": "success",
                    "result_type": data.get("data", {}).get("resultType"),
                    "results": data.get("data", {}).get("result", [])
                }
        except Exception as exc:
            logger.warning("Prometheus instant query failed (%s): %s", query, exc)
            return {"status": "error", "error": str(exc), "query": query}

    async def query_range(
        self,
        query: str,
        start_seconds_ago: int = 300,
        step: str = "15s"
    ) -> Dict[str, Any]:
        """Executes a PromQL range query (/api/v1/query_range).
        
        Args:
            query: PromQL query expression.
            start_seconds_ago: Time window lookback in seconds (default: 300s / 5m).
            step: Query resolution step (e.g., '15s', '1m').
        """
        now = time.time()
        start = now - start_seconds_ago
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": str(start),
            "end": str(now),
            "step": step
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "success":
                    return {"status": "error", "error": data.get("error", "Prometheus error")}

                results = data.get("data", {}).get("result", [])
                formatted_series: List[Dict[str, Any]] = []

                for item in results:
                    metric = item.get("metric", {})
                    values = item.get("values", [])
                    numeric_values = []
                    for v in values:
                        try:
                            numeric_values.append(float(v[1]))
                        except (ValueError, IndexError):
                            pass

                    stats = {
                        "count": len(numeric_values),
                        "min": min(numeric_values) if numeric_values else None,
                        "max": max(numeric_values) if numeric_values else None,
                        "avg": round(sum(numeric_values) / len(numeric_values), 4) if numeric_values else None,
                        "latest": numeric_values[-1] if numeric_values else None
                    }

                    formatted_series.append({
                        "metric": metric,
                        "stats": stats,
                        "sample_points_count": len(values),
                        "recent_samples": values[-5:] if values else []
                    })

                return {
                    "status": "success",
                    "query": query,
                    "lookback_seconds": start_seconds_ago,
                    "step": step,
                    "series_count": len(formatted_series),
                    "series": formatted_series
                }
        except Exception as exc:
            logger.warning("Prometheus range query failed (%s): %s", query, exc)
            # If in mock mode or test environment without live Prometheus
            if settings.mock_mode:
                return {
                    "status": "mock_success",
                    "query": query,
                    "lookback_seconds": start_seconds_ago,
                    "step": step,
                    "series_count": 1,
                    "series": [{
                        "metric": {"job": "target-workload", "mock": "true"},
                        "stats": {"count": 20, "min": 25.0, "max": 80.0, "avg": 52.5, "latest": 68.0},
                        "sample_points_count": 20,
                        "recent_samples": [[now - 30, "65.0"], [now - 15, "68.0"]]
                    }]
                }
            return {"status": "error", "error": str(exc), "query": query}


prom_client = PrometheusClient()
