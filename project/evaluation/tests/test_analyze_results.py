"""Unit tests for EvaluationAnalyzer and visualization rendering."""

import os
import pandas as pd
import pytest
from evaluation.analyze_results import EvaluationAnalyzer


@pytest.fixture
def sample_datasets(tmp_path):
    """Generates synthetic HPA and Agentic CSV datasets for testing."""
    hpa_rows = []
    agentic_rows = []

    # 10 time steps
    for i in range(10):
        t = i * 5.0
        # HPA has higher latency and flapping
        hpa_rows.append({
            "timestamp": 1700000000 + t,
            "elapsed_seconds": t,
            "regime": "Standard-HPA",
            "active_users": 10 if i < 3 else (100 if i < 7 else 20),
            "rps": 50.0 if i < 3 else 500.0,
            "p50_latency_ms": 25.0 if i < 3 else 280.0,
            "p90_latency_ms": 40.0 if i < 3 else 600.0,
            "p95_latency_ms": 50.0 if i < 3 else 750.0,
            "p99_latency_ms": 70.0 if i < 3 else 950.0,
            "max_latency_ms": 120.0 if i < 3 else 1200.0,
            "total_requests": (i + 1) * 200,
            "sla_violations": 0 if i < 3 else (i - 2) * 50,
            "error_rate_pct": 0.0,
            "desired_replicas": 1 if i < 4 else (4 if i < 7 else 1),
            "current_replicas": 1 if i < 4 else (4 if i < 7 else 1),
            "cpu_utilization_pct": 30.0 if i < 3 else 90.0,
            "guardrail_interceptions": 0,
            "guardrail_action": "NONE",
            "is_fallback": False,
        })

        # Agentic maintains low latency with proactive scale-up and no flapping
        agentic_rows.append({
            "timestamp": 1700000000 + t,
            "elapsed_seconds": t,
            "regime": "Agentic-Autoscaler",
            "active_users": 10 if i < 3 else (100 if i < 7 else 20),
            "rps": 50.0 if i < 3 else 500.0,
            "p50_latency_ms": 15.0 if i < 3 else 45.0,
            "p90_latency_ms": 25.0 if i < 3 else 80.0,
            "p95_latency_ms": 35.0 if i < 3 else 110.0,
            "p99_latency_ms": 45.0 if i < 3 else 160.0,
            "max_latency_ms": 80.0 if i < 3 else 250.0,
            "total_requests": (i + 1) * 200,
            "sla_violations": 0,
            "error_rate_pct": 0.0,
            "desired_replicas": 1 if i < 3 else 4,
            "current_replicas": 1 if i < 3 else 4,  # hysteresis holds replicas at 4!
            "cpu_utilization_pct": 30.0 if i < 3 else 65.0,
            "guardrail_interceptions": 0 if i < 7 else 2,
            "guardrail_action": "ACCEPTED" if i < 7 else "REJECTED",
            "is_fallback": False,
        })

    hpa_csv = tmp_path / "hpa_metrics.csv"
    agentic_csv = tmp_path / "agentic_metrics.csv"

    pd.DataFrame(hpa_rows).to_csv(hpa_csv, index=False)
    pd.DataFrame(agentic_rows).to_csv(agentic_csv, index=False)

    return str(hpa_csv), str(agentic_csv), str(tmp_path)


class TestEvaluationAnalyzer:
    """Tests metrics aggregation, chart rendering, and report synthesis."""

    def test_calculate_metrics(self, sample_datasets):
        hpa_csv, agentic_csv, out_dir = sample_datasets
        analyzer = EvaluationAnalyzer(hpa_csv, agentic_csv, out_dir)
        metrics = analyzer.calculate_metrics()

        assert "hpa" in metrics
        assert "agentic" in metrics
        assert "delta" in metrics

        # HPA p99 max should be ~950ms, Agentic ~160ms
        assert metrics["hpa"]["p99_max_ms"] == 950.0
        assert metrics["agentic"]["p99_max_ms"] == 160.0

        # Peak latency reduction delta should be positive (>50%)
        assert metrics["delta"]["p99_peak_reduction_pct"] > 50.0

        # Flapping should be present in HPA (scaled down immediately), 0 in Agentic
        assert metrics["hpa"]["flapping_events"] >= 1
        assert metrics["agentic"]["flapping_events"] == 0

    def test_chart_generation(self, sample_datasets):
        hpa_csv, agentic_csv, out_dir = sample_datasets
        analyzer = EvaluationAnalyzer(hpa_csv, agentic_csv, out_dir)
        charts = analyzer.generate_all_charts()

        for name, path in charts.items():
            assert os.path.exists(path), f"Chart {name} was not generated at {path}"
            assert os.path.getsize(path) > 1000  # Ensure PNG file is non-empty

    def test_markdown_report_generation(self, sample_datasets):
        hpa_csv, agentic_csv, out_dir = sample_datasets
        analyzer = EvaluationAnalyzer(hpa_csv, agentic_csv, out_dir)
        report_path = analyzer.generate_markdown_report()

        assert os.path.exists(report_path)
        assert os.path.getsize(report_path) > 500

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Empirical Evaluation Report" in content
            assert "Standard Kubernetes HPA" in content
            assert "Agentic Autoscaler" in content
            assert "Figure 1: Response Latency Over Time" in content
