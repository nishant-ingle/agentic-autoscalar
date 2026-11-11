#!/usr/bin/env bash
# test-traffic.sh — Round-robin traffic generator for agentic-autoscaler
#
# Usage:
#   ./test-traffic.sh [mode] [duration_secs] [namespace]
#
# Modes:
#   service   (default) — send all traffic through the ClusterIP Service (random iptables)
#   roundrobin          — discover pod IPs and rotate requests evenly across each pod
#   skewed              — round-robin base load + heavy CPU burn pinned to the FIRST pod
#
# Examples:
#   ./test-traffic.sh roundrobin 60 workload-system
#   ./test-traffic.sh skewed 120 workload-system
#   ./test-traffic.sh service 30            # original behaviour

set -euo pipefail

MODE="${1:-roundrobin}"
DURATION_SECS="${2:-60}"
NAMESPACE="${3:-workload-system}"
SERVICE_HOST="${SERVICE_HOST:-http://localhost:8080}"
POD_PORT="${POD_PORT:-8080}"
WORKLOAD_LABEL="${WORKLOAD_LABEL:-app=target-workload}"

# Maximum concurrent curl processes — prevents fork-bombing the shell process table.
# Each curl takes ~20-200ms; at 0.2s sleep and MAX_JOBS=10 we cap at ~50 req/s.
MAX_JOBS="${MAX_JOBS:-10}"

# ── Concurrency gate: block until background job count drops below MAX_JOBS ───
throttle() {
  while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do
    sleep 0.05
  done
}

# ── Helper: resolve pod IPs via kubectl ───────────────────────────────────────
get_pod_ips() {
  kubectl get pods -n "${NAMESPACE}" -l "${WORKLOAD_LABEL}" \
    --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.status.podIP}{"\n"}{end}' 2>/dev/null \
    | grep -v '^$'
}

echo "=========================================================="
echo " Mode      : ${MODE}"
echo " Duration  : ${DURATION_SECS}s"
echo " Namespace : ${NAMESPACE}"
echo " Label     : ${WORKLOAD_LABEL}"
echo "=========================================================="

END_TIME=$((SECONDS + DURATION_SECS))

# ── MODE: service (original — through ClusterIP, iptables random) ─────────────
if [[ "${MODE}" == "service" ]]; then
  echo "Routing all traffic through Service (iptables random selection)"
  while [ $SECONDS -lt $END_TIME ]; do
    throttle; curl -s "${SERVICE_HOST}/api/workload?rounds=15000&delay_ms=20" > /dev/null &
    if (( SECONDS % 5 == 0 )); then
      throttle; curl -s "${SERVICE_HOST}/api/load/cpu?duration_ms=600&concurrency=2" > /dev/null &
    fi
    throttle; curl -s "${SERVICE_HOST}/healthz" > /dev/null &
    sleep 0.2
  done
  wait
  echo "Done. Traffic sent through Service."
  exit 0
fi

# ── Resolve pod IPs (required for roundrobin + skewed) ────────────────────────
mapfile -t POD_IPS < <(get_pod_ips)

if [[ ${#POD_IPS[@]} -eq 0 ]]; then
  echo "ERROR: No running pods found for label '${WORKLOAD_LABEL}' in namespace '${NAMESPACE}'."
  echo "       Are you port-forwarding? Use MODE=service instead, or check kubectl access."
  exit 1
fi

echo "Discovered ${#POD_IPS[@]} pod(s):"
for ip in "${POD_IPS[@]}"; do
  echo "  → http://${ip}:${POD_PORT}"
done
echo ""

POD_COUNT=${#POD_IPS[@]}
RR_INDEX=0  # round-robin cursor

# ── MODE: roundrobin — equal load spread across all pods ─────────────────────
if [[ "${MODE}" == "roundrobin" ]]; then
  echo "Starting round-robin traffic (equal load, rotating across all pods)..."
  TICK=0
  while [ $SECONDS -lt $END_TIME ]; do
    TARGET_IP="${POD_IPS[$((RR_INDEX % POD_COUNT))]}"
    TARGET="http://${TARGET_IP}:${POD_PORT}"
    RR_INDEX=$(( RR_INDEX + 1 ))

    # Workload request to current pod in rotation
    throttle; curl -s "${TARGET}/api/workload?rounds=15000&delay_ms=20" > /dev/null &

    # Every 5 ticks: CPU burn to next pod in rotation (keeps load spread)
    if (( TICK % 5 == 0 )); then
      BURN_IP="${POD_IPS[$((RR_INDEX % POD_COUNT))]}"
      throttle; curl -s "http://${BURN_IP}:${POD_PORT}/api/load/cpu?duration_ms=600&concurrency=2" > /dev/null &
      RR_INDEX=$(( RR_INDEX + 1 ))
    fi

    TICK=$(( TICK + 1 ))
    sleep 0.2
  done
  wait
  echo "Done. Requests distributed round-robin across ${POD_COUNT} pod(s)."
  exit 0
fi

# ── MODE: skewed — heavy CPU burn pinned to pod[0], light load round-robins ──
if [[ "${MODE}" == "skewed" ]]; then
  HOT_POD_IP="${POD_IPS[0]}"
  HOT_POD="http://${HOT_POD_IP}:${POD_PORT}"
  echo "Starting skewed traffic:"
  echo "  HOT pod (heavy CPU burn) → http://${HOT_POD_IP}:${POD_PORT}"
  echo "  Remaining pods receive light round-robin baseline load"
  echo ""

  TICK=0
  while [ $SECONDS -lt $END_TIME ]; do
    # Heavy CPU burn pinned to pod[0] on every iteration
    throttle; curl -s "${HOT_POD}/api/load/cpu?duration_ms=800&concurrency=4" > /dev/null &

    # Light workload round-robins across ALL pods (including hot pod)
    TARGET_IP="${POD_IPS[$((RR_INDEX % POD_COUNT))]}"
    throttle; curl -s "http://${TARGET_IP}:${POD_PORT}/api/workload?rounds=10000&delay_ms=10" > /dev/null &
    RR_INDEX=$(( RR_INDEX + 1 ))

    # Healthcheck round-robin
    HC_IP="${POD_IPS[$((RR_INDEX % POD_COUNT))]}"
    throttle; curl -s "http://${HC_IP}:${POD_PORT}/healthz" > /dev/null &
    RR_INDEX=$(( RR_INDEX + 1 ))

    TICK=$(( TICK + 1 ))
    sleep 0.2
  done
  wait
  echo "Done. Skewed load — pod[0] (${HOT_POD_IP}) received concentrated CPU burn."
  exit 0
fi

echo "ERROR: Unknown mode '${MODE}'. Use: service | roundrobin | skewed"
exit 1
