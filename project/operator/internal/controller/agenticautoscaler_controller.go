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

package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	meta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/builder"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/predicate"

	autoscalingv1alpha1 "github.com/nishant-ingle/agentic-autoscaler/api/v1alpha1"
	"github.com/nishant-ingle/agentic-autoscaler/internal/guardrails"
	"github.com/nishant-ingle/agentic-autoscaler/internal/reasoner"
)

const (
	// DefaultPollingIntervalSeconds is the fallback reconciliation polling interval
	DefaultPollingIntervalSeconds int32 = 15
	// DefaultCooldownPeriodSeconds is the default anti-flapping scaling cooldown
	DefaultCooldownPeriodSeconds int32 = 60
	// DefaultScaleDownHysteresisSeconds is the default scale-down cooldown after a scale-up (10 minutes)
	DefaultScaleDownHysteresisSeconds int32 = 600
	// DefaultTargetCPUUtilization is the standard reactive HPA fallback CPU target
	DefaultTargetCPUUtilization int32 = 70

	// ConditionTypeTargetFound indicates whether the target deployment was successfully found
	ConditionTypeTargetFound = "TargetFound"
	// ConditionTypeScalingActive indicates whether the autoscaler is actively monitoring and able to scale
	ConditionTypeScalingActive = "ScalingActive"
	// ConditionTypeGuardrailApplied indicates whether deterministic guardrails intercepted the proposal
	ConditionTypeGuardrailApplied = "GuardrailApplied"
	// ConditionTypeReasonerHealthy indicates whether the external reasoning layer is reachable and healthy
	ConditionTypeReasonerHealthy = "ReasonerHealthy"
)

// AgenticAutoscalerReconciler reconciles a AgenticAutoscaler object
type AgenticAutoscalerReconciler struct {
	client.Client
	Scheme            *runtime.Scheme
	Recorder          record.EventRecorder
	ReasonerClient    *reasoner.Client
	GuardrailPipeline *guardrails.GuardrailPipeline
}

