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

package guardrails_test

import (
	"testing"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"github.com/nishant-ingle/agentic-autoscaler/internal/guardrails"
)

func TestGuardrails(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Guardrails Suite")
}

var _ = Describe("Deterministic Guardrail Pipeline", func() {
	var (
		pipeline *guardrails.GuardrailPipeline
		now      time.Time
	)

	BeforeEach(func() {
		pipeline = guardrails.NewGuardrailPipeline()
		now = time.Date(2026, 11, 9, 20, 0, 0, 0, time.UTC)
	})

	Context("Absolute Boundary Enforcement", func() {
		It("should accept recommendations within minReplicas and maxReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    3,
				CurrentReplicas:     2,
				MinReplicas:         1,
				MaxReplicas:         5,
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeTrue())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionAccepted))
			Expect(result.TargetReplicas).To(Equal(int32(3)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleUp))
			Expect(result.Interceptions).To(BeEmpty())
		})

		It("should clamp recommendations exceeding maxReplicas when currentReplicas < maxReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    10, // Exceeds ceiling
				CurrentReplicas:     2,
				MinReplicas:         1,
				MaxReplicas:         5,
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionClamped))
			Expect(result.TargetReplicas).To(Equal(int32(5)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleUp))
			Expect(result.Interceptions).To(HaveLen(1))
			Expect(result.Interceptions[0].GuardrailName).To(Equal("AbsoluteBoundaryEnforcement"))
			Expect(result.Interceptions[0].Disposition).To(Equal(guardrails.DispositionClamped))
			Expect(result.Interceptions[0].OriginalValue).To(Equal(int32(10)))
			Expect(result.Interceptions[0].EnforcedValue).To(Equal(int32(5)))
		})

		It("should reject recommendations exceeding maxReplicas when currentReplicas == maxReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    8,
				CurrentReplicas:     5, // Already at max
				MinReplicas:         1,
				MaxReplicas:         5,
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionRejected))
			Expect(result.TargetReplicas).To(Equal(int32(5)))
			Expect(result.Action).To(Equal(guardrails.ActionMaintain))
			Expect(result.Interceptions).To(HaveLen(1))
			Expect(result.Interceptions[0].Disposition).To(Equal(guardrails.DispositionRejected))
		})

		It("should clamp recommendations below minReplicas when currentReplicas > minReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    0, // Below floor
				CurrentReplicas:     3,
				MinReplicas:         1,
				MaxReplicas:         5,
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionClamped))
			Expect(result.TargetReplicas).To(Equal(int32(1)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleDown))
			Expect(result.Interceptions).To(HaveLen(1))
			Expect(result.Interceptions[0].GuardrailName).To(Equal("AbsoluteBoundaryEnforcement"))
		})

		It("should reject recommendations below minReplicas when currentReplicas == minReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    0,
				CurrentReplicas:     1, // Already at min
				MinReplicas:         1,
				MaxReplicas:         5,
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionRejected))
			Expect(result.TargetReplicas).To(Equal(int32(1)))
			Expect(result.Action).To(Equal(guardrails.ActionMaintain))
		})
	})

	Context("Scale-Down Hysteresis Window", func() {
		It("should reject any scale-down issued within 10 minutes of a prior scale-up", func() {
			lastScaleUp := now.Add(-3 * time.Minute) // Scaled up 3 minutes ago
			input := guardrails.PipelineInput{
				ProposedReplicas:    2,
				CurrentReplicas:     4, // Scale-down from 4 to 2
				MinReplicas:         1,
				MaxReplicas:         5,
				LastScaleUpTime:     &lastScaleUp,
				ScaleDownHysteresis: 10 * time.Minute, // 10 min window
				CooldownPeriod:      0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionRejected))
			Expect(result.TargetReplicas).To(Equal(int32(4))) // Maintained at current
			Expect(result.Action).To(Equal(guardrails.ActionMaintain))
			Expect(result.Interceptions).To(HaveLen(1))
			Expect(result.Interceptions[0].GuardrailName).To(Equal("ScaleDownHysteresis"))
			Expect(result.Interceptions[0].Disposition).To(Equal(guardrails.DispositionRejected))
		})

		It("should allow scale-down when prior scale-up was more than 10 minutes ago", func() {
			lastScaleUp := now.Add(-11 * time.Minute) // Scaled up 11 minutes ago
			input := guardrails.PipelineInput{
				ProposedReplicas:    2,
				CurrentReplicas:     4,
				MinReplicas:         1,
				MaxReplicas:         5,
				LastScaleUpTime:     &lastScaleUp,
				ScaleDownHysteresis: 10 * time.Minute,
				CooldownPeriod:      0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeTrue())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionAccepted))
			Expect(result.TargetReplicas).To(Equal(int32(2)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleDown))
			Expect(result.Interceptions).To(BeEmpty())
		})

		It("should not block scale-up even if inside the hysteresis window", func() {
			lastScaleUp := now.Add(-2 * time.Minute)
			input := guardrails.PipelineInput{
				ProposedReplicas:    5,
				CurrentReplicas:     3, // Another scale-up from 3 to 5
				MinReplicas:         1,
				MaxReplicas:         5,
				LastScaleUpTime:     &lastScaleUp,
				ScaleDownHysteresis: 10 * time.Minute,
				CooldownPeriod:      0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeTrue())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionAccepted))
			Expect(result.TargetReplicas).To(Equal(int32(5)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleUp))
		})
	})

	Context("Temporal Rate-Limiting Cooldown Window (Anti-Flapping)", func() {
		It("should reject any scaling operation within the cooldown period", func() {
			lastScale := now.Add(-25 * time.Second) // Scaled 25s ago
			input := guardrails.PipelineInput{
				ProposedReplicas:    4,
				CurrentReplicas:     2,
				MinReplicas:         1,
				MaxReplicas:         5,
				LastScaleTime:       &lastScale,
				CooldownPeriod:      60 * time.Second, // 60s cooldown
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeFalse())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionRejected))
			Expect(result.TargetReplicas).To(Equal(int32(2))) // Kept at current
			Expect(result.Action).To(Equal(guardrails.ActionMaintain))
			Expect(result.Interceptions).To(HaveLen(1))
			Expect(result.Interceptions[0].GuardrailName).To(Equal("CooldownRateLimiting"))
		})

		It("should allow scaling operation when cooldown has expired", func() {
			lastScale := now.Add(-65 * time.Second) // Scaled 65s ago (cooldown 60s)
			input := guardrails.PipelineInput{
				ProposedReplicas:    4,
				CurrentReplicas:     2,
				MinReplicas:         1,
				MaxReplicas:         5,
				LastScaleTime:       &lastScale,
				CooldownPeriod:      60 * time.Second,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.PassedUnmodified).To(BeTrue())
			Expect(result.PrimaryDisposition).To(Equal(guardrails.DispositionAccepted))
			Expect(result.TargetReplicas).To(Equal(int32(4)))
			Expect(result.Action).To(Equal(guardrails.ActionScaleUp))
		})
	})

	Context("Sanitization and Boundary Edge Cases", func() {
		It("should sanitize minReplicas < 1 and maxReplicas < minReplicas", func() {
			input := guardrails.PipelineInput{
				ProposedReplicas:    4,
				CurrentReplicas:     1,
				MinReplicas:         0,  // Sanitized to 1
				MaxReplicas:         -1, // Sanitized to minReplicas (1)
				CooldownPeriod:      0,
				ScaleDownHysteresis: 0,
				Now:                 now,
			}

			result := pipeline.Evaluate(input)
			Expect(result.TargetReplicas).To(Equal(int32(1))) // Clamped to 1
			Expect(result.Action).To(Equal(guardrails.ActionMaintain))
		})
	})
})
