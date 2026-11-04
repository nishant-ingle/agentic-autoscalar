#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-http://localhost:8080}"
DURATION_SECS="${2:-30}"

echo "=========================================================="
echo " Generating Test Traffic against ${TARGET_HOST}"
echo " Duration: ${DURATION_SECS} seconds"
echo "=========================================================="

END_TIME=$((SECONDS + DURATION_SECS))

echo "Simulating mixed API traffic and intermittent CPU burn spikes..."

while [ $SECONDS -lt $END_TIME ]; do
  # 1. Normal API workload call
  curl -s "${TARGET_HOST}/api/workload?rounds=15000&delay_ms=20" > /dev/null &

  # 2. Occasional CPU burn spike
  if (( SECONDS % 5 == 0 )); then
    curl -s "${TARGET_HOST}/api/load/cpu?duration_ms=600&concurrency=2" > /dev/null &
  fi

  # 3. Health check
  curl -s "${TARGET_HOST}/healthz" > /dev/null &

  sleep 0.2
done

wait
echo ""
echo "Traffic test finished. Metrics have been emitted to Prometheus."
