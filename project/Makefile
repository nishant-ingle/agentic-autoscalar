.PHONY: all build-docker deploy test-traffic verify port-forward help undeploy swagger operator-build operator-install operator-run operator-apply-sample operator-undeploy verify-operator operator-docker-build operator-deploy operator-logs

NAMESPACE_WORKLOAD := workload-system
NAMESPACE_MONITORING := monitoring
OPERATOR_IMG ?= agentic-autoscaler:latest
KIND_CLUSTER_NAME ?= desktop

help:
	@echo "Available commands for Epic 1 & 2:"
	@echo "  make build-docker          Build the Go/Gin target microservice Docker image"
	@echo "  make deploy                Deploy lightweight Prometheus, Grafana, and target workload"
	@echo "  make test-traffic          Fire simulated synthetic traffic at the workload service"
	@echo "  make verify                Query Prometheus API to verify scraping and metric ingestion"
	@echo "  make port-forward          Open local tunnels for Workload (8080), Prometheus (9090), Grafana (3000)"
	@echo "  make undeploy              Tear down deployed manifests and Helm releases"
	@echo "  make operator-install      Install the AgenticAutoscaler CRD into the cluster"
	@echo "  make operator-build        Build the Kubebuilder controller manager binary"
	@echo "  make operator-docker-build Build the controller manager container image"
	@echo "  make operator-run          Run the AgenticAutoscaler controller locally on host"
	@echo "  make operator-deploy       Build, load, and deploy the operator into the cluster"
	@echo "  make operator-logs         Stream logs from the in-cluster operator deployment"
	@echo "  make operator-apply-sample Apply sample AgenticAutoscaler CR pointing to target-workload"
	@echo "  make verify-operator       Run automated test suite for Epic 2 controller & CRD"
	@echo "  make operator-undeploy     Delete sample CR, operator deployment, and uninstall CRD"

build-docker:
	@echo "Building docker image..."
	cd target-service && docker build -t target-service:latest .

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

operator-undeploy:
	@echo "Cleaning up AgenticAutoscaler custom resources, controller deployment, and CRD..."
	-kubectl delete -f k8s/agenticautoscaler.yaml --ignore-not-found
	-cd operator && make undeploy ignore-not-found=true
	-cd operator && make uninstall ignore-not-found=true
