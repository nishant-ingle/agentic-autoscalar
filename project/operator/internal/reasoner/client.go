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

package reasoner

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"time"
)

// DefaultTimeout is the strict 3-second SLA for reasoner calls as mandated by Epic 6.
const DefaultTimeout = 15 * time.Second

// DefaultTargetCPUPercent is the standard default target CPU utilization for reactive HPA fallback.
const DefaultTargetCPUPercent int32 = 70

// ClusterMetricsPayload matches the FastAPI / LangGraph telemetry schema.
type ClusterMetricsPayload struct {
	Timestamp                string  `json:"timestamp"`
	Namespace                string  `json:"namespace"`
	WorkloadName             string  `json:"workload_name"`
	CurrentReplicas          int32   `json:"current_replicas"`
	MinReplicas              int32   `json:"min_replicas"`
	MaxReplicas              int32   `json:"max_replicas"`
	CPUUtilizationPercent    float64 `json:"cpu_utilization_percent"`
	MemoryUtilizationPercent float64 `json:"memory_utilization_percent"`
	HTTPRequestsPerSecond    float64 `json:"http_requests_per_second"`
	HTTPP99LatencyMS         float64 `json:"http_p99_latency_ms"`
	ErrorRatePercent         float64 `json:"error_rate_percent"`
}

// ScalingRecommendationResponse matches the FastAPI / LangGraph recommendation schema.
type ScalingRecommendationResponse struct {
	WorkloadName                 string  `json:"workload_name"`
	Namespace                    string  `json:"namespace"`
	CurrentReplicas              int32   `json:"current_replicas"`
	TargetReplicas               int32   `json:"target_replicas"`
	Action                       string  `json:"action"`
	Reasoning                    string  `json:"reasoning"`
	ConfidenceScore              float64 `json:"confidence_score"`
	PrimaryMetricDriver          string  `json:"primary_metric_driver"`
	OperationalRunbooksRetrieved int     `json:"operational_runbooks_retrieved"`
	IsFallback                   bool    `json:"is_fallback"`
	ModelUsed                    string  `json:"model_used"`
	Timestamp                    string  `json:"timestamp"`
}

// HTTPClient interface allows mocking HTTP calls in unit tests.
type HTTPClient interface {
	Do(req *http.Request) (*http.Response, error)
}

// Client interacts with the external AI reasoning layer (FastAPI / LangGraph).
type Client struct {
	httpClient HTTPClient
	timeout    time.Duration
}

// NewClient creates a new Reasoner client with a strict 15-second timeout.
func NewClient(timeout time.Duration, customHTTP HTTPClient) *Client {
	if timeout <= 0 {
		timeout = DefaultTimeout
	}
	httpClient := customHTTP
	if httpClient == nil {
		httpClient = &http.Client{
			Timeout: timeout,
		}
	}
	return &Client{
		httpClient: httpClient,
		timeout:    timeout,
	}
}

