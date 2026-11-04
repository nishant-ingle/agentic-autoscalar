#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo " [Epic 1] Deploying Target Microservice & Prometheus Stack"
echo " Target Environment: Single-Node Docker Desktop Kubernetes"
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "[Step 1/5] Checking Kubernetes context..."
CURRENT_CONTEXT=$(kubectl config current-context || echo "none")
echo "Current kubectl context: ${CURRENT_CONTEXT}"

if [[ "${CURRENT_CONTEXT}" != *"docker-desktop"* ]]; then
  echo "WARNING: Your kubectl context is '${CURRENT_CONTEXT}', not 'docker-desktop'."
  echo "If you intend to use Docker Desktop, run: kubectl config use-context docker-desktop"
fi

echo ""
echo "[Step 2/5] Building Target Go/Gin Microservice Container Image..."
cd "${ROOT_DIR}/target-service"
docker build -t target-service:latest .
echo "Container image 'target-service:latest' built and available in local Docker engine."

echo ""
echo "[Step 3/5] Deploying kube-prometheus-stack via Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
helm repo update

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values "${ROOT_DIR}/monitoring/kube-prometheus-values.yaml" \
  --wait --timeout 5m

echo ""
echo "[Step 4/5] Deploying Target Microservice Manifests..."
kubectl apply -f "${ROOT_DIR}/k8s/namespace.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/deployment.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/service.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/servicemonitor.yaml"

echo ""
echo "[Step 5/5] Provisioning Grafana Dashboard..."
kubectl apply -f "${ROOT_DIR}/monitoring/grafana-dashboard-configmap.yaml"

echo ""
echo "Waiting for target-workload pods to become Ready..."
kubectl rollout status deployment/target-workload -n workload-system --timeout=120s

echo ""
echo "=========================================================="
echo " Epic 1 Deployment Complete!"
echo "=========================================================="
echo "To access dashboards and services, run:"
echo "  make port-forward"
echo ""
echo "  - Target Microservice: http://localhost:8080"
echo "  - Prometheus Web UI:   http://localhost:9090"
echo "  - Grafana Dashboard:   http://localhost:3000 (admin / prom-operator)"
echo "=========================================================="
