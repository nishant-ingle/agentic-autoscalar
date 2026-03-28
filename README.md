# Agentic Kubernetes Auto-Scaler

## Overview
Traditional Kubernetes Horizontal Pod Autoscalers (HPA) are inherently reactive, scaling infrastructure only *after* a spike in resource utilization has occurred. This latency can result in dropped requests or degraded performance during sudden traffic surges. 

The **Agentic Kubernetes Auto-Scaler (PKA)** is a polyglot distributed system that proactively scales Kubernetes workloads based on time-series forecasting. By decoupling the infrastructure orchestration (Go) from the machine learning inference (Python), PKA ensures highly available, zero-latency scaling.

## High-Level Architecture
PKA utilizes a two-service architecture to enforce a strict separation of concerns:

1. **PKA-Controller (Golang):** A custom Kubernetes Operator built using `kubebuilder`. It continuously monitors cluster state, queries Prometheus for live metrics, and executes scaling operations via the Kubernetes API.
2. **PKA-Inference Engine (Python):** A highly concurrent FastAPI/PyTorch service that ingests time-series metrics from the Go controller, runs an autoregressive forecasting model, and returns a predictive scaling recommendation.

### System Data Flow
1. User applies a `AgenticAutoscaler` Custom Resource (CRD) to a target Deployment.
2. The **Go Controller** reconciles the CRD, fetching the last 15 minutes of CPU/Memory metrics from **Prometheus**.
3. The Go Controller sends a structured metric payload to the **Python Inference API**.
4. The Python service runs the forecasting model, calculates the required replicas for the next time horizon (e.g., T+5 minutes), and returns the recommendation.
5. The Go Controller patches the target Deployment to the predicted replica count.

---

## 📜 Custom Resource Definition (CRD)
To manage the autoscaler, users define a `AgenticAutoscaler` custom resource. This integrates natively with `kubectl`.

```yaml
apiVersion: scaling.pka.io/v1alpha1
kind: AgenticAutoscaler
metadata:
  name: frontend-predictive-scaler
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: frontend-webapp
  minReplicas: 3
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  forecastWindow: 5m # Predict 5 minutes into the future
```

---

## 🔌 API Specification: Controller ↔ Inference Engine

The communication between the Go Controller and the Python Inference Engine occurs over a RESTful API (can be upgraded to gRPC for massive scale). 

### `POST /api/v1/predict`
Calculates the predicted resource utilization and recommended replica count based on historical telemetry.

#### **Request Body (JSON)**
Sent by the Go Controller. Contains the necessary time-series data fetched from Prometheus.
```json
{
  "target_service": "frontend-webapp",
  "namespace": "production",
  "current_replicas": 12,
  "target_utilization_percent": 70,
  "telemetry": [
    {
      "timestamp": "2026-03-28T10:45:00Z",
      "cpu_usage_millicores": 2500,
      "memory_usage_mb": 4096
    },
    {
      "timestamp": "2026-03-28T10:46:00Z",
      "cpu_usage_millicores": 2800,
      "memory_usage_mb": 4120
    }
    // ... continues for the configured lookback window
  ]
}
```

#### **Response Body (JSON)**
Returned by the Python Inference Engine.
```json
{
  "target_service": "frontend-webapp",
  "forecast_timestamp": "2026-03-28T10:51:00Z",
  "predicted_cpu_millicores": 8500,
  "recommended_replicas": 18,
  "confidence_score": 0.92,
  "metadata": {
    "model_version": "v1.2.0-pytorch",
    "inference_latency_ms": 45
  }
}
```

---

## 🛡 Fault Tolerance & Reliability (SDE-2 Focus)
Building for massive scale means expecting failure. PKA implements the following safeguards:

* **Graceful Degradation (Fallback Mode):** If the Python Inference Engine goes down or returns a 5xx error, the Go Controller automatically falls back to standard reactive HPA logic. The system never stops scaling.
* **Circuit Breaking:** The Go controller uses a circuit breaker pattern when communicating with the Python API. If the inference engine latency spikes >500ms, the circuit opens to prevent controller thread exhaustion.
* **Confidence Thresholds:** If the ML model returns a prediction with a `confidence_score < 0.70`, the Controller ignores the prediction and maintains the current replica count to prevent chaotic scaling (thrashing).
* **Cool-down Periods:** To prevent the "yo-yo" effect of rapid scaling up and down, the controller enforces a configurable `scaleDownStabilizationWindow` (e.g., 5 minutes) before terminating pods.

---

## 🛠 Tech Stack
* **Infrastructure Operator:** Golang, `client-go`, `kubebuilder`, Kubernetes API.
* **Inference Engine:** Python 3.11, FastAPI, PyTorch (or Statsmodels/Prophet for statistical forecasting), Pandas.
* **Observability:** Prometheus (Metrics), Grafana (Dashboards).
* **Deployment:** Docker, Helm, Minikube / K3D for local testing.

