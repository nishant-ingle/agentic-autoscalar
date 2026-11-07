.PHONY: all help port-forward deploy undeploy build-docker test-traffic verify swagger \
	app-build-docker app-docker-build app-deploy app-port-forward app-logs app-test-traffic app-verify app-swagger app-undeploy \
	operator-build operator-docker-build operator-install operator-run operator-deploy operator-logs operator-apply-sample operator-verify verify-operator operator-undeploy \
	reasoner-test reasoner-run reasoner-docker-build reasoner-deploy reasoner-logs reasoner-verify verify-reasoner reasoner-undeploy

NAMESPACE_WORKLOAD := workload-system
NAMESPACE_MONITORING := monitoring
OPERATOR_IMG ?= agentic-autoscaler:latest
REASONER_IMG ?= reasoner-service:latest
KIND_CLUSTER_NAME ?= desktop

help:
	@echo "================================================================================"
	@echo " Agentic Kubernetes Autoscaler - Component Lifecycle Targets"
	@echo "================================================================================"
	@echo "Target Microservice & Monitoring Stack (Gin App + Prometheus/Grafana):"
	@echo "  make deploy                (or make app-deploy) Deploy Prometheus, Grafana, and Gin workload"
	@echo "  make build-docker          (or make app-docker-build) Build Gin workload Docker image"
	@echo "  make app-logs              Stream multi-pod prefixed logs from target-workload pods"
	@echo "  make test-traffic          (or make app-test-traffic) Fire synthetic traffic at workload"
	@echo "  make verify                (or make app-verify) Query Prometheus to verify metric ingestion"
	@echo "  make port-forward          (or make app-port-forward) Open local tunnels (Workload:8080, Prometheus:9090, Grafana:3000)"
	@echo "  make swagger               (or make app-swagger) Generate Swagger API documentation"
	@echo "  make undeploy              (or make app-undeploy) Clean up workload and Helm releases"
	@echo ""
	@echo "Kubernetes Operator (Control Plane - operator-system):"
	@echo "  make operator-install      Install the AgenticAutoscaler CRD into the cluster"
	@echo "  make operator-build        Build the Kubebuilder controller manager host binary"
	@echo "  make operator-docker-build Build the controller manager container image"
	@echo "  make operator-run          Run the AgenticAutoscaler controller locally on host"
	@echo "  make operator-deploy       Build, load, and deploy the operator into the cluster"
	@echo "  make operator-logs         Stream logs from the in-cluster operator deployment"
	@echo "  make operator-apply-sample Apply sample AgenticAutoscaler CR pointing to target-workload"
	@echo "  make verify-operator       (or make operator-verify) Run automated test suite for Epic 2"
	@echo "  make operator-undeploy     Delete sample CR, operator deployment, and uninstall CRD"
	@echo ""
	@echo "AI Reasoning Layer (FastAPI / LangGraph):"
	@echo "  make reasoner-test         Run pytest test suite for Epic 3 FastAPI/LangGraph reasoner"
	@echo "  make reasoner-run          Run FastAPI telemetry reasoner locally on port 8000"
	@echo "  make reasoner-docker-build Build reasoner service container image"
	@echo "  make reasoner-deploy       Deploy reasoner service to cluster in workload-system"
	@echo "  make reasoner-logs         Stream logs from in-cluster reasoner service"
	@echo "  make verify-reasoner       (or make reasoner-verify) Run automated acceptance test for Epic 3"
	@echo "  make reasoner-undeploy     Delete reasoner service deployment from cluster"
	@echo "================================================================================"

# ==============================================================================
# 1. Target Microservice (Gin App) & Monitoring Targets
# ==============================================================================

build-docker:
	@echo "Building docker image..."
	cd target-service && docker build -t target-service:latest .
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image target-service:latest into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image target-service:latest --name $(KIND_CLUSTER_NAME)) || true

deploy: build-docker
	@echo "Deploying lightweight standalone Prometheus..."
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo add grafana https://grafana.github.io/helm-charts
	helm repo update
	helm upgrade --install prometheus prometheus-community/prometheus \
		--namespace $(NAMESPACE_MONITORING) --create-namespace \
		--set server.global.scrape_interval="10s" \
		--set alertmanager.enabled=false \
		--set prometheus-pushgateway.enabled=false \
		--set kube-state-metrics.enabled=false \
		--set prometheus-node-exporter.enabled=false \
		--set server.resources.requests.memory="256Mi" \
		--set server.resources.requests.cpu="200m" \
		--set configmapReload.prometheus.image.tag=v0.76.2
	@echo "Deploying lightweight standalone Grafana..."
	helm upgrade --install grafana grafana/grafana \
		--namespace $(NAMESPACE_MONITORING) \
		--set adminPassword=prom-operator
	@echo "Deploying target workload..."
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	kubectl rollout restart deployment/target-workload -n $(NAMESPACE_WORKLOAD)
	@echo "Deployment complete. (Skipped servicemonitor.yaml as we are using standalone Prometheus)"

test-traffic:
	@chmod +x scripts/test-traffic.sh
	@./scripts/test-traffic.sh http://localhost:8080 30

verify:
	@chmod +x scripts/verify-metrics.sh
	@./scripts/verify-metrics.sh http://localhost:9090