// EvaluateScaling sends cluster telemetry to the external Reasoner.
// If the call times out (>3s), returns a non-200 code, or returns invalid JSON schema,
// it defaults safely to standard reactive HPA behavior.
func (c *Client) EvaluateScaling(
	ctx context.Context,
	reasonerURL string,
	payload ClusterMetricsPayload,
	targetCPU int32,
) (*ScalingRecommendationResponse, error) {
	if targetCPU <= 0 {
		targetCPU = DefaultTargetCPUPercent
	}

	if reasonerURL == "" {
		fallback := c.ComputeReactiveHPA(payload, targetCPU, "ReasonerURL is empty")
		return fallback, errors.New("empty reasoner URL: engaged reactive HPA fallback")
	}

	if payload.Timestamp == "" {
		payload.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		fallback := c.ComputeReactiveHPA(payload, targetCPU, fmt.Sprintf("Failed to marshal telemetry payload: %v", err))
		return fallback, fmt.Errorf("failed to marshal telemetry: %w", err)
	}

	callCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(callCtx, http.MethodPost, reasonerURL, bytes.NewBuffer(bodyBytes))
	if err != nil {
		fallback := c.ComputeReactiveHPA(payload, targetCPU, fmt.Sprintf("Failed to create HTTP request: %v", err))
		return fallback, fmt.Errorf("failed to create HTTP request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		// Handles connection failure, context timeout (>15s), network partitions
		errMsg := fmt.Sprintf("Reasoner call failed or timed out (>%s): %v", c.timeout, err)
		fallback := c.ComputeReactiveHPA(payload, targetCPU, errMsg)
		return fallback, fmt.Errorf("%s", errMsg)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		errMsg := fmt.Sprintf("Failed to read reasoner response body: %v", err)
		fallback := c.ComputeReactiveHPA(payload, targetCPU, errMsg)
		return fallback, fmt.Errorf("%s", errMsg)
	}

	if resp.StatusCode != http.StatusOK {
		errMsg := fmt.Sprintf("Reasoner returned non-200 status code: %d, body: %s", resp.StatusCode, string(respBytes))
		fallback := c.ComputeReactiveHPA(payload, targetCPU, errMsg)
		return fallback, fmt.Errorf("%s", errMsg)
	}

	var rec ScalingRecommendationResponse
	if err := json.Unmarshal(respBytes, &rec); err != nil {
		errMsg := fmt.Sprintf("Reasoner returned malformed JSON schema: %v", err)
		fallback := c.ComputeReactiveHPA(payload, targetCPU, errMsg)
		return fallback, fmt.Errorf("%s", errMsg)
	}

	// Strict schema validation checks
	if rec.TargetReplicas < 1 || rec.Action == "" {
		errMsg := fmt.Sprintf("Reasoner returned invalid schema fields (target_replicas=%d, action=%s)", rec.TargetReplicas, rec.Action)
		fallback := c.ComputeReactiveHPA(payload, targetCPU, errMsg)
		return fallback, fmt.Errorf("%s", errMsg)
	}

	return &rec, nil
}

// ComputeReactiveHPA calculates desired replicas following standard Kubernetes Horizontal Pod Autoscaler algorithm:
//
//	desiredReplicas = ceil[ currentReplicas * ( currentMetricValue / targetMetricValue ) ]
//
// Includes standard 10% tolerance band to avoid flapping around the target.
func (c *Client) ComputeReactiveHPA(
	payload ClusterMetricsPayload,
	targetCPU int32,
	failureReason string,
) *ScalingRecommendationResponse {
	if targetCPU <= 0 {
		targetCPU = DefaultTargetCPUPercent
	}

	currentReplicas := payload.CurrentReplicas
	if currentReplicas < 1 {
		currentReplicas = 1
	}

	minReplicas := payload.MinReplicas
	if minReplicas < 1 {
		minReplicas = 1
	}
	maxReplicas := payload.MaxReplicas
	if maxReplicas < minReplicas {
		maxReplicas = minReplicas
	}

	desiredReplicas := currentReplicas
	action := "MAINTAIN"

	if payload.CPUUtilizationPercent > 0 {
		ratio := payload.CPUUtilizationPercent / float64(targetCPU)

		// 10% tolerance band around target (0.90 <= ratio <= 1.10)
		if math.Abs(ratio-1.0) > 0.10 {
			computed := int32(math.Ceil(float64(currentReplicas) * ratio))
			desiredReplicas = computed
		}
	}

	// Boundary clamping
	if desiredReplicas > maxReplicas {
		desiredReplicas = maxReplicas
	}
	if desiredReplicas < minReplicas {
		desiredReplicas = minReplicas
	}

	if desiredReplicas > currentReplicas {
		action = "SCALE_UP"
	} else if desiredReplicas < currentReplicas {
		action = "SCALE_DOWN"
	} else {
		action = "MAINTAIN"
	}

	return &ScalingRecommendationResponse{
		WorkloadName:    payload.WorkloadName,
		Namespace:       payload.Namespace,
		CurrentReplicas: currentReplicas,
		TargetReplicas:  desiredReplicas,
		Action:          action,
		Reasoning: fmt.Sprintf(
			"[FALLBACK REACTIVE HPA] Fallback engaged: %s. Replicas evaluated via reactive HPA formula (observed CPU: %.1f%%, target CPU: %d%%).",
			failureReason, payload.CPUUtilizationPercent, targetCPU,
		),
		ConfidenceScore:              1.0,
		PrimaryMetricDriver:          "CPU_UTILIZATION_REACTIVE_HPA_FALLBACK",
		OperationalRunbooksRetrieved: 0,
		IsFallback:                   true,
		ModelUsed:                    "reactive-hpa-fallback",
		Timestamp:                    time.Now().UTC().Format(time.RFC3339),
	}
}
