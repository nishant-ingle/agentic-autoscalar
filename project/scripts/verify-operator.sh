#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-workload-system}"
AUTOSCALER_NAME="target-workload-autoscaler"
DEPLOYMENT_NAME="target-workload"

echo "=========================================================="
echo " [Acceptance Verification] Checking Epic 2 Operator"
echo " Namespace: ${NAMESPACE}"
echo "=========================================================="

echo ""
echo "[Check 1/4] Verifying AgenticAutoscaler CRD Registration..."
if kubectl get crd agenticautoscalers.autoscaling.autoscale.ai > /dev/null 2>&1; then
  echo "✔ CRD 'agenticautoscalers.autoscaling.autoscale.ai' is registered in cluster."
else
  echo "✖ CRD is not registered. Run 'make operator-install' first."
  exit 1
fi

echo ""
echo "[Check 2/4] Verifying AgenticAutoscaler Custom Resource..."
if kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" > /dev/null 2>&1; then
  echo "✔ Custom resource '${AUTOSCALER_NAME}' exists."
  kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" -o wide
else
  echo "✖ Custom resource '${AUTOSCALER_NAME}' not found. Run 'make operator-apply-sample' first."
  exit 1
fi

echo ""
echo "[Check 3/4] Verifying Controller Reconciliation Status & Conditions..."
TARGET_FOUND=$(kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.conditions[?(@.type=="TargetFound")].status}' 2>/dev/null || echo "")
SCALING_ACTIVE=$(kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.conditions[?(@.type=="ScalingActive")].status}' 2>/dev/null || echo "")
CURRENT_REPLICAS=$(kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.currentReplicas}' 2>/dev/null || echo "")

if [ "${TARGET_FOUND}" == "True" ] && [ "${SCALING_ACTIVE}" == "True" ]; then
  echo "✔ Reconciler conditions verified: TargetFound=True, ScalingActive=True."
  echo "✔ Observed replicas: ${CURRENT_REPLICAS}"
else
  echo "✖ Controller has not reconciled or conditions are not True yet."
  echo "  (Make sure the controller is running: 'make operator-run' or 'make operator-deploy')"
  echo "  TargetFound: '${TARGET_FOUND}', ScalingActive: '${SCALING_ACTIVE}'"
  exit 1
fi

echo ""
echo "[Check 4/4] Dynamic Watch Verification (Scale 2 -> 3 -> 2)..."
INITIAL_REPLICAS=$(kubectl get deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}')
echo "Current deployment replicas: ${INITIAL_REPLICAS}"

echo "Scaling deployment to 3 replicas to test dynamic event watching..."
kubectl scale deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --replicas=3 > /dev/null

echo "Waiting for AgenticAutoscaler to detect and update status (up to 20s)..."
SUCCESS=false
for i in {1..20}; do
  OBSERVED=$(kubectl get aa "${AUTOSCALER_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.desiredReplicas}' 2>/dev/null || echo "")
  if [ "${OBSERVED}" == "3" ]; then
    SUCCESS=true
    echo "✔ Controller dynamically detected scale event: desiredReplicas updated to 3."
    break
  fi
  sleep 1
done

echo "Resetting deployment back to ${INITIAL_REPLICAS} replicas..."
kubectl scale deployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --replicas="${INITIAL_REPLICAS}" > /dev/null

if [ "${SUCCESS}" != "true" ]; then
  echo "✖ Dynamic watch timeout: Controller did not reflect scale change in time."
  exit 1
fi

echo ""
echo "=========================================================="
echo "✔ All Epic 2 Acceptance Criteria Verified Successfully!"
echo "=========================================================="
