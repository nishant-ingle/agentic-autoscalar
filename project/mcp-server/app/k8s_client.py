import logging
from typing import Dict, Any, List, Optional
from kubernetes import client, config
from app.config import settings
from app.security import validate_namespace, sanitize_tail_lines

logger = logging.getLogger(__name__)


class KubernetesClient:
    """Read-only Kubernetes client for inspecting workloads and pod logs."""

    def __init__(self):
        self._initialized = False
        self._core_api: Optional[client.CoreV1Api] = None
        self._apps_api: Optional[client.AppsV1Api] = None
        self._init_client()

    def _init_client(self) -> None:
        """Attempts in-cluster configuration first, then local kubeconfig."""
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration.")
            self._initialized = True
        except Exception:
            try:
                config.load_kube_config()
                logger.info("Loaded local ~/.kube/config configuration.")
                self._initialized = True
            except Exception as exc:
                logger.warning("Could not initialize Kubernetes client from environment: %s", exc)
                self._initialized = False

        if self._initialized:
            self._core_api = client.CoreV1Api()
            self._apps_api = client.AppsV1Api()

    def get_workload_metrics(
        self,
        namespace: str = "workload-system",
        workload_name: str = "target-workload"
    ) -> Dict[str, Any]:
        """Reads replica specs, ready counts, and pod statuses for target deployment."""
        validate_namespace(namespace)

        if not self._initialized or not self._apps_api or not self._core_api:
            if settings.mock_mode:
                return {
                    "status": "mock_success",
                    "namespace": namespace,
                    "workload_name": workload_name,
                    "desired_replicas": 2,
                    "ready_replicas": 2,
                    "available_replicas": 2,
                    "updated_replicas": 2,
                    "pods": [
                        {"name": f"{workload_name}-mock-pod-1", "phase": "Running", "restarts": 0, "ready": True},
                        {"name": f"{workload_name}-mock-pod-2", "phase": "Running", "restarts": 0, "ready": True}
                    ]
                }
            return {
                "status": "error",
                "error": "Kubernetes client not connected to cluster and mock_mode is disabled."
            }

        try:
            dep = self._apps_api.read_namespaced_deployment(name=workload_name, namespace=namespace)
            spec_replicas = dep.spec.replicas or 0
            status = dep.status
            ready_replicas = status.ready_replicas or 0
            available_replicas = status.available_replicas or 0
            updated_replicas = status.updated_replicas or 0

            # List corresponding pods using selector
            match_labels = dep.spec.selector.match_labels or {"app": workload_name}
            selector_str = ",".join([f"{k}={v}" for k, v in match_labels.items()])
            pod_list = self._core_api.list_namespaced_pod(namespace=namespace, label_selector=selector_str)

            pods_info: List[Dict[str, Any]] = []
            for pod in pod_list.items:
                restarts = 0
                is_ready = False
                if pod.status and pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        restarts += cs.restart_count
                        if cs.ready:
                            is_ready = True

                pods_info.append({
                    "name": pod.metadata.name,
                    "phase": pod.status.phase if pod.status else "Unknown",
                    "restarts": restarts,
                    "ready": is_ready,
                    "ip": pod.status.pod_ip if pod.status else None,
                    "node": pod.spec.node_name if pod.spec else None
                })

            return {
                "status": "success",
                "namespace": namespace,
                "workload_name": workload_name,
                "desired_replicas": spec_replicas,
                "ready_replicas": ready_replicas,
                "available_replicas": available_replicas,
                "updated_replicas": updated_replicas,
                "pod_count": len(pods_info),
                "pods": pods_info
            }
        except Exception as exc:
            logger.error("Failed to read workload metrics for %s/%s: %s", namespace, workload_name, exc)
            return {"status": "error", "error": str(exc), "namespace": namespace, "workload": workload_name}

    def fetch_recent_logs(
        self,
        namespace: str = "workload-system",
        workload_name: str = "target-workload",
        tail_lines: int = 50,
        container: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches recent stdout/stderr logs from the workload's active pods."""
        validate_namespace(namespace)
        safe_tail = sanitize_tail_lines(tail_lines)

        if not self._initialized or not self._core_api:
            if settings.mock_mode:
                return {
                    "status": "mock_success",
                    "namespace": namespace,
                    "workload_name": workload_name,
                    "tail_lines": safe_tail,
                    "entries": [
                        {"pod": f"{workload_name}-mock", "log": "[HTTP] 200 GET /api/workload 12ms"},
                        {"pod": f"{workload_name}-mock", "log": "[HTTP] 200 GET /healthz 1ms"}
                    ]
                }
            return {
                "status": "error",
                "error": "Kubernetes client not connected to cluster and mock_mode is disabled."
            }

        try:
            # Locate pods for deployment
            pod_list = self._core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={workload_name}"
            )
            if not pod_list.items:
                # Try fallback selector
                pod_list = self._core_api.list_namespaced_pod(namespace=namespace)
                items = [p for p in pod_list.items if workload_name in (p.metadata.name or "")]
            else:
                items = pod_list.items

            if not items:
                return {
                    "status": "warning",
                    "message": f"No active pods found for workload '{workload_name}' in namespace '{namespace}'.",
                    "entries": []
                }

            entries: List[Dict[str, Any]] = []
            for pod in items[:3]:  # inspect up to 3 pods
                pod_name = pod.metadata.name
                try:
                    kwargs = {"name": pod_name, "namespace": namespace, "tail_lines": safe_tail}
                    if container:
                        kwargs["container"] = container
                    log_text = self._core_api.read_namespaced_pod_log(**kwargs)
                    lines = [ln.strip() for ln in log_text.strip().split("\n") if ln.strip()]
                    entries.append({
                        "pod": pod_name,
                        "line_count": len(lines),
                        "lines": lines[-safe_tail:]
                    })
                except Exception as pod_err:
                    entries.append({"pod": pod_name, "error": str(pod_err)})

            return {
                "status": "success",
                "namespace": namespace,
                "workload_name": workload_name,
                "tail_lines": safe_tail,
                "pods_sampled": len(entries),
                "entries": entries
            }
        except Exception as exc:
            logger.error("Failed to fetch logs for %s/%s: %s", namespace, workload_name, exc)
            return {"status": "error", "error": str(exc), "namespace": namespace, "workload": workload_name}


k8s_client = KubernetesClient()
