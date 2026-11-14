"""Unit tests for Locust load testing script and traffic profiles."""

import pytest
from evaluation.locustfile import (
    MicroserviceUser,
    StepAndSpikeShape,
    EvaluationEventMetrics,
    SLA_LATENCY_THRESHOLD_MS,
)


class TestLocustLoadScript:
    """Tests Locust user profiles, load shapes, and SLA tracking."""

    def test_user_task_weights(self):
        """Verify task definitions and weighting on MicroserviceUser."""
        tasks = MicroserviceUser.tasks
        # MicroserviceUser defines tasks via decorators: workload_mixed, cpu_burst, health_check
        assert hasattr(MicroserviceUser, "workload_mixed")
        assert hasattr(MicroserviceUser, "cpu_burst")
        assert hasattr(MicroserviceUser, "health_check")
        assert MicroserviceUser.wait_time is not None

    def test_step_and_spike_shape_stages(self):
        """Verify dynamic load shape defines expected stage transitions."""
        shape = StepAndSpikeShape()
        shape.stage_duration = 10
        stages = shape.get_stages()

        assert len(stages) == 7
        # Stage 1: Warmup
        assert stages[0]["users"] == 10
        # Stage 2: Step 1
        assert stages[1]["users"] == 30
        # Stage 3: Step 2
        assert stages[2]["users"] == 60
        # Stage 4: Sudden Flash Spike
        assert stages[3]["users"] == 150
        assert stages[3]["spawn_rate"] >= 50
        # Stage 5: Post-spike sustain
        assert stages[4]["users"] == 100
        # Stage 6: Sharp step-down (testing hysteresis)
        assert stages[5]["users"] == 20
        # Stage 7: Idle baseline
        assert stages[6]["users"] == 5

    def test_step_and_spike_shape_tick(self, monkeypatch):
        """Verify tick() returns correct user counts across time boundaries."""
        shape = StepAndSpikeShape()
        shape.stage_duration = 10

        # Simulate elapsed time 5s (Stage 1)
        monkeypatch.setattr(shape, "get_run_time", lambda: 5.0)
        users, spawn_rate = shape.tick()
        assert users == 10
        assert spawn_rate == 5

        # Simulate elapsed time 35s (Stage 4 - Spike)
        monkeypatch.setattr(shape, "get_run_time", lambda: 35.0)
        users, spawn_rate = shape.tick()
        assert users == 150
        assert spawn_rate == 50

        # Simulate elapsed time after all stages (75s > 70s)
        monkeypatch.setattr(shape, "get_run_time", lambda: 75.0)
        assert shape.tick() is None

    def test_sla_metrics_tracking(self):
        """Verify SLA violation tracking and percentage calculations."""
        metrics = EvaluationEventMetrics(sla_threshold_ms=500.0)

        # 1. Fast request (under SLA threshold)
        metrics.record_request("GET", "/api/workload", 120.0, 1024, exception=None)
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.sla_violations == 0
        assert metrics.sla_violation_rate == 0.0

        # 2. Slow request (exceeds SLA threshold)
        metrics.record_request("GET", "/api/load/cpu", 750.0, 512, exception=None)
        assert metrics.total_requests == 2
        assert metrics.sla_violations == 1
        assert metrics.sla_violation_rate == 50.0

        # 3. Failed request
        metrics.record_request("GET", "/api/workload", 900.0, 0, exception=Exception("Timeout"))
        assert metrics.total_requests == 3
        assert metrics.failed_requests == 1
        assert metrics.sla_violations == 2
        assert pytest.approx(metrics.sla_violation_rate, 0.1) == 66.67

        # 4. Reset
        metrics.reset()
        assert metrics.total_requests == 0
        assert metrics.sla_violations == 0
        assert metrics.sla_violation_rate == 0.0
