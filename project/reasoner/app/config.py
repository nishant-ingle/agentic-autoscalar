import os
import yaml
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings

# Automatically locate and load the root repository .env
ENV_FILE_PATH = find_dotenv()
if ENV_FILE_PATH:
    load_dotenv(ENV_FILE_PATH)


class Settings(BaseSettings):
    service_name: str = "agentic-autoscaler-reasoner"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    timeout_seconds: float = 15.0

    # Provider settings
    llm_provider: str = "openai"
    llm_temperature: float = 0.1
    llm_model: str = "gpt-4o-mini"
    max_retries: int = 2

    # Target thresholds
    target_cpu_percent: float = 65.0
    target_memory_percent: float = 75.0
    latency_spike_threshold_ms: float = 250.0
    error_rate_threshold_percent: float = 5.0

    # MCP Integration: defaults to modern Streamable HTTP endpoint (/mcp)
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "http://localhost:8001/mcp")

    # Operational RAG & pgvector Configuration (Epic 5)
    rag_enabled: bool = os.getenv("RAG_ENABLED", "true").lower() in ("true", "1", "yes")
    pg_host: str = os.getenv("PGHOST", os.getenv("DB_HOST", "localhost"))
    pg_port: int = int(os.getenv("PGPORT", os.getenv("DB_PORT", "5432")))
    pg_database: str = os.getenv("PGDATABASE", os.getenv("DB_NAME", "agentic_autoscalar_db"))
    pg_user: str = os.getenv("PGUSER", os.getenv("DB_USER", "agentic_autoscalar"))
    pg_password: str = os.getenv("PGPASSWORD", os.getenv("DB_PASSWORD_BASE", "agentic_autoscalar"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "2"))
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    model_config = {
        "env_file": ENV_FILE_PATH or ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


def load_config() -> Settings:
    """Load settings from config.yaml if present, complemented by env variables."""
    settings = Settings()
    config_file = Path(__file__).resolve().parent.parent / "config.yaml"
    
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                data = yaml.safe_load(f) or {}
            
            svc = data.get("service", {})
            if "name" in svc:
                settings.service_name = svc["name"]
            if "host" in svc:
                settings.host = svc["host"]
            if "port" in svc:
                settings.port = int(os.getenv("PORT", svc["port"]))
            if "timeout_seconds" in svc:
                settings.timeout_seconds = float(svc["timeout_seconds"])

            model_setting = data.get("model_setting", {})
            provider = os.getenv("LLM_PROVIDER", model_setting.get("provider", settings.llm_provider))
            settings.llm_provider = provider

            providers = data.get("providers", {})
            if provider in providers:
                settings.llm_model = providers[provider].get("model_name", settings.llm_model)

            margins = data.get("scaling_margins", {})
            if "target_cpu_percent" in margins:
                settings.target_cpu_percent = float(margins["target_cpu_percent"])
            if "latency_spike_threshold_ms" in margins:
                settings.latency_spike_threshold_ms = float(margins["latency_spike_threshold_ms"])
        except Exception:
            pass

    # Direct env overrides
    if os.getenv("LLM_PROVIDER"):
        settings.llm_provider = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_MODEL"):
        settings.llm_model = os.getenv("LLM_MODEL")

    return settings


settings = load_config()
