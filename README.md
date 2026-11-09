# Agentic Kubernetes Autoscaler & Evaluation Framework

[![Kubernetes](https://img.shields.io/badge/Kubernetes-v1.28%2B-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Go](https://img.shields.io/badge/Go-1.22-00ADD8?logo=go&logoColor=white)](https://golang.org/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20AI-FF6F00)](https://langchain-ai.github.io/langgraph/)
[![pgvector](https://img.shields.io/badge/pgvector-PostgreSQL%20RAG-336791?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)

A closed-loop, agent-driven Kubernetes autoscaling framework and empirical evaluation harness. 

This project bridges **cloud-native systems engineering** (custom Go/Kubebuilder operator, deterministic safety invariants) with **agentic AI architectures** (LangGraph, Model Context Protocol, and `pgvector` operational memory) to overcome the structural limitations of standard reactive autoscaling (Kubernetes HPA).

> **Project Status:** Active Work-in-Progress (Ongoing). Currently benchmarking and comparing performance characteristics against standard Kubernetes Horizontal Pod Autoscaler (HPA) using distributed Locust load testing.

---

## The Problem: Reactive HPA vs. Proactive Reasoning

Standard Kubernetes **Horizontal Pod Autoscaler (HPA)** scales pods based on trailing metric thresholds (e.g., average CPU or memory utilization over window periods):
* **Delayed Reaction:** Metric collection and moving averages lag behind traffic bursts, leading to high P99 latency spikes and SLA breaches during sudden flash crowds.
* **Oscillation & Pod Flapping:** Rapid metric fluctuation can cause churn (aggressive scale-up followed immediately by premature scale-down).
* **Zero Semantic Context:** HPA operates purely on scalar thresholds without insight into HTTP error codes, traffic distribution patterns, or historical organizational runbooks.

### The Solution: Agent-Driven Autoscaling with Safety Invariants

```
                                  +--------------------------------------------------------+
                                  |                 Reasoning & Context                    |
                                  |                                                        |
                                  |   +-------------------+      +---------------------+   |
                                  |   | pgvector Runbooks |      | LangGraph Reasoner  |   |
                                  |   | (SRE Knowledge)   |----->| (FastAPI / LLM)     |   |
                                  |   +-------------------+      +----------+----------+   |
                                  +-----------------------------------------|--------------+
                                                                            | MCP Protocol
                                                                            v
+------------------+         +----------------------+            +---------------------+
| Prometheus Stack |<--------| Target Microservice  |            |  MCP Server Tools   |
| (Metrics Scrape) |         | (Go/Gin App Pods)    |            | (Cluster Telemetry) |
+--------+---------+         +----------+-----------+            +---------------------+
         |                              ^
         | Query Metrics                | Scale Subresource Patch
         v                              |
+---------------------------------------+--------------------------------------------------+
| Go Kubernetes Operator (Kubebuilder & client-go)                                         |
|                                                                                          |
|  +--------------------+      +----------------------------------+      +---------------+ |
|  | Reconciliation     |----->| Deterministic Guardrail Pipeline |----->| Deployment    | |
|  | Loop & CRD Watcher |      | (Clamp, Anti-Flap Hysteresis,    |      | Scale Manager | |
|  +--------------------+      |  Temporal Limits, HPA Fallback)  |      +---------------+ |
|                              +----------------------------------+                        |
+------------------------------------------------------------------------------------------+
```

1. **Intelligent Reasoning:** Telemetry and incident history are interpreted by a LangGraph agent via the **Model Context Protocol (MCP)** and a **`pgvector` RAG** memory store.
2. **Deterministic Safety Barrier:** All agent recommendations are intercepted by a high-assurance **Go Guardrail Engine** (`client-go`) that clamps replica bounds, enforces anti-flapping hysteresis cooldowns, and falls back to reactive HPA if external services fail.

---

## Architectural Epics

| Epic | Component | Tech Stack | Status |
| :--- | :--- | :--- | :--- |
| **Epic 1** | **Target Workload & Telemetry Baseline** | Go 1.22, Gin, Prometheus Operator, Grafana | Completed |
| **Epic 2** | **Control Plane Kubernetes Operator** | Go, Kubebuilder v4, `client-go`, Custom CRD | Completed |
| **Epic 3** | **AI Reasoning Microservice** | Python 3.11, FastAPI, LangGraph, LangChain, Pydantic | Completed |
| **Epic 4** | **Model Context Protocol (MCP) Server** | Python MCP SDK, Prometheus API, JSON-RPC | Completed |
| **Epic 5** | **Operational RAG Memory Pipeline** | PostgreSQL, `pgvector`, Embedding Retriever | Completed |
| **Epic 6** | **Deterministic Guardrail Pipeline** | Go, Controller-Runtime, Temporal Hysteresis | Completed |
| **Epic 7** | **Comparative Evaluation Harness** | Locust, Python, Prometheus Exporter | In Progress |

---

## Component Deep Dive

### 1. Control Plane Operator (`project/operator`)
Built with **Kubebuilder** and **`client-go`**, the operator watches a custom resource definition: `AgenticAutoscaler` (`autoscale.ai/v1alpha1`).
- **Safety Guardrails:** Intercepts external AI recommendations and checks them against strict invariants:
  - **Boundary Clamping:** Rigid enforcement of `minReplicas` and `maxReplicas`.
  - **Scale-Down Hysteresis:** Configurable cooldown window (default: 600s) preventing premature scale-down following a scale-up action.
  - **Temporal Rate Limiting:** Enforces minimum duration intervals between consecutive scale operations to eliminate flapping.
  - **Automatic HPA Fallback:** If the reasoning service times out (>3s) or produces schema validation errors, the controller automatically falls back to deterministic reactive CPU-based scaling.

### 2. AI Reasoner Service (`project/reasoner`)
An asynchronous **FastAPI** service powered by a **LangGraph** state machine.
- Consumes real-time cluster metrics (CPU/memory saturation, request rates, HTTP 5xx error spikes).
- Uses tool-calling over MCP to query prometheus range queries and logs dynamically.
- Returns structured scaling plans conforming to strict Pydantic schemas (`target_replicas`, `action`, `reasoning`).

### 3. Model Context Protocol Server (`project/mcp-server`)
Implements Anthropic's **Model Context Protocol (MCP)** to expose standardized, read-only operational tools:
- `get_cluster_metrics`: Current CPU/memory utilization and replica states.
- `query_prometheus_range`: Time-series Prometheus queries.
- `fetch_recent_logs`: Scrapes stdout logs for active error signatures and stack traces.
- Enforces strict read-only execution sandboxing at the protocol boundary.

### 4. Operational RAG Memory (`project/rag`)
Uses **PostgreSQL** with the **`pgvector`** extension to supply operational grounding:
- Indexes synthetic post-mortems, incident runbooks, and historical anomaly patterns.
- Performs cosine-similarity retrieval on incident signatures to guide the reasoning engine during anomalous load spikes.

### 5. Target Microservice (`project/target-service`)
A production-grade Go/Gin HTTP service deployed in the `workload-system` namespace:
- Exposes Prometheus telemetry at `/metrics`.
- Exposes synthetic stress endpoints:
  - `/api/load/cpu`: Deterministic CPU burn (`duration_ms`, `concurrency`).
  - `/api/load/memory/allocate` & `/release`: Heap footprint manipulation.
  - `/api/workload`: Configurable HTTP latency simulation.

---

## Repository Structure

```text
.
├── Makefile                     # Root facade delegating to project lifecycle tasks
├── plan.txt                     # Detailed engineering backlog & Jira-style user stories
└── project/
    ├── Makefile                 # Unified developer lifecycle management
    ├── k8s/                     # Kubernetes manifests (namespaces, services, monitors)
    ├── monitoring/              # Grafana dashboards & Helm values for Prometheus Operator
    ├── target-service/          # Go/Gin microservice instrumented for metrics
    ├── operator/                # Go Kubebuilder controller & deterministic guardrails
    ├── reasoner/                # FastAPI / LangGraph telemetry reasoning service
    ├── mcp-server/              # Model Context Protocol server exposing K8s/Prometheus tools
    ├── rag/                     # pgvector RAG memory & SRE runbook seed scripts
    └── scripts/                 # Automated deployment, port-forwarding, and verification scripts
```

---

## Prerequisites

- **Go:** `v1.22+`
- **Python:** `3.11+`
- **Docker & Kubernetes:** Docker Desktop (single-node Kubernetes enabled), K3D, or Minikube
- **Tools:** `kubectl`, `helm`, `kubebuilder`

---

## Quickstart & Local Setup

### 1. Deploy Infrastructure & Target Workload
Deploys Prometheus Operator, Grafana, and the Go/Gin target microservice:
```bash
make deploy
```
Open local tunnels to Grafana (port 3000), Prometheus (port 9090), and Target Service (port 8080):
```bash
make port-forward
```

### 2. Run and Deploy the Kubernetes Operator
Install CRDs and run the Go controller:
```bash
# Test and deploy CRD + Operator
make operator-test
make operator-deploy

# Apply sample AgenticAutoscaler custom resource
make operator-apply-sample

# Stream operator logs
make operator-logs
```

### 3. Start the AI Reasoner & MCP Server
```bash
# MCP Server (Port 8001)
make mcp-test
make mcp-run

# Reasoner Service (Port 8000)
make reasoner-test
make reasoner-run
```

### 4. Initialize Operational Memory (pgvector RAG)
```bash
# Seed synthetic SRE incident runbooks and embeddings
make rag-seed

# Verify stored vector embeddings
make rag-verify
```

### 5. Deterministic Guardrail Verification
Execute the automated test suite verifying anti-flapping hysteresis, replica bounds, and fallback triggers:
```bash
make guardrails-test
make verify-guardrails
```

---

## Sample Custom Resource (`AgenticAutoscaler`)

```yaml
apiVersion: autoscale.ai/v1alpha1
kind: AgenticAutoscaler
metadata:
  name: target-workload-autoscaler
  namespace: workload-system
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: target-workload
  minReplicas: 2
  maxReplicas: 10
  pollingIntervalSeconds: 15
  scaleDownHysteresisSeconds: 600   # 10-minute anti-flapping window
  targetCPUUtilization: 70          # Fallback threshold if AI is unreachable
  reasonerURL: "http://reasoner-service.workload-system.svc.cluster.local:8000/evaluate"
  prometheusURL: "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
```

Inspect running status with rich printer columns:
```bash
kubectl get agenticautoscalers -n workload-system
```
```text
NAME                         TARGET            MIN   MAX   CURRENT   DESIRED   ACTION     FALLBACK   AGE
target-workload-autoscaler   target-workload   2     10    2         4         SCALE_UP   false      5m
```

---

## Ongoing Evaluation: Benchmarking Against HPA

The comparative evaluation framework (**Epic 7**) subjects the cluster to identical traffic loads generated via **Locust** across two separate control regimes:
1. **Control Group:** Native Kubernetes HPA (reactive CPU threshold scaling).
2. **Experimental Group:** Agentic Autoscaler (predictive reasoning + MCP telemetry + pgvector SRE runbooks + Go guardrails).

### Evaluated Metrics:
* **P99 & P95 Request Latency:** Tracking response degradation during sudden step loads and flash crowds.
* **Scaling Reaction Time:** Elapsed time from traffic onset to healthy pod readiness.
* **Pod Flapping Frequency:** Rate of oscillation between scale-up and scale-down decisions under oscillating loads.
* **SLA Violations:** Total count of requests exceeding target response thresholds (e.g., >500ms or 5xx status codes).
* **Resource Overhead & Cost:** Total pod core-hours utilized across equivalent workload benchmarks.

---

## License

This project is licensed under the GPLv3 License.
