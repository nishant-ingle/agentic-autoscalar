# Agentic Autoscaler: Epic 1 - Infrastructure Baseline & Target Telemetry

This module delivers **Epic 1 (`AUTOSCALE-101`)** of the Agent-Driven Kubernetes Autoscaler & Evaluation Framework. It establishes a production-grade target microservice instrumented with Prometheus, packaged for deployment on **Docker Desktop Kubernetes (single-node)**.

---

## Architecture Overview

```
                         +-----------------------------------------------+
                         |          Docker Desktop Single-Node           |
                         |                                               |
+-------------------+    |   +-------------------+                       |
|   Locust / Test   |------->|   Target Service  |                       |
| Traffic Generator |    |   |  (Go/Gin Pods x2) |                       |
+-------------------+    |   +---------+---------+                       |
                         |             | :8080/metrics                   |
                         |             v                                 |
                         |   +-------------------+                       |
                         |   |  ServiceMonitor   |                       |
                         |   |   (15s scrape)    |                       |
                         |   +---------+---------+                       |
                         |             v                                 |
                         |   +-------------------+       +-----------+   |
                         |   |    Prometheus     |------>|  Grafana  |   |
                         |   |     Operator      |       | Dashboard |   |
                         |   +-------------------+       +-----------+   |
                         +-----------------------------------------------+
```

---

## Directory Structure

```text
.
├── Makefile                                # Developer lifecycle automation
├── README.md                               # Setup and architecture documentation
├── k8s/                                    # Target microservice Kubernetes manifests
│   ├── deployment.yaml                     # 2 replicas, 100m CPU / 128Mi requests
│   ├── namespace.yaml                      # 'workload-system' namespace
│   ├── service.yaml                        # ClusterIP with named port 'http-metrics'
│   └── servicemonitor.yaml                 # CRD configured for 15s scrape intervals
├── monitoring/
│   ├── dashboards/
│   │   └── target-workload-dashboard.json  # Grafana dashboard definition
│   ├── grafana-dashboard-configmap.yaml    # ConfigMap for auto-loading into Grafana
│   └── kube-prometheus-values.yaml         # Optimized Helm values for Docker Desktop
├── scripts/
│   ├── deploy-all.sh                       # 1-click end-to-end installation
│   ├── port-forward.sh                     # Port-forward tunnels for all components
│   ├── test-traffic.sh                     # Synthetic load generator script
│   └── verify-metrics.sh                   # Automated acceptance criteria checker
└── target-service/                         # Go/Gin Target Microservice
    ├── Dockerfile                          # Multi-stage minimal Alpine container
    ├── go.mod                              # Go 1.22 dependencies
    ├── cmd/server/main.go                  # Main entrypoint with graceful shutdown
    └── internal/
        ├── handlers/
        │   ├── cpu.go                      # Artificial CPU stress endpoint
        │   ├── health.go                   # /healthz and /readyz probes
        │   ├── memory.go                   # Artificial heap allocation endpoint
        │   ├── workload.go                 # Mixed CPU / I/O latency workload
        │   └── handlers_test.go            # Unit tests
        └── metrics/
            └── prometheus.go               # Gin middleware & Prometheus collectors
```

---

## Endpoints Provided by Target Microservice

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/healthz`, `/livez` | `GET` | Pod liveness probe |
| `/readyz` | `GET` | Pod readiness probe |
| `/metrics` | `GET` | Prometheus telemetry endpoint (`workload_http_*`, Go runtime, cAdvisor) |
| `/api/workload` | `GET`, `POST` | Simulated realistic API traffic (configurable rounds & I/O latency) |
| `/api/load/cpu` | `GET`, `POST` | Deterministic CPU stressor (`?duration_ms=500&concurrency=2`) |
| `/api/load/memory/allocate` | `POST` | Deterministic memory growth (`?mb=50`) |
| `/api/load/memory/release` | `POST` | Releases memory and triggers Go garbage collection |

---

## Quickstart (Single-Node Docker Desktop)

### 1. Pre-requisites
Ensure your Docker Desktop Kubernetes cluster is running:
```bash
kubectl config use-context docker-desktop
helm version
docker --version
```

### 2. Deploy Everything
Execute the one-command deployment script:
```bash
make deploy
```
This script will:
1. Build the local `target-service:latest` image inside your Docker engine (no external registry required).
2. Install `kube-prometheus-stack` via Helm with custom single-node values.
3. Deploy the `workload-system` namespace, Deployment (2 replicas), Service, and `ServiceMonitor`.
4. Register the Grafana Dashboard ConfigMap.

### 3. Open Port Forwards
In a separate terminal, run:
```bash
make port-forward
```
Access the services:
- **Target Microservice**: [http://localhost:8080](http://localhost:8080)
  - Try: `curl http://localhost:8080/healthz`
  - Try: `curl "http://localhost:8080/api/workload?rounds=20000&delay_ms=20"`
  - Try: `curl "http://localhost:8080/api/load/cpu?duration_ms=1000&concurrency=2"`
- **Prometheus UI**: [http://localhost:9090](http://localhost:9090)
  - Check targets: [http://localhost:9090/targets](http://localhost:9090/targets)
- **Grafana UI**: [http://localhost:3000](http://localhost:3000)
  - Credentials: `admin` / `prom-operator`
  - Dashboard: "Target Workload Telemetry (Epic 1)" under folder "Agentic Autoscaler"

### 4. Generate Traffic & Verify Ingestion
Run the test traffic generator for 30 seconds:
```bash
make test-traffic
```

Run the automated verification script:
```bash
make verify
```

---

## Feasible Assumptions Made

1. **Docker Desktop Local Registry**: Since single-node Docker Desktop shares its daemon image store with the Kubernetes runtime, `imagePullPolicy: IfNotPresent` and local tag `target-service:latest` are used, eliminating the requirement for an external container registry or local push-pull loop.
2. **Component Filtering for Docker Desktop**: In `kube-prometheus-values.yaml`, scrape targets for control plane components that bind to localhost (`kubeScheduler`, `kubeControllerManager`, `kubeProxy`, `kubeEtcd`) are disabled to eliminate spurious failing targets on single-node desktop clusters.
3. **Cross-Namespace ServiceMonitor Discovery**: Set `serviceMonitorSelectorNilUsesHelmValues: false` in Prometheus configuration so that the Prometheus Operator automatically discovers `ServiceMonitor` resources in the `workload-system` namespace.
4. **Baseline Resource Quotas**: Container requests are set to `cpu: 100m`, `memory: 128Mi` and limits to `cpu: 500m`, `memory: 512Mi` to guarantee quick and responsive CPU spikes for testing autoscaling in subsequent epics without overloading the developer laptop.
5. **Scrape Frequency**: In accordance with US-101 subtask 4, the scrape interval is set to **15 seconds** (`scrapeInterval: 15s`).
