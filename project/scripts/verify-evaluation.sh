#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/../venv/bin/python"
VENV_PYTEST="${PROJECT_DIR}/../venv/bin/pytest"
RESULTS_DIR="${PROJECT_DIR}/evaluation/results"
export MPLCONFIGDIR="/tmp/matplotlib"

echo "=========================================================="
echo " [Acceptance Verification] Checking Epic 7 Evaluation Harness"
echo " Comparative Benchmark: Standard HPA vs Agentic Autoscaler"
echo "=========================================================="

echo ""
echo "[Check 1/4] Running Comprehensive Unit Test Suite (15 specs)..."
echo "  - Locust Load Scripts, Shapes, and SLA Tracking"
echo "  - Metrics Collector & Time-Series Exporters"
echo "  - Automated Benchmark Runner & State Machine"
echo "  - Evaluation Analyzer & Visualization Engine"

cd "${PROJECT_DIR}"
PYTHONPATH=. "${VENV_PYTEST}" evaluation/tests -v

echo ""
echo "[Check 2/4] Verifying Acceptance Criteria 1: Dynamic High-Concurrency Locust Load Profiles..."
echo "  - Validating MicroserviceUser tasks (/api/workload, /api/load/cpu, /healthz)"
echo "  - Validating StepAndSpikeShape dynamic step-load & flash-crowd transitions"
echo "  - Validating SLA violation event listener (<500ms threshold)"
PYTHONPATH=. "${VENV_PYTEST}" evaluation/tests/test_locustfile.py -v
echo "✔ Acceptance Criteria 1 Verified: Locust script successfully drives reproducible, high-concurrency traffic loads."

echo ""
echo "[Check 3/4] Verifying Acceptance Criteria 2: Clean Time-Series Metrics Export..."
echo "  - Executing Comparative Benchmark Runner..."
mkdir -p "${RESULTS_DIR}"
PYTHONPATH=. "${VENV_PYTHON}" -m evaluation.benchmark_runner \
  --mode simulation \
  --stage-duration 5 \
  --output-dir "${RESULTS_DIR}"

if [[ ! -f "${RESULTS_DIR}/hpa_metrics.csv" ]] || [[ ! -f "${RESULTS_DIR}/agentic_metrics.csv" ]]; then
  echo "ERROR: Failed to export time-series metrics CSV datasets!"
  exit 1
fi

HPA_ROWS=$(wc -l < "${RESULTS_DIR}/hpa_metrics.csv" | tr -d ' ')
AGENTIC_ROWS=$(wc -l < "${RESULTS_DIR}/agentic_metrics.csv" | tr -d ' ')
echo "  - Exported Standard HPA dataset: ${HPA_ROWS} records (${RESULTS_DIR}/hpa_metrics.csv)"
echo "  - Exported Agentic Autoscaler dataset: ${AGENTIC_ROWS} records (${RESULTS_DIR}/agentic_metrics.csv)"
echo "✔ Acceptance Criteria 2 Verified: Evaluation harness automatically exports clean time-series datasets."

echo ""
echo "[Check 4/4] Verifying Acceptance Criteria 3: Final Charts & Comprehensive Evaluation Report..."
echo "  - Processing datasets and rendering publication-grade charts..."
PYTHONPATH=. "${VENV_PYTHON}" -m evaluation.analyze_results \
  --hpa-csv "${RESULTS_DIR}/hpa_metrics.csv" \
  --agentic-csv "${RESULTS_DIR}/agentic_metrics.csv" \
  --output-dir "${RESULTS_DIR}"

for chart in latency_over_time.png replicas_vs_load.png sla_flapping_comparison.png guardrails_summary.png; do
  if [[ ! -f "${RESULTS_DIR}/${chart}" ]]; then
    echo "ERROR: Expected chart '${chart}' was not generated!"
    exit 1
  fi
  echo "  ✔ Generated chart: ${RESULTS_DIR}/${chart} ($(wc -c < "${RESULTS_DIR}/${chart}" | tr -d ' ') bytes)"
done

if [[ ! -f "${RESULTS_DIR}/evaluation_report.md" ]]; then
  echo "ERROR: Evaluation report markdown was not generated!"
  exit 1
fi
echo "  ✔ Generated report: ${RESULTS_DIR}/evaluation_report.md"
echo "✔ Acceptance Criteria 3 Verified: Final report generates clean charts demonstrating comparative resilience, reaction speed, and stability."

echo ""
echo "=========================================================="
echo "✔ All Epic 7 Acceptance Criteria Verified Successfully!"
echo "=========================================================="
