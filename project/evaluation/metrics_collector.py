"""Metrics Collector for comparative autoscaler evaluation.

Collects real-time telemetry across Prometheus, Kubernetes, and Locust during
benchmark runs, exporting structured time-series datasets (CSV/JSON) for downstream
analysis and visualization.
"""

import csv
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import requests

logger = logging.getLogger("MetricsCollector")


@dataclass
class MetricSample:
    timestamp: float
    elapsed_seconds: float
    regime: str  # "Standard-HPA" or "Agentic-Autoscaler"
    active_users: int
    rps: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    total_requests: int
    sla_violations: int
    error_rate_pct: float
    desired_replicas: int
    current_replicas: int
    cpu_utilization_pct: float
    guardrail_interceptions: int
    guardrail_action: str
    is_fallback: bool


class MetricsCollector:
    """Collects and aggregates time-series metrics during autoscaler evaluation."""

    def __init__(
        self,
        regime: str,
        prometheus_url: Optional[str] = None,
        locust_stats_url: Optional[str] = None,
        namespace: str = "workload-system",
        deployment_name: str = "target-workload",
        autoscaler_name: str = "target-workload-autoscaler",
        sla_threshold_ms: float = 500.0,
    ):
        self.regime = regime
        self.prometheus_url = prometheus_url or os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self.locust_stats_url = locust_stats_url or os.getenv("LOCUST_STATS_URL", "http://localhost:8089")
        self.namespace = namespace
        self.deployment_name = deployment_name
        self.autoscaler_name = autoscaler_name
        self.sla_threshold_ms = sla_threshold_ms

        self.samples: List[MetricSample] = []
        self.start_time: float = 0.0
        self.is_running: bool = False
        self._cumulative_guardrail_interceptions: int = 0

    def start(self):
        """Initializes the collection timer."""
        self.start_time = time.time()
        self.is_running = True
        self.samples.clear()
        self._cumulative_guardrail_interceptions = 0
        logger.info(f"Started MetricsCollector for regime '{self.regime}'")

    def stop(self):
        """Halts collection."""
        self.is_running = False
        logger.info(f"Stopped MetricsCollector. Total samples: {len(self.samples)}")

    def collect_sample(
        self,
        active_users: int = 0,
        override_rps: Optional[float] = None,
        override_latencies: Optional[Dict[str, float]] = None,
        override_replicas: Optional[int] = None,
        override_cpu: Optional[float] = None,
        override_total_requests: Optional[int] = None,
        override_sla_violations: Optional[int] = None,
        override_guardrail_action: Optional[str] = None,
    ) -> MetricSample:
        """Collects a single snapshot of system telemetry."""
        now = time.time()
        elapsed = now - (self.start_time if self.start_time > 0 else now)

        # 1. Gather Locust / Traffic Telemetry
        locust_metrics = self._query_locust_stats()
        rps = override_rps if override_rps is not None else locust_metrics.get("rps", 0.0)
        p50 = override_latencies.get("p50", 0.0) if override_latencies else locust_metrics.get("p50", 0.0)
        p90 = override_latencies.get("p90", 0.0) if override_latencies else locust_metrics.get("p90", 0.0)
        p95 = override_latencies.get("p95", 0.0) if override_latencies else locust_metrics.get("p95", 0.0)
        p99 = override_latencies.get("p99", 0.0) if override_latencies else locust_metrics.get("p99", 0.0)
        max_lat = override_latencies.get("max", 0.0) if override_latencies else locust_metrics.get("max", 0.0)
        total_reqs = override_total_requests if override_total_requests is not None else locust_metrics.get("total_requests", 0)
        sla_viols = override_sla_violations if override_sla_violations is not None else locust_metrics.get("sla_violations", 0)
        err_pct = locust_metrics.get("error_rate_pct", 0.0)
        users = active_users or locust_metrics.get("active_users", 0)

        # 2. Gather Kubernetes Deployment Replicas
        k8s_replicas = self._query_k8s_replicas()
        current_reps = override_replicas if override_replicas is not None else k8s_replicas.get("current", 1)
        desired_reps = override_replicas if override_replicas is not None else k8s_replicas.get("desired", current_reps)

        # 3. Gather CPU Utilization
        cpu_pct = override_cpu if override_cpu is not None else self._query_cpu_utilization()

        # 4. Gather Guardrail Interceptions (for Agentic Autoscaler)
        guardrail_info = self._query_guardrail_status()
        action = override_guardrail_action if override_guardrail_action is not None else guardrail_info.get("action", "NONE")
        if action in ["CLAMPED", "REJECTED"]:
            self._cumulative_guardrail_interceptions += 1

        sample = MetricSample(
            timestamp=now,
            elapsed_seconds=round(elapsed, 2),
            regime=self.regime,
            active_users=users,
            rps=round(rps, 2),
            p50_latency_ms=round(p50, 2),
            p90_latency_ms=round(p90, 2),
            p95_latency_ms=round(p95, 2),
            p99_latency_ms=round(p99, 2),
            max_latency_ms=round(max_lat, 2),
            total_requests=total_reqs,
            sla_violations=sla_viols,
            error_rate_pct=round(err_pct, 2),
            desired_replicas=desired_reps,
            current_replicas=current_reps,
            cpu_utilization_pct=round(cpu_pct, 2),
            guardrail_interceptions=self._cumulative_guardrail_interceptions,
            guardrail_action=action,
            is_fallback=guardrail_info.get("is_fallback", False),
        )
        self.samples.append(sample)
        return sample

    def _query_locust_stats(self) -> Dict:
        """Polls Locust REST API if accessible."""
        stats = {
            "rps": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
            "total_requests": 0,
            "sla_violations": 0,
            "error_rate_pct": 0.0,
            "active_users": 0,
        }
        try:
            resp = requests.get(f"{self.locust_stats_url}/stats/requests", timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                stats["rps"] = data.get("total_rps", 0.0)
                stats["active_users"] = data.get("user_count", 0)
                # Aggregate latency percentiles from total stats item
                for item in data.get("stats", []):
                    if item.get("name") == "Aggregated":
                        stats["total_requests"] = item.get("num_requests", 0)
                        num_failures = item.get("num_failures", 0)
                        if stats["total_requests"] > 0:
                            stats["error_rate_pct"] = (num_failures / stats["total_requests"]) * 100.0
                        stats["max"] = item.get("max_response_time", 0.0)
                
                # Check percentiles endpoint if available
                p_resp = requests.get(f"{self.locust_stats_url}/stats/percentiles", timeout=1.0)
                if p_resp.status_code == 200:
                    p_data = p_resp.json()
                    for p_item in p_data.get("percentiles", []):
                        if p_item.get("name") == "Aggregated":
                            stats["p50"] = p_item.get("50%", 0.0)
                            stats["p90"] = p_item.get("90%", 0.0)
                            stats["p95"] = p_item.get("95%", 0.0)
                            stats["p99"] = p_item.get("99%", 0.0)
        except Exception:
            # Locust API may not be active; callers can provide overrides or simulated values
            pass
        return stats

    def _query_k8s_replicas(self) -> Dict[str, int]:
        """Queries deployment replicas from Kubernetes API via kubectl."""
        res = {"desired": 1, "current": 1}
        try:
            cmd = [
                "kubectl", "get", "deployment", self.deployment_name,
                "-n", self.namespace,
                "-o", "jsonpath={.spec.replicas},{.status.readyReplicas}"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if proc.returncode == 0 and proc.stdout:
                parts = proc.stdout.strip().split(",")
                desired = int(parts[0]) if parts[0].isdigit() else 1
                current = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else desired
                res["desired"] = desired
                res["current"] = current
        except Exception:
            pass
        return res

    def _query_cpu_utilization(self) -> float:
        """Queries CPU utilization from Prometheus or kubectl top."""
        if self.prometheus_url:
            try:
                # PromQL query for CPU utilization
                query = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{self.namespace}",pod=~"{self.deployment_name}-.*"}}[1m])) * 100'
                resp = requests.get(f"{self.prometheus_url}/api/v1/query", params={"query": query}, timeout=1.5)
                if resp.status_code == 200:
                    result = resp.json().get("data", {}).get("result", [])
                    if result and len(result) > 0:
                        val = float(result[0].get("value", [0, 0])[1])
                        return max(0.0, min(100.0, val))
            except Exception:
                pass

        # Fallback to kubectl top pod
        try:
            cmd = ["kubectl", "top", "pods", "-n", self.namespace, "-l", f"app={self.deployment_name}", "--no-headers"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if proc.returncode == 0 and proc.stdout:
                lines = proc.stdout.strip().split("\n")
                total_mcores = 0
                for line in lines:
                    cols = line.split()
                    if len(cols) >= 2 and cols[1].endswith("m"):
                        total_mcores += int(cols[1].rstrip("m"))
                # Assuming 100m is 100% request baseline
                return float(total_mcores)
        except Exception:
            pass
        return 0.0

    def _query_guardrail_status(self) -> Dict:
        """Queries AgenticAutoscaler custom resource status for guardrail actions."""
        res = {"action": "NONE", "is_fallback": False}
        if self.regime != "Agentic-Autoscaler":
            return res

        try:
            cmd = [
                "kubectl", "get", "agenticautoscaler", self.autoscaler_name,
                "-n", self.namespace,
                "-o", "jsonpath={.status.lastGuardrailAction},{.status.fallbackEngaged}"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if proc.returncode == 0 and proc.stdout:
                parts = proc.stdout.strip().split(",")
                action = parts[0] if parts[0] else "NONE"
                fallback = parts[1].lower() == "true" if len(parts) > 1 else False
                res["action"] = action
                res["is_fallback"] = fallback
        except Exception:
            pass
        return res

    def export_to_csv(self, filepath: str):
        """Exports all recorded samples to a clean CSV dataset."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        if not self.samples:
            logger.warning("No samples to export.")
            return

        keys = list(asdict(self.samples[0]).keys())
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for s in self.samples:
                writer.writerow(asdict(s))
        logger.info(f"Successfully exported {len(self.samples)} rows to {filepath}")

    def export_to_json(self, filepath: str):
        """Exports all recorded samples to a structured JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = [asdict(s) for s in self.samples]
        with open(filepath, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Successfully exported JSON dataset to {filepath}")
