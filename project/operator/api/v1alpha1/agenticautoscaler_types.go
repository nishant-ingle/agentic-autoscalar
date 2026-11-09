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

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// CrossVersionObjectReference contains enough information to identify the referred resource.
type CrossVersionObjectReference struct {
	// Kind of the referent; e.g. Deployment
	// +kubebuilder:default="Deployment"
	Kind string `json:"kind"`

	// Name of the referent
	Name string `json:"name"`

	// API version of the referent
	// +optional
	// +kubebuilder:default="apps/v1"
	APIVersion string `json:"apiVersion,omitempty"`
}

// AgenticAutoscalerSpec defines the desired state of AgenticAutoscaler
type AgenticAutoscalerSpec struct {
	// ScaleTargetRef points to the target resource to scale (e.g. Deployment)
	ScaleTargetRef CrossVersionObjectReference `json:"scaleTargetRef"`

	// MinReplicas is the lower limit for the number of replicas to which the autoscaler can scale down.
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=1
	// +optional
	MinReplicas *int32 `json:"minReplicas,omitempty"`

	// MaxReplicas is the upper limit for the number of replicas to which the autoscaler can scale up.
	// +kubebuilder:validation:Minimum=1
	MaxReplicas int32 `json:"maxReplicas"`

	// PollingIntervalSeconds defines how frequently (in seconds) the controller polls metrics and reconciles.
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:default=15
	// +optional
	PollingIntervalSeconds *int32 `json:"pollingIntervalSeconds,omitempty"`

	// CooldownPeriodSeconds defines the cooldown duration (in seconds) between scaling operations.
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:default=60
	// +optional
	CooldownPeriodSeconds *int32 `json:"cooldownPeriodSeconds,omitempty"`

	// ScaleDownHysteresisSeconds defines the cool-down window (in seconds) rejecting scale-downs after a prior scale-up.
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:default=600
	// +optional
	ScaleDownHysteresisSeconds *int32 `json:"scaleDownHysteresisSeconds,omitempty"`

	// TargetCPUUtilization is the target CPU percentage used for standard reactive HPA fallback calculations.
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=100
	// +kubebuilder:default=70
	// +optional
	TargetCPUUtilization *int32 `json:"targetCPUUtilization,omitempty"`

	// ReasonerURL is the endpoint of the external reasoning engine (e.g., FastAPI / LangGraph service).
	// +optional
	ReasonerURL string `json:"reasonerURL,omitempty"`

	// PrometheusURL is the optional endpoint of the Prometheus server to query live metrics.
	// +optional
	PrometheusURL string `json:"prometheusURL,omitempty"`
}

// AgenticAutoscalerStatus defines the observed state of AgenticAutoscaler
type AgenticAutoscalerStatus struct {
	// CurrentReplicas is current number of replicas of pods managed by this autoscaler.
	// +optional
	CurrentReplicas int32 `json:"currentReplicas"`

	// ReadyReplicas is the number of ready pods targeted by this autoscaler.
	// +optional
	ReadyReplicas int32 `json:"readyReplicas"`

	// DesiredReplicas is the desired number of replicas of pods calculated by the autoscaler.
	// +optional
	DesiredReplicas int32 `json:"desiredReplicas"`

	// LastScaleTime is the last time the AgenticAutoscaler scaled the target resource.
	// +optional
	LastScaleTime *metav1.Time `json:"lastScaleTime,omitempty"`

	// LastScaleUpTime is the last time the AgenticAutoscaler scaled up the target resource.
	// +optional
	LastScaleUpTime *metav1.Time `json:"lastScaleUpTime,omitempty"`

	// LastScaleDownTime is the last time the AgenticAutoscaler scaled down the target resource.
	// +optional
	LastScaleDownTime *metav1.Time `json:"lastScaleDownTime,omitempty"`

	// LastScaleAction records the most recent scaling action executed (SCALE_UP, SCALE_DOWN, MAINTAIN).
	// +optional
	LastScaleAction string `json:"lastScaleAction,omitempty"`

	// LastGuardrailAction describes any guardrail enforcement taken during the latest cycle (e.g. ACCEPTED, CLAMPED, REJECTED).
	// +optional
	LastGuardrailAction string `json:"lastGuardrailAction,omitempty"`

	// LastGuardrailReason explains why a guardrail was triggered or why scaling was rejected/clamped.
	// +optional
	LastGuardrailReason string `json:"lastGuardrailReason,omitempty"`

	// FallbackEngaged indicates whether the controller engaged fallback reactive HPA behavior.
	// +optional
	FallbackEngaged bool `json:"fallbackEngaged"`

	// LastReconcileTime is the last time the target deployment was inspected by the reconciler.
	// +optional
	LastReconcileTime *metav1.Time `json:"lastReconcileTime,omitempty"`

	// ObservedGeneration is the most recent generation observed by this autoscaler.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Conditions represents the latest available observations of current state.
	// +listType=map
	// +listMapKey=type
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=aa;aautoscaler
// +kubebuilder:printcolumn:name="Target",type="string",JSONPath=".spec.scaleTargetRef.name",description="Target workload"
// +kubebuilder:printcolumn:name="Min",type="integer",JSONPath=".spec.minReplicas",description="Min replicas"
// +kubebuilder:printcolumn:name="Max",type="integer",JSONPath=".spec.maxReplicas",description="Max replicas"
// +kubebuilder:printcolumn:name="Current",type="integer",JSONPath=".status.currentReplicas",description="Current replicas"
// +kubebuilder:printcolumn:name="Desired",type="integer",JSONPath=".status.desiredReplicas",description="Desired replicas"
// +kubebuilder:printcolumn:name="Action",type="string",JSONPath=".status.lastScaleAction",description="Last scale action"
// +kubebuilder:printcolumn:name="Fallback",type="boolean",JSONPath=".status.fallbackEngaged",description="Fallback engaged"
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"

// AgenticAutoscaler is the Schema for the agenticautoscalers API
type AgenticAutoscaler struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   AgenticAutoscalerSpec   `json:"spec,omitempty"`
	Status AgenticAutoscalerStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// AgenticAutoscalerList contains a list of AgenticAutoscaler
type AgenticAutoscalerList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []AgenticAutoscaler `json:"items"`
}

func init() {
	SchemeBuilder.Register(&AgenticAutoscaler{}, &AgenticAutoscalerList{})
}