// +kubebuilder:rbac:groups=autoscaling.autoscale.ai,resources=agenticautoscalers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=autoscaling.autoscale.ai,resources=agenticautoscalers/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=autoscaling.autoscale.ai,resources=agenticautoscalers/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=apps,resources=deployments/status,verbs=get
// +kubebuilder:rbac:groups=apps,resources=deployments/scale,verbs=get;update;patch
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *AgenticAutoscalerReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Ensure ReasonerClient and GuardrailPipeline are initialized
	if r.ReasonerClient == nil {
		r.ReasonerClient = reasoner.NewClient(reasoner.DefaultTimeout, nil)
	}
	if r.GuardrailPipeline == nil {
		r.GuardrailPipeline = guardrails.NewGuardrailPipeline()
	}

	// 1. Fetch the AgenticAutoscaler instance
	var autoscaler autoscalingv1alpha1.AgenticAutoscaler
	if err := r.Get(ctx, req.NamespacedName, &autoscaler); err != nil {
		if apierrors.IsNotFound(err) {
			logger.Info("AgenticAutoscaler resource not found; ignoring because object was deleted", "autoscaler", req.NamespacedName)
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Failed to retrieve AgenticAutoscaler", "autoscaler", req.NamespacedName)
		return ctrl.Result{}, err
	}

	// 2. Parse configuration, constraints, and guardrail timings
	pollingInterval := DefaultPollingIntervalSeconds
	if autoscaler.Spec.PollingIntervalSeconds != nil && *autoscaler.Spec.PollingIntervalSeconds > 0 {
		pollingInterval = *autoscaler.Spec.PollingIntervalSeconds
	}

	cooldownPeriod := DefaultCooldownPeriodSeconds
	if autoscaler.Spec.CooldownPeriodSeconds != nil && *autoscaler.Spec.CooldownPeriodSeconds >= 0 {
		cooldownPeriod = *autoscaler.Spec.CooldownPeriodSeconds
	}

	scaleDownHysteresis := DefaultScaleDownHysteresisSeconds
	if autoscaler.Spec.ScaleDownHysteresisSeconds != nil && *autoscaler.Spec.ScaleDownHysteresisSeconds >= 0 {
		scaleDownHysteresis = *autoscaler.Spec.ScaleDownHysteresisSeconds
	}

	targetCPU := DefaultTargetCPUUtilization
	if autoscaler.Spec.TargetCPUUtilization != nil && *autoscaler.Spec.TargetCPUUtilization > 0 {
		targetCPU = *autoscaler.Spec.TargetCPUUtilization
	}

	minReplicas := int32(1)
	if autoscaler.Spec.MinReplicas != nil && *autoscaler.Spec.MinReplicas > 0 {
		minReplicas = *autoscaler.Spec.MinReplicas
	}
	maxReplicas := autoscaler.Spec.MaxReplicas
	if maxReplicas < minReplicas {
		maxReplicas = minReplicas
	}

	targetRef := autoscaler.Spec.ScaleTargetRef
	targetKey := types.NamespacedName{
		Namespace: autoscaler.Namespace,
		Name:      targetRef.Name,
	}

	// 3. Inspect target Deployment status using client-go
	var deployment appsv1.Deployment
	if err := r.Get(ctx, targetKey, &deployment); err != nil {
		if apierrors.IsNotFound(err) {
			logger.Info("Target deployment not found",
				"autoscaler", req.NamespacedName,
				"targetDeployment", targetKey.String(),
			)

			meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
				Type:               ConditionTypeTargetFound,
				Status:             metav1.ConditionFalse,
				Reason:             "DeploymentNotFound",
				Message:            fmt.Sprintf("Target deployment '%s' was not found in namespace '%s'", targetRef.Name, autoscaler.Namespace),
				ObservedGeneration: autoscaler.Generation,
			})
			meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
				Type:               ConditionTypeScalingActive,
				Status:             metav1.ConditionFalse,
				Reason:             "TargetNotFound",
				Message:            "Autoscaling inactive: target deployment cannot be reached",
				ObservedGeneration: autoscaler.Generation,
			})

			now := metav1.Now()
			autoscaler.Status.LastReconcileTime = &now
			if updateErr := r.Status().Update(ctx, &autoscaler); updateErr != nil {
				logger.Error(updateErr, "Failed to update AgenticAutoscaler status after target deployment not found")
			}
			return ctrl.Result{RequeueAfter: time.Duration(pollingInterval) * time.Second}, nil
		}
		logger.Error(err, "Failed to fetch target deployment", "targetDeployment", targetKey.String())
		return ctrl.Result{}, err
	}

	// 4. Extract deployment replica metrics
	specReplicas := int32(1)
	if deployment.Spec.Replicas != nil {
		specReplicas = *deployment.Spec.Replicas
	}
	currentStatusReplicas := deployment.Status.Replicas
	readyReplicas := deployment.Status.ReadyReplicas
	availableReplicas := deployment.Status.AvailableReplicas
	updatedReplicas := deployment.Status.UpdatedReplicas

	// 5. Collect telemetry for the external reasoner
	telemetry := r.collectTelemetry(ctx, &autoscaler, &deployment, specReplicas, minReplicas, maxReplicas)

	// 6. Request reasoning proposal from Reasoner service (with strict 3-second SLA and fallback)
	rec, reasonerErr := r.ReasonerClient.EvaluateScaling(ctx, autoscaler.Spec.ReasonerURL, telemetry, targetCPU)
	fallbackEngaged := false

	if reasonerErr != nil {
		fallbackEngaged = true
		logger.Info("[AUDIT: REASONER FALLBACK ENGAGED] External reasoner service failed or timed out; safe reactive HPA fallback activated",
			"audit_event", "REASONER_FALLBACK",
			"autoscaler", req.NamespacedName.String(),
			"target_deployment", targetKey.String(),
			"reasoner_url", autoscaler.Spec.ReasonerURL,
			"fallback_target_replicas", rec.TargetReplicas,
			"fallback_action", rec.Action,
			"error", reasonerErr.Error(),
		)

		if r.Recorder != nil {
			r.Recorder.Eventf(&autoscaler, corev1.EventTypeWarning, "ReasonerFallbackEngaged",
				"Reasoner call failed (>3s timeout or error: %v); safely engaged standard reactive HPA fallback (target %d replicas)",
				reasonerErr, rec.TargetReplicas,
			)
		}

		meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
			Type:               ConditionTypeReasonerHealthy,
			Status:             metav1.ConditionFalse,
			Reason:             "ReasonerServiceOutage",
			Message:            fmt.Sprintf("Reasoner call failed: %v", reasonerErr),
			ObservedGeneration: autoscaler.Generation,
		})
	} else {
		fallbackEngaged = rec.IsFallback
		logger.Info("Received scaling proposal from AI Reasoner",
			"autoscaler", req.NamespacedName.String(),
			"target_replicas", rec.TargetReplicas,
			"action", rec.Action,
			"model", rec.ModelUsed,
			"confidence", rec.ConfidenceScore,
			"driver", rec.PrimaryMetricDriver,
		)

		meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
			Type:               ConditionTypeReasonerHealthy,
			Status:             metav1.ConditionTrue,
			Reason:             "ReasonerAvailable",
			Message:            fmt.Sprintf("Reasoner service responded successfully (model: %s)", rec.ModelUsed),
			ObservedGeneration: autoscaler.Generation,
		})
	}

	// 7. Pass proposal through Deterministic Guardrail Pipeline
	lastScaleTime := timeFromMeta(autoscaler.Status.LastScaleTime)
	lastScaleUpTime := timeFromMeta(autoscaler.Status.LastScaleUpTime)
	lastScaleDownTime := timeFromMeta(autoscaler.Status.LastScaleDownTime)

	guardrailInput := guardrails.PipelineInput{
		ProposedReplicas:    rec.TargetReplicas,
		CurrentReplicas:     specReplicas,
		MinReplicas:         minReplicas,
		MaxReplicas:         maxReplicas,
		LastScaleTime:       lastScaleTime,
		LastScaleUpTime:     lastScaleUpTime,
		LastScaleDownTime:   lastScaleDownTime,
		CooldownPeriod:      time.Duration(cooldownPeriod) * time.Second,
		ScaleDownHysteresis: time.Duration(scaleDownHysteresis) * time.Second,
		Now:                 time.Now(),
	}

	verdict := r.GuardrailPipeline.Evaluate(guardrailInput)

	// Record structured audit logs and emit Kubernetes events for all guardrail interceptions
	if len(verdict.Interceptions) > 0 {
		for _, interception := range verdict.Interceptions {
			logger.Info("[AUDIT: GUARDRAIL INTERCEPTION] Safety barrier intercepted scaling recommendation",
				"audit_event", "GUARDRAIL_INTERCEPTION",
				"guardrail", interception.GuardrailName,
				"disposition", string(interception.Disposition),
				"autoscaler", req.NamespacedName.String(),
				"target_deployment", targetKey.String(),
				"proposed_replicas", interception.OriginalValue,
				"enforced_replicas", interception.EnforcedValue,
				"reason", interception.Reason,
			)

			if r.Recorder != nil {
				r.Recorder.Eventf(&autoscaler, corev1.EventTypeWarning, "GuardrailInterception",
					"[%s] %s: proposed %d, enforced %d. %s",
					interception.GuardrailName, interception.Disposition, interception.OriginalValue, interception.EnforcedValue, interception.Reason,
				)
			}
		}

		meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
			Type:               ConditionTypeGuardrailApplied,
			Status:             metav1.ConditionTrue,
			Reason:             "GuardrailTriggered",
			Message:            verdict.SummaryReason,
			ObservedGeneration: autoscaler.Generation,
		})
	} else {
		meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
			Type:               ConditionTypeGuardrailApplied,
			Status:             metav1.ConditionFalse,
			Reason:             "NoGuardrailTriggered",
			Message:            "Scaling recommendation passed all safety invariants without modification",
			ObservedGeneration: autoscaler.Generation,
		})
	}

	// 8. Apply scaling modification if final target differs from deployment spec
	if verdict.TargetReplicas != specReplicas {
		deployment.Spec.Replicas = &verdict.TargetReplicas
		if err := r.Update(ctx, &deployment); err != nil {
			logger.Error(err, "Failed to update target deployment replicas", "deployment", targetKey.String())
			return ctrl.Result{}, err
		}

		nowMeta := metav1.Now()
		autoscaler.Status.LastScaleTime = &nowMeta
		if verdict.Action == guardrails.ActionScaleUp {
			autoscaler.Status.LastScaleUpTime = &nowMeta
		} else if verdict.Action == guardrails.ActionScaleDown {
			autoscaler.Status.LastScaleDownTime = &nowMeta
		}
		autoscaler.Status.LastScaleAction = string(verdict.Action)

		logger.Info("[AUDIT: SCALING EXECUTED] Scaled target deployment",
			"audit_event", "SCALE_EXECUTED",
			"autoscaler", req.NamespacedName.String(),
			"target_deployment", targetKey.String(),
			"previous_replicas", specReplicas,
			"new_replicas", verdict.TargetReplicas,
			"action", string(verdict.Action),
			"reasoning", rec.Reasoning,
		)

		if r.Recorder != nil {
			r.Recorder.Eventf(&autoscaler, corev1.EventTypeNormal, "ScalingExecuted",
				"Scaled deployment %s from %d to %d replicas (Action: %s)",
				targetRef.Name, specReplicas, verdict.TargetReplicas, verdict.Action,
			)
		}
	} else {
		autoscaler.Status.LastScaleAction = string(guardrails.ActionMaintain)
		logger.Info("Reconcile loop: observed target deployment state",
			"autoscaler", req.NamespacedName.String(),
			"targetDeployment", targetKey.String(),
			"specReplicas", specReplicas,
			"statusReplicas", currentStatusReplicas,
			"readyReplicas", readyReplicas,
			"availableReplicas", availableReplicas,
			"updatedReplicas", updatedReplicas,
			"minReplicas", minReplicas,
			"maxReplicas", maxReplicas,
			"guardrailDisposition", string(verdict.PrimaryDisposition),
			"pollingIntervalSeconds", pollingInterval,
		)
	}

	// 9. Update AgenticAutoscaler status subresource
	meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
		Type:               ConditionTypeTargetFound,
		Status:             metav1.ConditionTrue,
		Reason:             "DeploymentAvailable",
		Message:            fmt.Sprintf("Target deployment '%s' successfully inspected", targetRef.Name),
		ObservedGeneration: autoscaler.Generation,
	})
	meta.SetStatusCondition(&autoscaler.Status.Conditions, metav1.Condition{
		Type:               ConditionTypeScalingActive,
		Status:             metav1.ConditionTrue,
		Reason:             "ReconciliationSuccess",
		Message:            "AgenticAutoscaler is actively monitoring target workload metrics and replicas",
		ObservedGeneration: autoscaler.Generation,
	})

	autoscaler.Status.CurrentReplicas = currentStatusReplicas
	autoscaler.Status.ReadyReplicas = readyReplicas
	autoscaler.Status.DesiredReplicas = verdict.TargetReplicas
	autoscaler.Status.LastGuardrailAction = string(verdict.PrimaryDisposition)
	autoscaler.Status.LastGuardrailReason = verdict.SummaryReason
	autoscaler.Status.FallbackEngaged = fallbackEngaged
	autoscaler.Status.ObservedGeneration = autoscaler.Generation
	nowMeta := metav1.Now()
	autoscaler.Status.LastReconcileTime = &nowMeta

	if err := r.Status().Update(ctx, &autoscaler); err != nil {
		if apierrors.IsConflict(err) {
			logger.Info("Conflict updating AgenticAutoscaler status; requeueing", "autoscaler", req.NamespacedName)
			return ctrl.Result{Requeue: true}, nil
		}
		logger.Error(err, "Failed to update AgenticAutoscaler status", "autoscaler", req.NamespacedName)
		return ctrl.Result{}, err
	}

	logger.Info("Reconciliation finished successfully; scheduling next poll",
		"autoscaler", req.NamespacedName.String(),
		"targetDeployment", targetKey.String(),
		"desiredReplicas", verdict.TargetReplicas,
		"requeueAfterSeconds", pollingInterval,
	)

	return ctrl.Result{RequeueAfter: time.Duration(pollingInterval) * time.Second}, nil
}

