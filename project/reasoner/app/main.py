import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, ENV_FILE_PATH
from app.routers.health import router as health_router
from app.routers.scaling import router as scaling_router

# Configure structured logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
)
logger = logging.getLogger("reasoner")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Agentic Autoscaler Reasoner Service (%s)", settings.service_name)
    logger.info("Loaded Environment File: %s", ENV_FILE_PATH or "None (system environment only)")
    logger.info("Active LLM Provider: %s | Model: %s", settings.llm_provider, settings.llm_model)
    logger.info("Target CPU: %.1f%% | Latency Threshold: %.1fms", settings.target_cpu_percent, settings.latency_spike_threshold_ms)
    yield
    logger.info("Shutting down Agentic Autoscaler Reasoner Service")


app = FastAPI(
    title="Agentic Autoscaler Reasoner API",
    description="Asynchronous Telemetry Reasoning Layer for Kubernetes Autoscaling (Epic 3: AUTOSCALE-301)",
    version="0.1.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    """Measures latency and attaches structured correlation IDs to every incoming HTTP request."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"

    # Log non-healthcheck routes with structured timing
    if not request.url.path.endswith(("healthz", "readyz", "livez")):
        logger.info(
            "HTTP %s %s status=%d duration=%.2fms req_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id
        )

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Returns clean, standardized HTTP 422 JSON errors when telemetry payloads are malformed."""
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error.get("loc", []))
        errors.append({
            "field": field_path,
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error")
        })

    logger.warning("Rejected malformed telemetry payload on %s: %s", request.url.path, errors)
    return JSONResponse(
        status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
        content={
            "error": "Unprocessable Entity",
            "message": "ClusterMetricsPayload failed strict schema validation",
            "details": errors
        }
    )


# Register Routers
app.include_router(health_router)
app.include_router(scaling_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
