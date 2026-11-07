#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "=========================================================="
echo " [Acceptance Verification] Checking Epic 3 Reasoner Layer"
echo " Reasoner URL: ${BASE_URL}"
echo "=========================================================="

echo ""
echo "[Check 1/3] Verifying Asynchronous Service Health & Readiness Probes..."
HEALTH_RESP=$(curl -s -f "${BASE_URL}/healthz" || echo "")
READY_RESP=$(curl -s -f "${BASE_URL}/readyz" || echo "")

if [ -n "${HEALTH_RESP}" ] && [ -n "${READY_RESP}" ]; then
  echo "✔ Health check passed: ${HEALTH_RESP}"
  echo "✔ Readiness probe passed: ${READY_RESP}"
else
  echo "✖ Health check failed. Ensure the Reasoner service is running at ${BASE_URL}"
  echo "  (Run 'make reasoner-run' or 'make reasoner-deploy')"
  exit 1
fi

echo ""
echo "[Check 2/3] Verifying Strict Pydantic Schema Validation (HTTP 422 on Malformed Payload)..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/evaluate-scaling" \
  -H "Content-Type: application/json" \
  -d '{"namespace": "workload-system", "workload_name": "target-workload", "max_replicas": 1, "min_replicas": 5}')

if [ "${HTTP_CODE}" -eq 422 ]; then
  echo "✔ Malformed payload (max_replicas < min_replicas) correctly rejected with HTTP 422 Unprocessable Entity."
else
  echo "✖ Expected HTTP 422 on malformed input, received HTTP ${HTTP_CODE}"
  exit 1
fi

echo ""
echo "[Check 3/3] Verifying Asynchronous /evaluate-scaling Decision Generation..."
SAMPLE_PAYLOAD='{
  "namespace": "workload-system",
  "workload_name": "target-workload",
  "current_replicas": 2,
  "min_replicas": 1,
  "max_replicas": 5,
  "cpu_utilization_percent": 92.5,
  "memory_utilization_percent": 68.0,
  "http_requests_per_second": 320.0,
  "http_p99_latency_ms": 285.0,
  "error_rate_percent": 0.0
}'

REASONING_RESPONSE=$(curl -s -X POST "${BASE_URL}/evaluate-scaling" \
  -H "Content-Type: application/json" \
  -d "${SAMPLE_PAYLOAD}")

TARGET_REPLICAS=$(echo "${REASONING_RESPONSE}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('target_replicas', ''))")
ACTION=$(echo "${REASONING_RESPONSE}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('action', ''))")
REASONING=$(echo "${REASONING_RESPONSE}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('reasoning', ''))")
IS_FALLBACK=$(echo "${REASONING_RESPONSE}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(str(data.get('is_fallback', '')).lower())")
MODEL_USED=$(echo "${REASONING_RESPONSE}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('model_used', 'unknown'))")

if [ -n "${TARGET_REPLICAS}" ] && [ -n "${ACTION}" ] && [ -n "${REASONING}" ]; then
  echo "✔ Reasoned scaling recommendation successfully generated:"
  if [ "${IS_FALLBACK}" == "false" ]; then
    echo "   - Execution Mode: [LLM CALLED SUCCESSFULLY] (Model: ${MODEL_USED})"
  else
    echo "   - Execution Mode: [DEFAULTED TO HARDCODED VALUES] (Model: ${MODEL_USED})"
  fi
  echo "   - Action: ${ACTION}"
  echo "   - Target Replicas: ${TARGET_REPLICAS} (current: 2)"
  echo "   - Reasoning: ${REASONING}"
else
  echo "✖ Malformed recommendation output: ${REASONING_RESPONSE}"
  exit 1
fi

echo ""
echo "=========================================================="
echo "✔ All Epic 3 Acceptance Criteria Verified Successfully!"
echo "=========================================================="
