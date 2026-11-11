.PHONY: all help port-forward deploy undeploy build-docker test-traffic verify swagger \
	app-build-docker app-docker-build app-deploy app-port-forward app-logs app-test-traffic app-verify app-swagger app-undeploy app-test test-app \
	operator-manifests operator-generate operator-test operator-build operator-docker-build operator-install operator-run operator-deploy operator-logs operator-apply-sample operator-verify verify-operator operator-undeploy \
	reasoner-test reasoner-run reasoner-docker-build reasoner-deploy reasoner-logs reasoner-verify verify-reasoner reasoner-port-forward reasoner-undeploy \
	mcp-test mcp-run mcp-docker-build mcp-deploy mcp-logs mcp-verify verify-mcp mcp-port-forward mcp-undeploy \
	rag-test rag-seed rag-docker-build rag-deploy rag-logs rag-verify verify-rag rag-clean-db rag-port-forward rag-undeploy \
	guardrails-test operator-guardrails-test verify-guardrails guardrails-verify epic6-verify

NAMESPACE_WORKLOAD := workload-system
NAMESPACE_MONITORING := monitoring
OPERATOR_IMG ?= agentic-autoscaler:latest
REASONER_IMG ?= reasoner-service:latest
MCP_IMG ?= mcp-server:latest
RAG_IMG ?= rag-syn-generator:latest
PGVECTOR_IMG ?= pgvector/pgvector:pg16
KIND_CLUSTER_NAME ?= desktop

all: help

help:
	@echo "================================================================================"
	@echo " Agentic Kubernetes Autoscaler - Component Lifecycle Targets"
	@echo "================================================================================"
	@echo "Target Microservice & Monitoring Stack (Gin App + Prometheus/Grafana):"
	@echo "  make deploy                (or make app-deploy) Deploy Prometheus, Grafana, and Gin workload"
	@echo "  make build-docker          (or make app-docker-build) Build Gin workload Docker image"
	@echo "  make app-test              (or make test-app) Run Gin workload Go unit tests"
	@echo "  make app-logs              Stream multi-pod prefixed logs from target-workload pods"
	@echo "  make test-traffic          (or make app-test-traffic) Fire synthetic traffic at workload"
	@echo "  make verify                (or make app-verify) Query Prometheus to verify metric ingestion"
	@echo "  make port-forward          (or make app-port-forward) Open local tunnels (Workload:8080, Prometheus:9090, Grafana:3000)"
	@echo "  make swagger               (or make app-swagger) Generate Swagger API documentation"
	@echo "  make undeploy              (or make app-undeploy) Clean up workload and Helm releases"
	@echo ""
	@echo "Kubernetes Operator (Control Plane - operator-system):"
	@echo "  make operator-manifests    Generate CRD manifests and RBAC using controller-gen"
	@echo "  make operator-generate     Generate DeepCopy code for Custom Resource API types"
	@echo "  make operator-test         Run operator controller unit and integration tests"
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
	@echo "  make reasoner-port-forward Port-forward in-cluster reasoner service to localhost:8000"
	@echo "  make reasoner-undeploy     Delete reasoner service deployment from cluster"
	@echo ""
	@echo "Model Context Protocol (MCP) Server (Epic 4 - k8s & Prometheus tools):"
	@echo "  make mcp-test              Run pytest test suite for Epic 4 MCP Server"
	@echo "  make mcp-run               Run MCP server locally on http://localhost:8001"
	@echo "  make mcp-docker-build      Build MCP server container image"
	@echo "  make mcp-deploy            Deploy MCP server to cluster in workload-system"
	@echo "  make mcp-logs              Stream logs from in-cluster MCP server"
	@echo "  make verify-mcp            (or make mcp-verify) Run automated acceptance test for Epic 4"
	@echo "  make mcp-port-forward      Port-forward in-cluster MCP server to localhost:8001"
	@echo "  make mcp-undeploy          Delete MCP server deployment, service, and RBAC"
	@echo ""
	@echo "Operational Memory & RAG Pipeline (Epic 5 - pgvector & Synthetic SRE Runbooks):"
	@echo "  make rag-test              Run pytest test suite for Epic 5 RAG pipeline"
	@echo "  make rag-seed              Seed synthetic SRE incidents and embeddings into pgvector"
	@echo "  make rag-verify            (or make verify-rag) Query PostgreSQL to verify vector embeddings"
	@echo "  make rag-docker-build      Build RAG synthetic generator container image"
	@echo "  make rag-deploy            Deploy and run RAG seeding Job in cluster"
	@echo "  make rag-logs              Stream logs from in-cluster RAG seeding Job"
	@echo "  make rag-clean-db          Truncate and reset rag_documents table in local database"
	@echo "  make rag-port-forward      Port-forward in-cluster PostgreSQL (pgvector) to localhost:5432"
	@echo "  make rag-undeploy          Delete RAG seeding Job and ConfigMap from cluster"
	@echo ""
	@echo "Deterministic Guardrails & Safety Barrier (Epic 6 - Go Controller):"
	@echo "  make guardrails-test       (or make operator-guardrails-test) Run guardrails and reasoner unit tests"
	@echo "  make verify-guardrails     (or make guardrails-verify, epic6-verify) Run Epic 6 acceptance verification"
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
	@if ! curl -s --max-time 1 http://localhost:8080/healthz > /dev/null 2>&1; then \
		echo "ERROR: No port-forward on localhost:8080. Run 'make port-forward' first (or kubectl port-forward svc/target-workload -n workload-system 8080:8080)."; \
		exit 1; \
	fi
	@./scripts/test-traffic.sh service 30