// collectTelemetry queries Prometheus if accessible, or creates a standard telemetry payload.
func (r *AgenticAutoscalerReconciler) collectTelemetry(
	ctx context.Context,
	autoscaler *autoscalingv1alpha1.AgenticAutoscaler,
	deployment *appsv1.Deployment,
	specReplicas, minReplicas, maxReplicas int32,
) reasoner.ClusterMetricsPayload {
	payload := reasoner.ClusterMetricsPayload{
		Timestamp:                time.Now().UTC().Format(time.RFC3339),
		Namespace:                autoscaler.Namespace,
		WorkloadName:             autoscaler.Spec.ScaleTargetRef.Name,
		CurrentReplicas:          specReplicas,
		MinReplicas:              minReplicas,
		MaxReplicas:              maxReplicas,
		CPUUtilizationPercent:    0.0,
		MemoryUtilizationPercent: 0.0,
		HTTPRequestsPerSecond:    0.0,
		HTTPP99LatencyMS:         20.0,
		ErrorRatePercent:         0.0,
	}

	promURL := autoscaler.Spec.PrometheusURL
	if promURL == "" {
		promURL = "http://prometheus-k8s.monitoring.svc.cluster.local:9090"
	}

	// Try querying Prometheus for CPU metrics with a short timeout
	client := &http.Client{Timeout: 500 * time.Millisecond}
	query := fmt.Sprintf("sum(rate(workload_http_requests_total{namespace=\"%s\"}[1m]))", autoscaler.Namespace)
	reqURL := fmt.Sprintf("%s/api/v1/query?query=%s", promURL, url.QueryEscape(query))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err == nil {
		resp, err := client.Do(req)
		if err == nil {
			defer resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				var promResp struct {
					Data struct {
						Result []struct {
							Value []interface{} `json:"value"`
						} `json:"result"`
					} `json:"data"`
				}
				if json.NewDecoder(resp.Body).Decode(&promResp) == nil && len(promResp.Data.Result) > 0 {
					valList := promResp.Data.Result[0].Value
					if len(valList) >= 2 {
						if strVal, ok := valList[1].(string); ok {
							if floatVal, parseErr := strconv.ParseFloat(strVal, 64); parseErr == nil {
								payload.HTTPRequestsPerSecond = floatVal
								// Estimate CPU utilization proportional to request throughput if raw CPU is unavailable
								if floatVal > 0 {
									payload.CPUUtilizationPercent = floatVal * 2.0
								}
							}
						}
					}
				}
			}
		}
	}

	return payload
}

