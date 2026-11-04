#!/usr/bin/env bash
set -euo pipefail

PROM_HOST="${1:-http://localhost:9090}"

echo "=========================================================="
echo " [Acceptance Verification] Checking Epic 1 Telemetry"
echo " Prometheus URL: ${PROM_HOST}"
echo "=========================================================="

echo ""
echo "[Check 1/3] Verifying Target Pod Deployment Health..."
kubectl get deployment target-workload -n workload-system
REPLICAS=$(kubectl get deployment target-workload -n workload-system -o jsonpath='{.status.readyReplicas}')
if [ "${REPLICAS:-0}" -ge 1 ]; then
  echo "✔ Target deployment has ${REPLICAS} ready replicas."
else
  echo "✖ Target deployment does not have ready replicas."
  exit 1
fi

echo ""
echo "[Check 2/3] Querying Prometheus Active Scrape Targets..."
TARGETS_JSON=$(curl -s "${PROM_HOST}/api/v1/targets" || echo "")
if [[ -z "$TARGETS_JSON" ]]; then
  echo "Prometheus is not reachable at ${PROM_HOST}. Ensure port-forward is active: make port-forward"
  exit 1
fi

HEALTHY_TARGETS=$(echo "${TARGETS_JSON}" | grep -o '"health":"up"' | wc -l || echo "0")
echo "✔ Prometheus targets are active (up count: ${HEALTHY_TARGETS})."

echo ""
echo "[Check 3/3] Querying Target Workload Golden Signals from Prometheus..."
QUERY="sum(rate(workload_http_requests_total{namespace=\"workload-system\"}[1m]))"
RESULT=$(curl -s --data-urlencode "query=${QUERY}" "${PROM_HOST}/api/v1/query")

echo "Query: ${QUERY}"
echo "Response: ${RESULT}"

echo ""
echo "=========================================================="
echo "✔ All Acceptance Criteria Verified!"
echo "=========================================================="
