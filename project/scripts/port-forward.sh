#!/usr/bin/env bash
set -e

echo "Starting Port Forwards..."
echo " - Workload Target:  http://localhost:8080"
echo " - Prometheus:       http://localhost:9090"
echo " - Grafana:          http://localhost:3000 (user: admin, pass: prom-operator)"
echo "Press Ctrl+C to stop all tunnels."

kubectl port-forward -n workload-system svc/target-workload 8080:8080 > /dev/null 2>&1 &
PID1=$!
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090 > /dev/null 2>&1 &
PID2=$!
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80 > /dev/null 2>&1 &
PID3=$!

trap "kill $PID1 $PID2 $PID3 2>/dev/null || true; exit" SIGINT SIGTERM EXIT

wait
