/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package guardrails

import (
	"fmt"
	"time"
)

// ScalingAction represents the intended scaling direction.
type ScalingAction string

const (
	ActionScaleUp   ScalingAction = "SCALE_UP"
	ActionScaleDown ScalingAction = "SCALE_DOWN"
	ActionMaintain  ScalingAction = "MAINTAIN"
)

// GuardrailDisposition indicates how a guardrail handled a recommendation.
type GuardrailDisposition string

const (
	DispositionAccepted GuardrailDisposition = "ACCEPTED"
	DispositionClamped  GuardrailDisposition = "CLAMPED"
	DispositionRejected GuardrailDisposition = "REJECTED"
)

// InterceptionRecord captures details of a single guardrail intervention.
type InterceptionRecord struct {
	GuardrailName string               `json:"guardrailName"`
	Disposition   GuardrailDisposition `json:"disposition"`
	OriginalValue int32                `json:"originalValue"`
	EnforcedValue int32                `json:"enforcedValue"`
	Reason        string               `json:"reason"`
}

// PipelineInput defines all operational metrics and state timestamps needed to evaluate safety invariants.
type PipelineInput struct {
	ProposedReplicas    int32
	CurrentReplicas     int32
	MinReplicas         int32
	MaxReplicas         int32
	LastScaleTime       *time.Time
	LastScaleUpTime     *time.Time
	LastScaleDownTime   *time.Time
	CooldownPeriod      time.Duration
	ScaleDownHysteresis time.Duration
	Now                 time.Time
}

// PipelineResult encapsulates the deterministic verdict after executing all guardrails.
type PipelineResult struct {
	OriginalReplicas   int32
	TargetReplicas     int32
	Action             ScalingAction
	Interceptions      []InterceptionRecord
	PassedUnmodified   bool
	PrimaryDisposition GuardrailDisposition
	SummaryReason      string
}

// GuardrailPipeline implements the deterministic safety barriers for scaling recommendations.
type GuardrailPipeline struct{}

// NewGuardrailPipeline creates a new instance of the GuardrailPipeline.
func NewGuardrailPipeline() *GuardrailPipeline {
	return &GuardrailPipeline{}
}