port-forward:
	@echo "Starting Port Forwards..."
	@echo "- Workload:   http://localhost:8080/healthz"
	@echo "- Prometheus: http://localhost:9090"
	@echo "- Grafana:    http://localhost:3000 (admin / prom-operator)"
	@echo "Press Ctrl+C to stop all tunnels."
	@kubectl port-forward svc/target-workload -n workload-system 8080:8080 > /dev/null 2>&1 & \
	kubectl port-forward svc/prometheus-server -n monitoring 9090:80 > /dev/null 2>&1 & \
	kubectl port-forward svc/grafana -n monitoring 3000:80 > /dev/null 2>&1 & \
	wait

undeploy:
	@echo "Cleaning up Epic 1 resources..."
	-kubectl delete -f k8s/service.yaml --ignore-not-found
	-kubectl delete -f k8s/deployment.yaml --ignore-not-found
	-kubectl delete -f k8s/namespace.yaml --ignore-not-found
	-helm uninstall prometheus -n $(NAMESPACE_MONITORING)
	-helm uninstall grafana -n $(NAMESPACE_MONITORING)

swagger:
	@echo "Generating Swagger documentation..."
	cd target-service && swag init -g cmd/server/main.go -o cmd/server/docs --parseInternal

app-logs:
	@echo "Streaming logs from target-workload pods..."
	kubectl logs -l app=target-workload -n $(NAMESPACE_WORKLOAD) -f --prefix --max-log-requests=10

# Aliases for app-* naming consistency
app-build-docker: build-docker
app-docker-build: build-docker
app-deploy: deploy
app-port-forward: port-forward
app-test-traffic: test-traffic
app-verify: verify
app-swagger: swagger
app-undeploy: undeploy

operator-build:
	@echo "Building Agentic Autoscaler controller manager..."
	cd operator && make build

operator-install:
	@echo "Installing AgenticAutoscaler CRD..."
	cd operator && make install

# Development: runs the controller locally (no leader election across pods)
operator-run:
	@echo "Starting AgenticAutoscaler controller..."
	cd operator && go run ./cmd/main.go

operator-docker-build:
	@echo "Building Agentic Autoscaler operator container image..."
	cd operator && docker build -t $(OPERATOR_IMG) .

# In-cluster deployment: builds image, loads into local cluster, and deploys via Kustomize
operator-deploy: operator-docker-build
	@echo "Ensuring image is available in local cluster..."
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image $(OPERATOR_IMG) into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image $(OPERATOR_IMG) --name $(KIND_CLUSTER_NAME)) || true
	@echo "Deploying Agentic Autoscaler controller manager to cluster..."
	cd operator && make deploy IMG=$(OPERATOR_IMG)
	@echo "Waiting for operator controller manager deployment to become ready..."
	kubectl rollout status deployment/operator-controller-manager -n operator-system --timeout=90s
	@echo "Agentic Autoscaler operator successfully deployed in operator-system namespace."

operator-logs:
	@echo "Streaming logs from Agentic Autoscaler controller manager..."
	kubectl logs -f deployment/operator-controller-manager -n operator-system

operator-apply-sample:
	@echo "Applying AgenticAutoscaler custom resource..."
	kubectl apply -f k8s/agenticautoscaler.yaml

verify-operator:
	@chmod +x scripts/verify-operator.sh
	@./scripts/verify-operator.sh workload-system

# Alias for verify-operator
operator-verify: verify-operator

operator-undeploy:
	@echo "Cleaning up AgenticAutoscaler custom resources, controller deployment, and CRD..."
	-kubectl delete -f k8s/agenticautoscaler.yaml --ignore-not-found
	-cd operator && make undeploy ignore-not-found=true
	-cd operator && make uninstall ignore-not-found=true

reasoner-test:
	@echo "Running reasoner unit and integration test suite..."
	cd reasoner && PYTHONPATH=. ../../venv/bin/pytest -v

reasoner-run:
	@echo "Starting FastAPI telemetry reasoner locally on http://localhost:8000..."
	cd reasoner && PYTHONPATH=. ../../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

reasoner-docker-build:
	@echo "Building Reasoner Docker image..."
	cd reasoner && docker build -t $(REASONER_IMG) .

reasoner-deploy: reasoner-docker-build
	@echo "Ensuring reasoner image is available in local cluster..."
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image $(REASONER_IMG) into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image $(REASONER_IMG) --name $(KIND_CLUSTER_NAME)) || true
	@echo "Deploying reasoner service to cluster..."
	kubectl apply -f k8s/reasoner-deployment.yaml
	kubectl apply -f k8s/reasoner-service.yaml
	@echo "Waiting for reasoner deployment rollout to complete..."
	kubectl rollout status deployment/reasoner-service -n $(NAMESPACE_WORKLOAD) --timeout=90s
	@echo "Reasoner service successfully deployed in $(NAMESPACE_WORKLOAD) namespace."

reasoner-logs:
	@echo "Streaming logs from Reasoner service..."
	kubectl logs -f deployment/reasoner-service -n $(NAMESPACE_WORKLOAD)

verify-reasoner:
	@chmod +x scripts/verify-reasoner.sh
	@./scripts/verify-reasoner.sh http://localhost:8000

# Alias for verify-reasoner
reasoner-verify: verify-reasoner

reasoner-undeploy:
	@echo "Cleaning up reasoner deployment and service..."
	-kubectl delete -f k8s/reasoner-service.yaml --ignore-not-found
	-kubectl delete -f k8s/reasoner-deployment.yaml --ignore-not-found