# Run round-robin or skewed traffic from INSIDE the cluster.
# Pod IPs (10.244.x.x) are not routable from the Mac host — this Job runs curl inside K8s.
# Override: make app-test-traffic-job MODE=skewed DURATION_SECS=120
MODE ?= service
DURATION_SECS ?= 60
app-test-traffic-job:
	@echo "Deploying traffic-generator RBAC + Job (mode=$(MODE), duration=$(DURATION_SECS)s)..."
	@# Apply RBAC resources (ServiceAccount, Role, RoleBinding) — safe to re-apply at any time
	@kubectl apply -f k8s/traffic-job.yaml
	@# Job pod templates are immutable — delete the old Job before recreating with new env values
	@kubectl delete job traffic-generator -n workload-system --ignore-not-found
	@# Render the manifest with the requested env values and create the Job fresh
	@sed \
		-e '/name: MODE/{' -e 'n' -e 's|value:.*|value: "$(MODE)"|' -e '}' \
		-e '/name: DURATION_SECS/{' -e 'n' -e 's|value:.*|value: "$(DURATION_SECS)"|' -e '}' \
		k8s/traffic-job.yaml | kubectl apply -f -
	@echo "Waiting for Job pod to become ready..."
	@kubectl wait --for=condition=ready pod -l app=traffic-generator -n workload-system --timeout=60s 2>/dev/null || true
	@echo "Streaming logs (Ctrl+C to detach):"
	@kubectl logs -f -l app=traffic-generator -n workload-system 2>/dev/null || true

app-test-traffic-job-delete:
	@kubectl delete job traffic-generator -n workload-system --ignore-not-found

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
	-kubectl delete ns $(NAMESPACE_MONITORING)

swagger:
	@echo "Generating Swagger documentation..."
	cd target-service && swag init -g cmd/server/main.go -o cmd/server/docs --parseInternal

app-logs:
	@echo "Streaming logs from target-workload pods..."
	kubectl logs -l app=target-workload -n $(NAMESPACE_WORKLOAD) -f --prefix --max-log-requests=10

app-test:
	@echo "Running target microservice unit tests..."
	cd target-service && go test -v ./...

test-app: app-test

# Aliases for app-* naming consistency
app-build-docker: build-docker
app-docker-build: build-docker
app-deploy: deploy
app-port-forward: port-forward
app-test-traffic: app-test-traffic-job
app-verify: verify
app-swagger: swagger
app-undeploy: undeploy

operator-manifests:
	@echo "Generating Kubernetes manifests (CRDs, RBAC) for operator..."
	cd operator && make manifests

operator-generate:
	@echo "Generating DeepCopy code for operator API types..."
	cd operator && make generate

