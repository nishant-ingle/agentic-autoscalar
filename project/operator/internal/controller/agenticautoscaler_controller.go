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
	"fmt"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	meta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/builder"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/predicate"

	autoscalingv1alpha1 "github.com/nishant-ingle/agentic-autoscaler/api/v1alpha1"
)

const (
	// DefaultPollingIntervalSeconds is the fallback reconciliation polling interval
	DefaultPollingIntervalSeconds int32 = 15
	// ConditionTypeTargetFound indicates whether the target deployment was successfully found
	ConditionTypeTargetFound = "TargetFound"
	// ConditionTypeScalingActive indicates whether the autoscaler is actively monitoring and able to scale
	ConditionTypeScalingActive = "ScalingActive"
)

// AgenticAutoscalerReconciler reconciles a AgenticAutoscaler object
type AgenticAutoscalerReconciler struct {
	client.Client
	Scheme *runtime.Scheme
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

	// 2. Parse configuration and constraints
	pollingInterval := DefaultPollingIntervalSeconds
	if autoscaler.Spec.PollingIntervalSeconds != nil && *autoscaler.Spec.PollingIntervalSeconds > 0 {
		pollingInterval = *autoscaler.Spec.PollingIntervalSeconds
	}

	minReplicas := int32(1)
	if autoscaler.Spec.MinReplicas != nil && *autoscaler.Spec.MinReplicas > 0 {
		minReplicas = *autoscaler.Spec.MinReplicas
	}
	maxReplicas := autoscaler.Spec.MaxReplicas

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

	// 5. Emit structured log reflecting current target deployment states
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
		"pollingIntervalSeconds", pollingInterval,
	)

	// 6. Update AgenticAutoscaler status subresource
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
	autoscaler.Status.DesiredReplicas = specReplicas
	autoscaler.Status.ObservedGeneration = autoscaler.Generation
	now := metav1.Now()
	autoscaler.Status.LastReconcileTime = &now

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
		"requeueAfterSeconds", pollingInterval,
	)

	return ctrl.Result{RequeueAfter: time.Duration(pollingInterval) * time.Second}, nil
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
