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

package reasoner_test

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"testing"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"github.com/nishant-ingle/agentic-autoscaler/internal/reasoner"
)

func TestReasoner(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Reasoner Suite")
}

// mockHTTPClient enables fine-grained simulation of network conditions.
type mockHTTPClient struct {
	doFunc func(req *http.Request) (*http.Response, error)
}

func (m *mockHTTPClient) Do(req *http.Request) (*http.Response, error) {
	return m.doFunc(req)
}

var _ = Describe("Reasoner Client & Fallback Engine", func() {
	var (
		client  *reasoner.Client
		payload reasoner.ClusterMetricsPayload
	)

	BeforeEach(func() {
		payload = reasoner.ClusterMetricsPayload{
			Namespace:                "workload-system",
			WorkloadName:             "target-workload",
			CurrentReplicas:          2,
			MinReplicas:              1,
			MaxReplicas:              5,
			CPUUtilizationPercent:    85.0,
			MemoryUtilizationPercent: 60.0,
			HTTPRequestsPerSecond:    150.0,
			HTTPP99LatencyMS:         45.0,
			ErrorRatePercent:         0.0,
		}
	})

	Context("Successful Reasoner Invocations", func() {
		It("should successfully parse valid JSON recommendations from FastAPI", func() {
			mockJSON := `{
				"workload_name": "target-workload",
				"namespace": "workload-system",
				"current_replicas": 2,
				"target_replicas": 4,
				"action": "SCALE_UP",
				"reasoning": "CPU utilization reached 85%, scaling up to meet demand.",
				"confidence_score": 0.95,
				"primary_metric_driver": "CPU_UTILIZATION",
				"operational_runbooks_retrieved": 2,
				"is_fallback": false,
				"model_used": "gpt-4o"
			}`

			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return &http.Response{
						StatusCode: http.StatusOK,
						Body:       io.NopCloser(bytes.NewBufferString(mockJSON)),
					}, nil
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).NotTo(HaveOccurred())
			Expect(resp.IsFallback).To(BeFalse())
			Expect(resp.TargetReplicas).To(Equal(int32(4)))
			Expect(resp.Action).To(Equal("SCALE_UP"))
			Expect(resp.ModelUsed).To(Equal("gpt-4o"))
		})
	})

	Context("Fallback Logic on Reasoning Service Outages", func() {
		It("should default safely to reactive HPA on timeout (>3s)", func() {
			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					// Simulate context deadline exceeded / timeout
					return nil, context.DeadlineExceeded
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("Reasoner call failed or timed out"))
			Expect(resp).NotTo(BeNil())
			Expect(resp.IsFallback).To(BeTrue())
			Expect(resp.ModelUsed).To(Equal("reactive-hpa-fallback"))
			// 85% CPU / 70% target with 2 replicas -> ceil(2 * 85/70) = ceil(2.428) = 3
			Expect(resp.TargetReplicas).To(Equal(int32(3)))
			Expect(resp.Action).To(Equal("SCALE_UP"))
		})

		It("should default safely to reactive HPA on connection refused / network error", func() {
			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return nil, errors.New("connection refused")
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).To(HaveOccurred())
			Expect(resp).NotTo(BeNil())
			Expect(resp.IsFallback).To(BeTrue())
			Expect(resp.TargetReplicas).To(Equal(int32(3)))
		})

		It("should default safely to reactive HPA on HTTP 500 error", func() {
			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return &http.Response{
						StatusCode: http.StatusInternalServerError,
						Body:       io.NopCloser(bytes.NewBufferString(`{"detail":"Internal reasoning error"}`)),
					}, nil
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("Reasoner returned non-200 status code: 500"))
			Expect(resp).NotTo(BeNil())
			Expect(resp.IsFallback).To(BeTrue())
		})

		It("should default safely to reactive HPA on malformed JSON response", func() {
			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return &http.Response{
						StatusCode: http.StatusOK,
						Body:       io.NopCloser(bytes.NewBufferString(`invalid-json-content`)),
					}, nil
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("malformed JSON schema"))
			Expect(resp).NotTo(BeNil())
			Expect(resp.IsFallback).To(BeTrue())
		})

		It("should default safely to reactive HPA on invalid schema values (e.g. target_replicas < 1)", func() {
			mock := &mockHTTPClient{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return &http.Response{
						StatusCode: http.StatusOK,
						Body: io.NopCloser(bytes.NewBufferString(`{
							"workload_name": "target-workload",
							"namespace": "workload-system",
							"current_replicas": 2,
							"target_replicas": 0,
							"action": "SCALE_DOWN"
						}`)),
					}, nil
				},
			}

			client = reasoner.NewClient(3*time.Second, mock)
			resp, err := client.EvaluateScaling(context.Background(), "http://mock-reasoner/evaluate-scaling", payload, 70)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid schema fields"))
			Expect(resp).NotTo(BeNil())
			Expect(resp.IsFallback).To(BeTrue())
		})
	})

	Context("Reactive HPA Algorithm Calculations", func() {
		BeforeEach(func() {
			client = reasoner.NewClient(3*time.Second, nil)
		})

		It("should calculate scale-up correctly when CPU exceeds target", func() {
			payload.CPUUtilizationPercent = 95.0
			payload.CurrentReplicas = 2
			// 95 / 70 * 2 = 2.71 -> ceil = 3
			rec := client.ComputeReactiveHPA(payload, 70, "test")
			Expect(rec.TargetReplicas).To(Equal(int32(3)))
			Expect(rec.Action).To(Equal("SCALE_UP"))
			Expect(rec.IsFallback).To(BeTrue())
		})

		It("should calculate scale-down correctly when CPU is well below target", func() {
			payload.CPUUtilizationPercent = 25.0
			payload.CurrentReplicas = 4
			// 25 / 70 * 4 = 1.428 -> ceil = 2
			rec := client.ComputeReactiveHPA(payload, 70, "test")
			Expect(rec.TargetReplicas).To(Equal(int32(2)))
			Expect(rec.Action).To(Equal("SCALE_DOWN"))
			Expect(rec.IsFallback).To(BeTrue())
		})

		It("should maintain replicas when CPU is within 10% tolerance band", func() {
			payload.CPUUtilizationPercent = 72.0 // 72 / 70 = 1.028 (within 10%)
			payload.CurrentReplicas = 3
			rec := client.ComputeReactiveHPA(payload, 70, "test")
			Expect(rec.TargetReplicas).To(Equal(int32(3)))
			Expect(rec.Action).To(Equal("MAINTAIN"))
		})

		It("should clamp to minReplicas and maxReplicas boundaries", func() {
			// Super high CPU would suggest 20 replicas, but max is 5
			payload.CPUUtilizationPercent = 500.0
			payload.CurrentReplicas = 2
			rec := client.ComputeReactiveHPA(payload, 70, "test")
			Expect(rec.TargetReplicas).To(Equal(int32(5)))
			Expect(rec.Action).To(Equal("SCALE_UP"))
		})
	})
})