operator-test:
	@echo "Running operator test suite..."
	cd operator && make test

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
	@echo "Ensuring namespace $(NAMESPACE_WORKLOAD) exists..."
	kubectl apply -f k8s/namespace.yaml
	@echo "Configuring in-cluster LLM credentials secret (if available in .env or environment)..."
	@API_KEY=$$(grep -E "^OPENAI_API_KEY=" ../.env .env 2>/dev/null | head -n 1 | cut -d "=" -f2- | tr -d "\"'" || true); \
	if [ -z "$$API_KEY" ]; then API_KEY="$$OPENAI_API_KEY"; fi; \
	API_BASE=$$(grep -E "^OPENAI_API_BASE=" ../.env .env 2>/dev/null | head -n 1 | cut -d "=" -f2- | tr -d "\"'" || true); \
	if [ -z "$$API_BASE" ]; then API_BASE="$${OPENAI_API_BASE:-https://api.openai.com/v1}"; fi; \
	if [ -n "$$API_KEY" ]; then \
		echo "Detected OPENAI_API_KEY. Creating/updating Kubernetes secret 'reasoner-llm-secret' in $(NAMESPACE_WORKLOAD)..."; \
		kubectl create secret generic reasoner-llm-secret \
			--namespace $(NAMESPACE_WORKLOAD) \
			--from-literal=OPENAI_API_KEY="$$API_KEY" \
			--from-literal=OPENAI_API_BASE="$$API_BASE" \
			--dry-run=client -o yaml | kubectl apply -f - ; \
	else \
		echo "No OPENAI_API_KEY detected in .env or environment; deploying reasoner in deterministic heuristic fallback mode."; \
	fi
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

reasoner-port-forward:
	@echo "Port-forwarding Reasoner service to http://localhost:8000..."
	kubectl port-forward svc/reasoner-service -n $(NAMESPACE_WORKLOAD) 8000:8000

reasoner-undeploy:
	@echo "Cleaning up reasoner deployment, service, and credentials..."
	-kubectl delete -f k8s/reasoner-service.yaml --ignore-not-found
	-kubectl delete -f k8s/reasoner-deployment.yaml --ignore-not-found
	-kubectl delete secret reasoner-llm-secret -n $(NAMESPACE_WORKLOAD) --ignore-not-found

# ==============================================================================
# 4. Model Context Protocol (MCP) Server Targets
# ==============================================================================

mcp-test:
	@echo "Running MCP Server test suite..."
	cd mcp-server && PYTHONPATH=. ../../venv/bin/pytest -v

mcp-run:
	@echo "Starting MCP Server locally on http://localhost:8001 (SSE Transport /sse)..."
	cd mcp-server && PYTHONPATH=. ../../venv/bin/python main.py --transport sse --port 8001

mcp-docker-build:
	@echo "Building MCP Server Docker image..."
	cd mcp-server && docker build -t $(MCP_IMG) .

mcp-deploy: mcp-docker-build
	@echo "Ensuring MCP Server image is available in local cluster..."
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image $(MCP_IMG) into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image $(MCP_IMG) --name $(KIND_CLUSTER_NAME)) || true
	@echo "Deploying MCP Server RBAC, Deployment, and Service to cluster..."
	kubectl apply -f k8s/mcp-server-rbac.yaml
	kubectl apply -f k8s/mcp-server-deployment.yaml
	kubectl apply -f k8s/mcp-server-service.yaml
	@echo "Waiting for MCP Server deployment rollout to complete..."
	kubectl rollout status deployment/mcp-server -n $(NAMESPACE_WORKLOAD) --timeout=90s
	@echo "MCP Server successfully deployed in $(NAMESPACE_WORKLOAD) namespace."

mcp-logs:
	@echo "Streaming logs from MCP Server..."
	kubectl logs -f deployment/mcp-server -n $(NAMESPACE_WORKLOAD)

verify-mcp:
	@chmod +x scripts/verify-mcp.sh
	@./scripts/verify-mcp.sh http://localhost:8001

# Alias for verify-mcp
mcp-verify: verify-mcp

mcp-port-forward:
	@echo "Port-forwarding MCP Server to http://localhost:8001..."
	kubectl port-forward svc/mcp-server -n $(NAMESPACE_WORKLOAD) 8001:8001

mcp-undeploy:
	@echo "Cleaning up MCP Server resources..."
	-kubectl delete -f k8s/mcp-server-service.yaml --ignore-not-found
	-kubectl delete -f k8s/mcp-server-deployment.yaml --ignore-not-found
	-kubectl delete -f k8s/mcp-server-rbac.yaml --ignore-not-found

# ==============================================================================
# 5. Operational Memory & RAG Targets (Epic 5 - pgvector & Synthetic SRE Runbooks)
# ==============================================================================

