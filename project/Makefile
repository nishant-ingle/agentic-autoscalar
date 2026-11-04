.PHONY: all build-docker deploy test-traffic verify port-forward help undeploy

NAMESPACE_WORKLOAD := workload-system
NAMESPACE_MONITORING := monitoring

help:
	@echo "Available commands for Epic 1:"
	@echo "  make build-docker   Build the Go/Gin target microservice Docker image"
	@echo "  make deploy         Deploy lightweight Prometheus, Grafana, and target workload"
	@echo "  make test-traffic   Fire simulated synthetic traffic at the workload service"
	@echo "  make verify         Query Prometheus API to verify scraping and metric ingestion"
	@echo "  make port-forward   Open local tunnels for Workload (8080), Prometheus (9090), Grafana (3000)"
	@echo "  make undeploy       Tear down deployed manifests and Helm releases"

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
		--set alertmanager.enabled=false \
		--set prometheus-pushgateway.enabled=false \
		--set kube-state-metrics.enabled=false \
		--set prometheus-node-exporter.enabled=false \
		--set server.resources.requests.memory="256Mi" \
		--set server.resources.requests.cpu="200m"
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
	@chmod +x scripts/port-forward.sh
	@./scripts/port-forward.sh

undeploy:
	@echo "Cleaning up Epic 1 resources..."
	-kubectl delete -f k8s/service.yaml --ignore-not-found
	-kubectl delete -f k8s/deployment.yaml --ignore-not-found
	-kubectl delete -f k8s/namespace.yaml --ignore-not-found
	-helm uninstall prometheus -n $(NAMESPACE_MONITORING)
	-helm uninstall grafana -n $(NAMESPACE_MONITORING).PHONY: all build-docker deploy test-traffic verify port-forward help undeploy

NAMESPACE_WORKLOAD := workload-system
NAMESPACE_MONITORING := monitoring

help:
	@echo "Available commands for Epic 1:"
	@echo "  make build-docker   Build the Go/Gin target microservice Docker image"
	@echo "  make deploy         Deploy lightweight Prometheus, Grafana, and target workload"
	@echo "  make test-traffic   Fire simulated synthetic traffic at the workload service"
	@echo "  make verify         Query Prometheus API to verify scraping and metric ingestion"
	@echo "  make port-forward   Open local tunnels for Workload (8080), Prometheus (9090), Grafana (3000)"
	@echo "  make undeploy       Tear down deployed manifests and Helm releases"

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
		--set alertmanager.enabled=false \
		--set prometheus-pushgateway.enabled=false \
		--set kube-state-metrics.enabled=false \
		--set prometheus-node-exporter.enabled=false \
		--set server.resources.requests.memory="256Mi" \
		--set server.resources.requests.cpu="200m"
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
	-helm uninstall grafana -n $(NAMESPACE_MONITORING)helm uninstall prometheus -n $(NAMESPACE_MONITORING)
