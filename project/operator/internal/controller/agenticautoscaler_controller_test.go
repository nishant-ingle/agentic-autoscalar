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
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	autoscalingv1alpha1 "github.com/nishant-ingle/agentic-autoscaler/api/v1alpha1"
	"github.com/nishant-ingle/agentic-autoscaler/internal/guardrails"
	"github.com/nishant-ingle/agentic-autoscaler/internal/reasoner"
)

type mockHTTPDoer struct {
	doFunc func(req *http.Request) (*http.Response, error)
}

func (m *mockHTTPDoer) Do(req *http.Request) (*http.Response, error) {
	return m.doFunc(req)
}

var _ = Describe("AgenticAutoscaler Controller & Epic 6 Guardrails", func() {
	var (
		ctx                context.Context
		autoscalerName     = "epic6-test-autoscaler"
		deploymentName     = "epic6-test-workload"
		namespace          = "default"
		typeNamespacedName types.NamespacedName
		depNamespacedName  types.NamespacedName
		fakeRecorder       *record.FakeRecorder
	)

	BeforeEach(func() {
		ctx = context.Background()
		typeNamespacedName = types.NamespacedName{Name: autoscalerName, Namespace: namespace}
		depNamespacedName = types.NamespacedName{Name: deploymentName, Namespace: namespace}
		fakeRecorder = record.NewFakeRecorder(50)
	})

	AfterEach(func() {
		// Clean up custom resource and deployment after each spec
		aa := &autoscalingv1alpha1.AgenticAutoscaler{}
		if err := k8sClient.Get(ctx, typeNamespacedName, aa); err == nil {
			_ = k8sClient.Delete(ctx, aa)
		}

		dep := &appsv1.Deployment{}
		if err := k8sClient.Get(ctx, depNamespacedName, dep); err == nil {
			_ = k8sClient.Delete(ctx, dep)
		}
	})

	It("should report TargetNotFound when target deployment is missing", func() {
		aa := &autoscalingv1alpha1.AgenticAutoscaler{
			ObjectMeta: metav1.ObjectMeta{Name: autoscalerName, Namespace: namespace},
			Spec: autoscalingv1alpha1.AgenticAutoscalerSpec{
				ScaleTargetRef: autoscalingv1alpha1.CrossVersionObjectReference{
					Kind: "Deployment",
					Name: "non-existent-deployment",
				},
				MaxReplicas: 5,
			},
		}
		Expect(k8sClient.Create(ctx, aa)).To(Succeed())

		controllerReconciler := &AgenticAutoscalerReconciler{
			Client:            k8sClient,
			Scheme:            k8sClient.Scheme(),
			Recorder:          fakeRecorder,
			GuardrailPipeline: guardrails.NewGuardrailPipeline(),
		}

		result, err := controllerReconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())
		Expect(result.RequeueAfter).To(BeNumerically(">", 0))

		updated := &autoscalingv1alpha1.AgenticAutoscaler{}
		Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
		Expect(updated.Status.Conditions).NotTo(BeEmpty())

		var foundCondition *metav1.Condition
		for i := range updated.Status.Conditions {
			if updated.Status.Conditions[i].Type == ConditionTypeTargetFound {
				foundCondition = &updated.Status.Conditions[i]
				break
			}
		}
		Expect(foundCondition).NotTo(BeNil())
		Expect(foundCondition.Status).To(Equal(metav1.ConditionFalse))
		Expect(foundCondition.Reason).To(Equal("DeploymentNotFound"))
	})

	Context("With active target deployment", func() {
		BeforeEach(func() {
			initialReplicas := int32(2)
			dep := &appsv1.Deployment{
				ObjectMeta: metav1.ObjectMeta{Name: deploymentName, Namespace: namespace},
				Spec: appsv1.DeploymentSpec{
					Replicas: &initialReplicas,
					Selector: &metav1.LabelSelector{
						MatchLabels: map[string]string{"app": "test-workload"},
					},
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Labels: map[string]string{"app": "test-workload"},
						},
						Spec: corev1.PodSpec{
							Containers: []corev1.Container{
								{Name: "app", Image: "busybox", Command: []string{"sleep", "3600"}},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, dep)).To(Succeed())
		})

		It("Acceptance Criteria 1: successfully clamps/rejects replica recommendations exceeding maxReplicas", func() {
			// Mock reasoner returning an excessive recommendation of 10 replicas (maxReplicas is 5)
			mockHTTP := &mockHTTPDoer{
				doFunc: func(req *http.Request) (*http.Response, error) {
					jsonResp := `{
						"workload_name": "epic6-test-workload",
						"namespace": "default",
						"current_replicas": 2,
						"target_replicas": 10,
						"action": "SCALE_UP",
						"reasoning": "Hallucinatory traffic spike perceived; proposing 10 replicas",
						"confidence_score": 0.99,
						"primary_metric_driver": "CPU_UTILIZATION",
						"is_fallback": false,
						"model_used": "mock-llm"
					}`
					return &http.Response{
						StatusCode: http.StatusOK,
						Body:       io.NopCloser(bytes.NewBufferString(jsonResp)),
					}, nil
				},
			}

			cooldownZero := int32(0)
			aa := &autoscalingv1alpha1.AgenticAutoscaler{
				ObjectMeta: metav1.ObjectMeta{Name: autoscalerName, Namespace: namespace},
				Spec: autoscalingv1alpha1.AgenticAutoscalerSpec{
					ScaleTargetRef: autoscalingv1alpha1.CrossVersionObjectReference{
						Kind: "Deployment",
						Name: deploymentName,
					},
					MinReplicas:           &[]int32{1}[0],
					MaxReplicas:           5,
					CooldownPeriodSeconds: &cooldownZero,
					ReasonerURL:           "http://mock-reasoner/evaluate-scaling",
				},
			}
			Expect(k8sClient.Create(ctx, aa)).To(Succeed())

			controllerReconciler := &AgenticAutoscalerReconciler{
				Client:            k8sClient,
				Scheme:            k8sClient.Scheme(),
				Recorder:          fakeRecorder,
				ReasonerClient:    reasoner.NewClient(3*time.Second, mockHTTP),
				GuardrailPipeline: guardrails.NewGuardrailPipeline(),
			}

			result, err := controllerReconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(BeNumerically(">", 0))

			// Verify target deployment was scaled to exactly maxReplicas (5) and NOT 10
			dep := &appsv1.Deployment{}
			Expect(k8sClient.Get(ctx, depNamespacedName, dep)).To(Succeed())
			Expect(*dep.Spec.Replicas).To(Equal(int32(5)))

			// Verify CR status reflects guardrail clamping and conditions
			updatedAA := &autoscalingv1alpha1.AgenticAutoscaler{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updatedAA)).To(Succeed())
			Expect(updatedAA.Status.DesiredReplicas).To(Equal(int32(5)))
			Expect(updatedAA.Status.LastGuardrailAction).To(Equal("CLAMPED"))
			Expect(updatedAA.Status.LastGuardrailReason).To(ContainSubstring("exceeds maxReplicas ceiling (5); clamped down to 5"))

			// Verify GuardrailApplied condition is True
			var guardrailCondition *metav1.Condition
			for i := range updatedAA.Status.Conditions {
				if updatedAA.Status.Conditions[i].Type == ConditionTypeGuardrailApplied {
					guardrailCondition = &updatedAA.Status.Conditions[i]
					break
				}
			}
			Expect(guardrailCondition).NotTo(BeNil())
			Expect(guardrailCondition.Status).To(Equal(metav1.ConditionTrue))
		})

		It("Acceptance Criteria 2: cooldown and hysteresis window prevents rapid oscillation (flapping)", func() {
			// Step A: First reconciliation triggers a scale-up from 2 to 4
			mockHTTPScaleUp := &mockHTTPDoer{
				doFunc: func(req *http.Request) (*http.Response, error) {
					jsonResp := `{
						"workload_name": "epic6-test-workload",
						"namespace": "default",
						"current_replicas": 2,
						"target_replicas": 4,
						"action": "SCALE_UP",
						"reasoning": "Legitimate load increase; scaling up to 4 replicas",
						"confidence_score": 0.90,
						"primary_metric_driver": "CPU_UTILIZATION",
						"is_fallback": false,
						"model_used": "mock-llm"
					}`
					return &http.Response{
						StatusCode: http.StatusOK,
						Body:       io.NopCloser(bytes.NewBufferString(jsonResp)),
					}, nil
				},
			}

			cooldown60 := int32(60)
			hysteresis600 := int32(600) // 10 minutes
			aa := &autoscalingv1alpha1.AgenticAutoscaler{
				ObjectMeta: metav1.ObjectMeta{Name: autoscalerName, Namespace: namespace},
				Spec: autoscalingv1alpha1.AgenticAutoscalerSpec{
					ScaleTargetRef: autoscalingv1alpha1.CrossVersionObjectReference{
						Kind: "Deployment",
						Name: deploymentName,
					},
					MinReplicas:                &[]int32{1}[0],
					MaxReplicas:                5,
					CooldownPeriodSeconds:      &cooldown60,
					ScaleDownHysteresisSeconds: &hysteresis600,
					ReasonerURL:                "http://mock-reasoner/evaluate-scaling",
				},
			}
			Expect(k8sClient.Create(ctx, aa)).To(Succeed())

			reconciler := &AgenticAutoscalerReconciler{
				Client:            k8sClient,
				Scheme:            k8sClient.Scheme(),
				Recorder:          fakeRecorder,
				ReasonerClient:    reasoner.NewClient(3*time.Second, mockHTTPScaleUp),
				GuardrailPipeline: guardrails.NewGuardrailPipeline(),
			}

			_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			// Deployment is now at 4 replicas
			dep := &appsv1.Deployment{}
			Expect(k8sClient.Get(ctx, depNamespacedName, dep)).To(Succeed())
			Expect(*dep.Spec.Replicas).To(Equal(int32(4)))

			// Step B: Immediate fluctuating load suggests scale-down from 4 back to 2 (within 10m hysteresis & 60s cooldown)
			mockHTTPScaleDown := &mockHTTPDoer{
				doFunc: func(req *http.Request) (*http.Response, error) {
					jsonResp := `{
						"workload_name": "epic6-test-workload",
						"namespace": "default",
						"current_replicas": 4,
						"target_replicas": 2,
						"action": "SCALE_DOWN",
						"reasoning": "Load dropped momentarily; proposing scale down",
						"confidence_score": 0.85,
						"primary_metric_driver": "CPU_UTILIZATION",
						"is_fallback": false,
						"model_used": "mock-llm"
					}`
					return &http.Response{
						StatusCode: http.StatusOK,
						Body:       io.NopCloser(bytes.NewBufferString(jsonResp)),
					}, nil
				},
			}

			reconciler.ReasonerClient = reasoner.NewClient(3*time.Second, mockHTTPScaleDown)

			_, err = reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			// Scale-down MUST be rejected by hysteresis/cooldown, leaving replicas at 4!
			Expect(k8sClient.Get(ctx, depNamespacedName, dep)).To(Succeed())
			Expect(*dep.Spec.Replicas).To(Equal(int32(4)))

			updatedAA := &autoscalingv1alpha1.AgenticAutoscaler{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updatedAA)).To(Succeed())
			Expect(updatedAA.Status.DesiredReplicas).To(Equal(int32(4)))
			Expect(updatedAA.Status.LastGuardrailAction).To(Equal("REJECTED"))
			Expect(updatedAA.Status.LastGuardrailReason).To(ContainSubstring("Scale-down from 4 to 2 rejected: prior scale-up occurred"))
		})

		It("Acceptance Criteria 3: system safely defaults to fallback reactive HPA behavior during simulated reasoning outages", func() {
			// Simulate reasoning service timeout / connection failure
			mockOutage := &mockHTTPDoer{
				doFunc: func(req *http.Request) (*http.Response, error) {
					return nil, errors.New("connection refused: simulated reasoning service outage")
				},
			}

			cooldownZero := int32(0)
			aa := &autoscalingv1alpha1.AgenticAutoscaler{
				ObjectMeta: metav1.ObjectMeta{Name: autoscalerName, Namespace: namespace},
				Spec: autoscalingv1alpha1.AgenticAutoscalerSpec{
					ScaleTargetRef: autoscalingv1alpha1.CrossVersionObjectReference{
						Kind: "Deployment",
						Name: deploymentName,
					},
					MinReplicas:           &[]int32{1}[0],
					MaxReplicas:           5,
					CooldownPeriodSeconds: &cooldownZero,
					ReasonerURL:           "http://failing-reasoner-service/evaluate-scaling",
				},
			}
			Expect(k8sClient.Create(ctx, aa)).To(Succeed())

			reconciler := &AgenticAutoscalerReconciler{
				Client:            k8sClient,
				Scheme:            k8sClient.Scheme(),
				Recorder:          fakeRecorder,
				ReasonerClient:    reasoner.NewClient(3*time.Second, mockOutage),
				GuardrailPipeline: guardrails.NewGuardrailPipeline(),
			}

			result, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(BeNumerically(">", 0))

			// Verify fallback engaged flag and reasoner outage conditions
			updatedAA := &autoscalingv1alpha1.AgenticAutoscaler{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updatedAA)).To(Succeed())
			Expect(updatedAA.Status.FallbackEngaged).To(BeTrue())

			var reasonerCondition *metav1.Condition
			for i := range updatedAA.Status.Conditions {
				if updatedAA.Status.Conditions[i].Type == ConditionTypeReasonerHealthy {
					reasonerCondition = &updatedAA.Status.Conditions[i]
					break
				}
			}
			Expect(reasonerCondition).NotTo(BeNil())
			Expect(reasonerCondition.Status).To(Equal(metav1.ConditionFalse))
			Expect(reasonerCondition.Reason).To(Equal("ReasonerServiceOutage"))

			// Verify event was recorded
			Expect(fakeRecorder.Events).NotTo(BeEmpty())
		})
	})
})