rag-test:
	@echo "Running Epic 5 RAG test suite..."
	cd rag && PYTHONPATH=. ../../venv/bin/pytest tests/epic5/test_approach_syn_generator.py -v

rag-seed:
	@echo "Seeding synthetic SRE incidents and generating embeddings into pgvector..."
	cd rag && PYTHONPATH=. ../../venv/bin/python -m epic5.approach_syn_generator epic5/config.yaml

rag-verify:
	@echo "Verifying documents and embeddings in pgvector..."
	@kubectl exec deployment/postgres -n $(NAMESPACE_WORKLOAD) -- psql -U agentic_autoscalar -d agentic_autoscalar_db -c "SELECT id, title, vector_dims(embedding) AS dims, created_at FROM rag_documents;" 2>/dev/null || \
		psql -U agentic_autoscalar -d agentic_autoscalar_db -c "SELECT id, title, vector_dims(embedding) AS dims, created_at FROM rag_documents;"

verify-rag: rag-verify

rag-docker-build:
	@echo "Building RAG Synthetic Generator Docker image..."
	cd rag && docker build -t $(RAG_IMG) .

rag-deploy: rag-docker-build
	@echo "Ensuring RAG Generator and pgvector images are available in local cluster..."
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image $(RAG_IMG) into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image $(RAG_IMG) --name $(KIND_CLUSTER_NAME)) || true
	@which kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q "^$(KIND_CLUSTER_NAME)$$" && \
		(echo "Loading image $(PGVECTOR_IMG) into Kind cluster '$(KIND_CLUSTER_NAME)'..." && kind load docker-image $(PGVECTOR_IMG) --name $(KIND_CLUSTER_NAME)) || true
	@echo "Ensuring namespace $(NAMESPACE_WORKLOAD) exists..."
	kubectl apply -f k8s/namespace.yaml
	@echo "Deploying in-cluster PostgreSQL (pgvector) container..."
	kubectl apply -f k8s/postgres-deployment.yaml
	@echo "Waiting for in-cluster PostgreSQL to become ready..."
	kubectl rollout status deployment/postgres -n $(NAMESPACE_WORKLOAD) --timeout=90s
	@echo "Applying RAG ConfigMap and seeding Job..."
	-kubectl delete job rag-syn-job -n $(NAMESPACE_WORKLOAD) --ignore-not-found
	-kubectl delete configmap rag-synthetic-schema -n $(NAMESPACE_WORKLOAD) --ignore-not-found
	kubectl apply -f rag/k8s/rag-syn-job.yaml
	@echo "Waiting for RAG seeding job to complete..."
	kubectl wait --for=condition=complete --timeout=120s job/rag-syn-job -n $(NAMESPACE_WORKLOAD) || true

rag-logs:
	@echo "Streaming logs from RAG Job..."
	kubectl logs job/rag-syn-job -n $(NAMESPACE_WORKLOAD)

rag-clean-db:
	@echo "Cleaning up rag_documents table in database..."
	@kubectl exec deployment/postgres -n $(NAMESPACE_WORKLOAD) -- psql -U agentic_autoscalar -d agentic_autoscalar_db -c "TRUNCATE TABLE rag_documents RESTART IDENTITY;" 2>/dev/null || \
		psql -U agentic_autoscalar -d agentic_autoscalar_db -c "TRUNCATE TABLE rag_documents RESTART IDENTITY;"

rag-port-forward:
	@echo "Port-forwarding PostgreSQL (pgvector) to localhost:5432..."
	kubectl port-forward svc/postgres -n $(NAMESPACE_WORKLOAD) 5432:5432

rag-undeploy:
	@echo "Deleting RAG Job, ConfigMap, and in-cluster PostgreSQL deployment..."
	-kubectl delete -f rag/k8s/rag-syn-job.yaml --ignore-not-found
	-kubectl delete -f k8s/postgres-deployment.yaml --ignore-not-found

# ==============================================================================
# 6. Deterministic Guardrails & Safety Barrier (Epic 6 - Go Controller Pipeline)
# ==============================================================================

guardrails-test:
	@echo "Running Epic 6 deterministic guardrails and reasoner test suites..."
	cd operator && go test -v ./internal/guardrails/... ./internal/reasoner/...

operator-guardrails-test: guardrails-test

verify-guardrails:
	@chmod +x scripts/verify-guardrails.sh
	@./scripts/verify-guardrails.sh

guardrails-verify: verify-guardrails
epic6-verify: verify-guardrails


