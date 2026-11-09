#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPERATOR_DIR="${PROJECT_DIR}/operator"

echo "=========================================================="
echo " [Acceptance Verification] Checking Epic 6 Guardrails"
echo " Deterministic Safety Barrier & Fallback Pipeline"
echo "=========================================================="

echo ""
echo "[Check 1/4] Running Comprehensive Unit Test Suites..."
echo "  - Deterministic Guardrail Pipeline (Boundary, Hysteresis, Cooldown)"
echo "  - AI Reasoner Client & Reactive HPA Fallback Engine"
echo "  - Reconciler Integration with Safety Interceptions"

cd "${OPERATOR_DIR}"
go test -v ./internal/guardrails/... ./internal/reasoner/...

echo ""
echo "[Check 2/4] Verifying Acceptance Criteria 1: Absolute Boundary Enforcement..."
echo "  - Testing proposedReplicas > maxReplicas clamped to maxReplicas"
echo "  - Testing proposedReplicas > maxReplicas rejected when already at maxReplicas"
echo "  - Testing proposedReplicas < minReplicas clamped to minReplicas"
echo "  - Testing proposedReplicas < minReplicas rejected when already at minReplicas"
go test -v ./internal/guardrails -run "TestGuardrails/Deterministic_Guardrail_Pipeline/Absolute_Boundary_Enforcement"
echo "✔ Acceptance Criteria 1 Verified: Controller successfully enforces hard min/max ceilings."

echo ""
echo "[Check 3/4] Verifying Acceptance Criteria 2: Cooldown Window & Hysteresis (Anti-Flapping)..."
echo "  - Testing scale-down within 10 minutes of scale-up is REJECTED"
echo "  - Testing scale-down after 10-minute window has elapsed is ALLOWED"
echo "  - Testing scaling during active cooldown period is REJECTED"
echo "  - Testing rapid oscillation (flapping) suppression under fluctuating loads"
go test -v ./internal/guardrails -run "TestGuardrails/Deterministic_Guardrail_Pipeline/Scale-Down_Hysteresis_Window"
go test -v ./internal/guardrails -run "TestGuardrails/Deterministic_Guardrail_Pipeline/Temporal_Rate-Limiting_Cooldown_Window"
echo "✔ Acceptance Criteria 2 Verified: Cooldown and hysteresis windows prevent rapid oscillation."

echo ""
echo "[Check 4/4] Verifying Acceptance Criteria 3: Safe Reactive HPA Fallback on Outages..."
echo "  - Testing Reasoner call timeout (>3s) defaults safely to reactive HPA"
echo "  - Testing Reasoner connection refused defaults safely to reactive HPA"
echo "  - Testing Reasoner HTTP 500 error defaults safely to reactive HPA"
echo "  - Testing Reasoner malformed JSON schema defaults safely to reactive HPA"
echo "  - Testing Reactive HPA mathematical formulas (target CPU vs observed CPU)"
go test -v ./internal/reasoner -run "TestReasoner/Reasoner_Client_&_Fallback_Engine/Fallback_Logic_on_Reasoning_Service_Outages"
go test -v ./internal/reasoner -run "TestReasoner/Reasoner_Client_&_Fallback_Engine/Reactive_HPA_Algorithm_Calculations"
echo "✔ Acceptance Criteria 3 Verified: System safely defaults to reactive HPA during reasoning outages."

echo ""
echo "=========================================================="
echo "✔ All Epic 6 Acceptance Criteria Verified Successfully!"
echo "=========================================================="
