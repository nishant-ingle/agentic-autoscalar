import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Kubernetes & Metrics MCP Server."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    mcp_server_name: str = "k8s-metrics-mcp-server"
    mcp_server_version: str = "1.0.0"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001

    # In local development: http://localhost:9090
    # In cluster: http://prometheus-server.monitoring.svc.cluster.local:80
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

    default_namespace: str = "workload-system"
    allowed_namespaces: List[str] = ["workload-system", "default", "monitoring"]

    # Security policy: strict read-only enforcement
    read_only_mode: bool = True
    max_log_lines: int = 200

    # Test/Mock fallback flag for environments without direct cluster access
    mock_mode: bool = False
    log_level: str = "INFO"


settings = Settings()
