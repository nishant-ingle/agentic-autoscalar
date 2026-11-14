"""Locust load testing script for comparative autoscaler evaluation.

Defines dynamic user behavior profiles (step-load and sudden flash-crowd traffic spikes)
targeting the Go/Gin microservice endpoints:
- /api/workload (mixed CPU + IO simulation)
- /api/load/cpu (burst CPU burn)
- /healthz (readiness & health check)
"""

import os
import time
from typing import Optional, Tuple
from locust import HttpUser, task, between, events
from locust.shape import LoadTestShape


# SLA Configuration: Requests taking longer than this threshold are counted as SLA violations.
SLA_LATENCY_THRESHOLD_MS = float(os.getenv("SLA_LATENCY_THRESHOLD_MS", "500.0"))


class EvaluationEventMetrics:
    """Thread-safe event tracker for Locust requests and SLA violations."""

    def __init__(self, sla_threshold_ms: float = SLA_LATENCY_THRESHOLD_MS):
        self.sla_threshold_ms = sla_threshold_ms
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.sla_violations = 0
        self.latencies = []

    def record_request(self, request_type: str, name: str, response_time: float, response_length: int, exception=None, **kwargs):
        self.total_requests += 1
        self.latencies.append(response_time)
        if exception:
            self.failed_requests += 1
        else:
            self.successful_requests += 1

        if response_time > self.sla_threshold_ms:
            self.sla_violations += 1

    def reset(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.sla_violations = 0
        self.latencies.clear()

    @property
    def sla_violation_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.sla_violations / self.total_requests) * 100.0


# Global metrics tracker instance
event_metrics = EvaluationEventMetrics()


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    event_metrics.record_request(
        request_type=request_type,
        name=name,
        response_time=response_time,
        response_length=response_length,
        exception=exception,
        **kwargs
    )


class MicroserviceUser(HttpUser):
    """Simulates realistic client traffic interacting with the target microservice."""

    wait_time = between(0.05, 0.2)

    @task(70)
    def workload_mixed(self):
        """Simulate realistic production API workload (CPU hashing + I/O delay)."""
        self.client.get(
            "/api/workload?rounds=15000&delay_ms=20",
            name="/api/workload"
        )

    @task(20)
    def cpu_burst(self):
        """Simulate periodic compute-intensive CPU burns."""
        self.client.get(
            "/api/load/cpu?duration_ms=600&concurrency=2",
            name="/api/load/cpu"
        )

    @task(10)
    def health_check(self):
        """Simulate lightweight status probes."""
        self.client.get(
            "/healthz",
            name="/healthz"
        )


class StepAndSpikeShape(LoadTestShape):
    """Dynamic load shape generating reproducible step-load and sudden flash-crowd traffic spikes.

    Stages:
    1. Baseline Warmup: Light steady traffic (10 users).
    2. Step Load (Ramp 1): Stepping to 30 users.
    3. Step Load (Ramp 2): Stepping to 60 users.
    4. Sudden Flash-Crowd Spike: Rapid surge to 150 users (simulates sudden viral event).
    5. Post-Spike Sustain: 100 users.
    6. Sharp Step-Down: Drops to 20 users (triggers and tests scale-down & hysteresis barrier).
    7. Idle Baseline: Final 5 users.
    """

    def __init__(self):
        super().__init__()
        # Allow scaling the duration of each stage via environment variables.
        # Default stage duration: 30 seconds (total 210s) for standard runs.
        # For 30-minute academic run, set STAGE_DURATION_SECS=250.
        self.stage_duration = int(os.getenv("STAGE_DURATION_SECS", "30"))
        self.total_stages = 7

    def get_stages(self):
        sd = self.stage_duration
        return [
            {"duration": sd * 1, "users": 10, "spawn_rate": 5},    # 1. Warm-up
            {"duration": sd * 2, "users": 30, "spawn_rate": 5},    # 2. Step 1
            {"duration": sd * 3, "users": 60, "spawn_rate": 10},   # 3. Step 2
            {"duration": sd * 4, "users": 150, "spawn_rate": 50},  # 4. Sudden Flash Spike
            {"duration": sd * 5, "users": 100, "spawn_rate": 15},  # 5. Post-spike sustain
            {"duration": sd * 6, "users": 20, "spawn_rate": 30},   # 6. Sharp step-down (hysteresis test)
            {"duration": sd * 7, "users": 5, "spawn_rate": 10},    # 7. Idle baseline
        ]

    def tick(self) -> Optional[Tuple[int, float]]:
        run_time = self.get_run_time()
        for stage in self.get_stages():
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None
