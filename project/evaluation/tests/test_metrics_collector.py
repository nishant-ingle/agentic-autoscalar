"""Unit tests for MetricsCollector and dataset exporters."""

import csv
import json
import os
import pytest
from evaluation.metrics_collector import MetricsCollector, MetricSample


class TestMetricsCollector:
    """Tests metrics collection, schema sanitization, and CSV/JSON export."""

    def test_collector_lifecycle(self):
        """Verify collector start, sample accumulation, and stop."""
        collector = MetricsCollector(regime="Standard-HPA")
        assert not collector.is_running
        assert len(collector.samples) == 0

        collector.start()
        assert collector.is_running

        sample = collector.collect_sample(
            active_users=25,
            override_rps=150.0,
            override_latencies={"p50": 20.0, "p90": 45.0, "p95": 60.0, "p99": 85.0, "max": 120.0},
            override_replicas=2,
            override_cpu=65.5,
        )

        assert isinstance(sample, MetricSample)
        assert sample.regime == "Standard-HPA"
        assert sample.active_users == 25
        assert sample.rps == 150.0
        assert sample.p99_latency_ms == 85.0
        assert sample.current_replicas == 2
        assert sample.cpu_utilization_pct == 65.5
        assert len(collector.samples) == 1

        collector.stop()
        assert not collector.is_running

    def test_export_to_csv(self, tmp_path):
        """Verify CSV export formats all required evaluation columns."""
        collector = MetricsCollector(regime="Agentic-Autoscaler")
        collector.start()

        collector.collect_sample(
            active_users=50,
            override_rps=325.0,
            override_latencies={"p50": 25.0, "p90": 55.0, "p95": 75.0, "p99": 110.0, "max": 150.0},
            override_replicas=3,
            override_cpu=72.0,
        )
        collector.stop()

        csv_file = tmp_path / "test_metrics.csv"
        collector.export_to_csv(str(csv_file))

        assert os.path.exists(csv_file)
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            row = rows[0]
            assert row["regime"] == "Agentic-Autoscaler"
            assert row["active_users"] == "50"
            assert float(row["p99_latency_ms"]) == 110.0
            assert int(row["current_replicas"]) == 3

    def test_export_to_json(self, tmp_path):
        """Verify structured JSON dataset export."""
        collector = MetricsCollector(regime="Agentic-Autoscaler")
        collector.start()

        collector.collect_sample(
            active_users=10,
            override_rps=65.0,
            override_latencies={"p50": 15.0, "p90": 30.0, "p95": 40.0, "p99": 50.0, "max": 65.0},
            override_replicas=1,
            override_cpu=30.0,
        )
        collector.stop()

        json_file = tmp_path / "test_metrics.json"
        collector.export_to_json(str(json_file))

        assert os.path.exists(json_file)
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["regime"] == "Agentic-Autoscaler"
            assert data[0]["rps"] == 65.0
