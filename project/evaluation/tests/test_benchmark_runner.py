"""Unit tests for BenchmarkRunner and comparative regime orchestration."""

import os
import pytest
from evaluation.benchmark_runner import BenchmarkRunner


class TestBenchmarkRunner:
    """Tests runner setup, state resets, and simulation execution."""

    def test_runner_initialization(self, tmp_path):
        """Verify runner initialization in simulation mode."""
        runner = BenchmarkRunner(
            output_dir=str(tmp_path),
            stage_duration_secs=5,
            mode="simulation"
        )
        assert runner.mode == "simulation"
        assert runner.stage_duration_secs == 5
        assert runner.output_dir == str(tmp_path)

    def test_state_resets_simulation(self, tmp_path):
        """Verify state reset hooks execute cleanly in simulation mode."""
        runner = BenchmarkRunner(
            output_dir=str(tmp_path),
            stage_duration_secs=5,
            mode="simulation"
        )
        # Should execute without errors or exceptions
        runner.reset_state_for_hpa()
        runner.reset_state_for_agentic()

    def test_run_regime_hpa_simulation(self, tmp_path):
        """Verify executing Standard HPA regime generates CSV dataset."""
        runner = BenchmarkRunner(
            output_dir=str(tmp_path),
            stage_duration_secs=2,  # total 14 seconds simulation
            mode="simulation"
        )
        csv_path = runner.run_regime("Standard-HPA")
        assert os.path.exists(csv_path)
        assert os.path.basename(csv_path) == "hpa_metrics.csv"
        assert os.path.getsize(csv_path) > 0

    def test_run_regime_agentic_simulation(self, tmp_path):
        """Verify executing Agentic Autoscaler regime generates CSV dataset."""
        runner = BenchmarkRunner(
            output_dir=str(tmp_path),
            stage_duration_secs=2,
            mode="simulation"
        )
        csv_path = runner.run_regime("Agentic-Autoscaler")
        assert os.path.exists(csv_path)
        assert os.path.basename(csv_path) == "agentic_metrics.csv"
        assert os.path.getsize(csv_path) > 0

    def test_run_comparative_benchmark(self, tmp_path):
        """Verify complete end-to-end comparative benchmark execution."""
        runner = BenchmarkRunner(
            output_dir=str(tmp_path),
            stage_duration_secs=2,
            mode="simulation"
        )
        results = runner.run_comparative_benchmark()
        assert "hpa_csv" in results
        assert "agentic_csv" in results
        assert os.path.exists(results["hpa_csv"])
        assert os.path.exists(results["agentic_csv"])
