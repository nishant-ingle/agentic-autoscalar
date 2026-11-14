# Epic 7: Comparative Evaluation Harness (Locust & HPA Benchmarking)

## Overview

Epic 7 implements an empirical, publication-standard benchmarking framework that subjects the Kubernetes cluster to reproducible, high-concurrency traffic profiles under two distinct control regimes:
1. **Regime A: Standard Kubernetes Horizontal Pod Autoscaler (HPA)**
2. **Regime B: Agentic Autoscaler (FastAPI Reasoner + MCP Server + pgvector RAG + Go Safety Guardrails)**

---

## Architecture & Components

```
project/evaluation/
├── locustfile.py            # High-concurrency Locust load generator & dynamic shapes
├── metrics_collector.py     # Real-time multi-source telemetry collector (Prometheus, K8s, Locust)
├── benchmark_runner.py      # Automated comparative benchmark runner & state reset machine
├── analyze_results.py       # Comparative analysis engine & publication-grade chart generator
├── pytest.ini               # Test configuration
├── requirements.txt         # Python dependencies (locust, matplotlib, pandas)
├── results/                 # Exported datasets, charts, and final evaluation report
│   ├── hpa_metrics.csv
│   ├── agentic_metrics.csv
│   ├── benchmark_summary.json
│   ├── latency_over_time.png
│   ├── replicas_vs_load.png
│   ├── sla_flapping_comparison.png
│   ├── guardrails_summary.png
│   └── evaluation_report.md
└── tests/                   # 15 automated unit & integration specs
    ├── conftest.py
    ├── test_locustfile.py
    ├── test_metrics_collector.py
    ├── test_benchmark_runner.py
    └── test_analyze_results.py
```

---

## Traffic Shaping Profiles (`locustfile.py`)

The dynamic load shape `StepAndSpikeShape` models real-world traffic dynamics across 7 continuous phases:
1. **Baseline Warmup**: Steady 10 concurrent users.
2. **Step Load Ramp 1**: 30 concurrent users.
3. **Step Load Ramp 2**: 60 concurrent users.
4. **Sudden Flash-Crowd Surge**: Instantaneous spike to 150 concurrent users (spawn rate 50/s) to simulate breaking viral traffic or cascading upstream failovers.
5. **Post-Spike Sustain**: 100 concurrent users.
6. **Sharp Step-Down**: Rapid drop to 20 users to test scale-down reaction and anti-flapping guardrail hysteresis.
7. **Idle Baseline**: 5 users.

Custom event listeners in Locust continuously track:
- Request latencies (P50, P90, P95, P99, Max).
- SLA violations (requests exceeding the 500ms latency ceiling).
- Request throughput and error rates.

---

## Quickstart Commands

### 1. Run Automated Unit & Integration Tests (15 specs)
```bash
make evaluation-test
```

### 2. Run Comparative Evaluation Benchmark
```bash
# Automated run across both regimes (auto-detects live cluster vs simulation):
make evaluation-run

# Custom arguments:
PYTHONPATH=. ../venv/bin/python -m evaluation.benchmark_runner --mode auto --stage-duration 25 --output-dir evaluation/results
```

### 3. Generate Charts and Report from Datasets
```bash
make evaluation-analyze
```

### 4. Run Full End-to-End Acceptance Verification
```bash
make verify-evaluation
```

---

## Acceptance Criteria Status

| Acceptance Criteria | Status | Verification Detail |
| :--- | :--- | :--- |
| **AC-1**: Locust script successfully drives reproducible, high-concurrency traffic loads against target endpoints. | **PASSED** | Verified via `test_locustfile.py` and Locust CLI runner across `/api/workload`, `/api/load/cpu`, and `/healthz`. |
| **AC-2**: Evaluation harness automatically exports time-series metrics into clean comparison datasets. | **PASSED** | Verified via `test_metrics_collector.py` and `benchmark_runner.py` exporting `hpa_metrics.csv` and `agentic_metrics.csv`. |
| **AC-3**: Final report generates clean charts demonstrating comparative resilience, response time, and stability of Agentic Autoscaler against Standard HPA. | **PASSED** | Verified via `analyze_results.py` generating 4 high-res charts and `evaluation_report.md`. |