func timeFromMeta(t *metav1.Time) *time.Time {
	if t == nil || t.IsZero() {
		return nil
	}
	v := t.Time
	return &v
}

// findAutoscalersForDeployment maps changes in Deployments to AgenticAutoscalers referencing them
func (r *AgenticAutoscalerReconciler) findAutoscalersForDeployment(ctx context.Context, obj client.Object) []ctrl.Request {
	deployment, ok := obj.(*appsv1.Deployment)
	if !ok {
		return nil
	}

	var autoscalerList autoscalingv1alpha1.AgenticAutoscalerList
	if err := r.List(ctx, &autoscalerList, client.InNamespace(deployment.Namespace)); err != nil {
		return nil
	}

	var requests []ctrl.Request
	for _, aa := range autoscalerList.Items {
		if aa.Spec.ScaleTargetRef.Name == deployment.Name {
			requests = append(requests, ctrl.Request{
				NamespacedName: types.NamespacedName{
					Namespace: aa.Namespace,
					Name:      aa.Name,
				},
			})
		}
	}
	return requests
}

// SetupWithManager sets up the controller with the Manager.
func (r *AgenticAutoscalerReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&autoscalingv1alpha1.AgenticAutoscaler{}).
		Watches(
			&appsv1.Deployment{},
			handler.EnqueueRequestsFromMapFunc(r.findAutoscalersForDeployment),
			builder.WithPredicates(predicate.ResourceVersionChangedPredicate{}),
		).
		Complete(r)
}