// Evaluate passes the proposed replica count through all deterministic guardrails in order:
// 1. Absolute boundary checks (minReplicas and maxReplicas hard limits).
// 2. Scale-down hysteresis window (prevents scale-downs shortly after scale-ups).
// 3. Temporal rate-limiting cooldown window (anti-flapping barrier).
func (g *GuardrailPipeline) Evaluate(input PipelineInput) PipelineResult {
	result := PipelineResult{
		OriginalReplicas:   input.ProposedReplicas,
		TargetReplicas:     input.ProposedReplicas,
		Action:             ActionMaintain,
		Interceptions:      make([]InterceptionRecord, 0),
		PassedUnmodified:   true,
		PrimaryDisposition: DispositionAccepted,
		SummaryReason:      "Scaling recommendation passed all deterministic safety guardrails without modification.",
	}

	now := input.Now
	if now.IsZero() {
		now = time.Now()
	}

	// Sanitize boundary inputs
	minReplicas := input.MinReplicas
	if minReplicas < 1 {
		minReplicas = 1
	}
	maxReplicas := input.MaxReplicas
	if maxReplicas < minReplicas {
		maxReplicas = minReplicas
	}

	currentReplicas := input.CurrentReplicas
	candidateReplicas := input.ProposedReplicas

	// -------------------------------------------------------------------------
	// Guardrail 1: Absolute Boundary Enforcement (Hard Floor & Hard Ceiling)
	// -------------------------------------------------------------------------
	if candidateReplicas > maxReplicas {
		result.PassedUnmodified = false
		if currentReplicas >= maxReplicas {
			// Already at or above maxReplicas; reject scaling up further
			record := InterceptionRecord{
				GuardrailName: "AbsoluteBoundaryEnforcement",
				Disposition:   DispositionRejected,
				OriginalValue: candidateReplicas,
				EnforcedValue: currentReplicas,
				Reason: fmt.Sprintf(
					"Proposed replicas (%d) exceeds maxReplicas ceiling (%d); scaling up rejected because current replicas is %d",
					candidateReplicas, maxReplicas, currentReplicas,
				),
			}
			result.Interceptions = append(result.Interceptions, record)
			candidateReplicas = currentReplicas
		} else {
			// Clamp to maxReplicas
			record := InterceptionRecord{
				GuardrailName: "AbsoluteBoundaryEnforcement",
				Disposition:   DispositionClamped,
				OriginalValue: candidateReplicas,
				EnforcedValue: maxReplicas,
				Reason: fmt.Sprintf(
					"Proposed replicas (%d) exceeds maxReplicas ceiling (%d); clamped down to %d",
					candidateReplicas, maxReplicas, maxReplicas,
				),
			}
			result.Interceptions = append(result.Interceptions, record)
			candidateReplicas = maxReplicas
		}
	} else if candidateReplicas < minReplicas {
		result.PassedUnmodified = false
		if currentReplicas <= minReplicas {
			// Already at or below minReplicas; reject scaling down further
			record := InterceptionRecord{
				GuardrailName: "AbsoluteBoundaryEnforcement",
				Disposition:   DispositionRejected,
				OriginalValue: candidateReplicas,
				EnforcedValue: currentReplicas,
				Reason: fmt.Sprintf(
					"Proposed replicas (%d) is below minReplicas floor (%d); scaling down rejected because current replicas is %d",
					candidateReplicas, minReplicas, currentReplicas,
				),
			}
			result.Interceptions = append(result.Interceptions, record)
			candidateReplicas = currentReplicas
		} else {
			// Clamp to minReplicas
			record := InterceptionRecord{
				GuardrailName: "AbsoluteBoundaryEnforcement",
				Disposition:   DispositionClamped,
				OriginalValue: candidateReplicas,
				EnforcedValue: minReplicas,
				Reason: fmt.Sprintf(
					"Proposed replicas (%d) is below minReplicas floor (%d); clamped up to %d",
					candidateReplicas, minReplicas, minReplicas,
				),
			}
			result.Interceptions = append(result.Interceptions, record)
			candidateReplicas = minReplicas
		}
	}

	// -------------------------------------------------------------------------
	// Guardrail 2: Scale-Down Hysteresis Window (Anti-Flapping on scale-down)
	// Reject any scale-down command issued within hysteresis window of a prior scale-up
	// -------------------------------------------------------------------------
	if candidateReplicas < currentReplicas {
		hysteresis := input.ScaleDownHysteresis
		if hysteresis > 0 && input.LastScaleUpTime != nil && !input.LastScaleUpTime.IsZero() {
			elapsed := now.Sub(*input.LastScaleUpTime)
			if elapsed < hysteresis {
				result.PassedUnmodified = false
				remaining := hysteresis - elapsed
				record := InterceptionRecord{
					GuardrailName: "ScaleDownHysteresis",
					Disposition:   DispositionRejected,
					OriginalValue: candidateReplicas,
					EnforcedValue: currentReplicas,
					Reason: fmt.Sprintf(
						"Scale-down from %d to %d rejected: prior scale-up occurred %s ago (hysteresis window is %s; cooldown remaining %s)",
						currentReplicas, candidateReplicas, elapsed.Round(time.Second), hysteresis.Round(time.Second), remaining.Round(time.Second),
					),
				}
				result.Interceptions = append(result.Interceptions, record)
				candidateReplicas = currentReplicas
			}
		}
	}

	// -------------------------------------------------------------------------
	// Guardrail 3: Temporal Rate-Limiting Cooldown Window
	// Prevent any scaling oscillation if within cooldownPeriod of any prior scaling action
	// -------------------------------------------------------------------------
	if candidateReplicas != currentReplicas {
		cooldown := input.CooldownPeriod
		if cooldown > 0 && input.LastScaleTime != nil && !input.LastScaleTime.IsZero() {
			elapsed := now.Sub(*input.LastScaleTime)
			if elapsed < cooldown {
				result.PassedUnmodified = false
				remaining := cooldown - elapsed
				record := InterceptionRecord{
					GuardrailName: "CooldownRateLimiting",
					Disposition:   DispositionRejected,
					OriginalValue: candidateReplicas,
					EnforcedValue: currentReplicas,
					Reason: fmt.Sprintf(
						"Scaling from %d to %d rejected: prior scaling event occurred %s ago (cooldown period is %s; cooldown remaining %s)",
						currentReplicas, candidateReplicas, elapsed.Round(time.Second), cooldown.Round(time.Second), remaining.Round(time.Second),
					),
				}
				result.Interceptions = append(result.Interceptions, record)
				candidateReplicas = currentReplicas
			}
		}
	}

	// Determine final action and summary disposition
	result.TargetReplicas = candidateReplicas
	if result.TargetReplicas > currentReplicas {
		result.Action = ActionScaleUp
	} else if result.TargetReplicas < currentReplicas {
		result.Action = ActionScaleDown
	} else {
		result.Action = ActionMaintain
	}

	if len(result.Interceptions) > 0 {
		// Pick primary disposition: REJECTED takes precedence over CLAMPED
		hasRejection := false
		for _, interception := range result.Interceptions {
			if interception.Disposition == DispositionRejected {
				hasRejection = true
				result.PrimaryDisposition = DispositionRejected
				result.SummaryReason = interception.Reason
				break
			}
		}
		if !hasRejection {
			result.PrimaryDisposition = DispositionClamped
			result.SummaryReason = result.Interceptions[0].Reason
		}
	}

	return result
}
