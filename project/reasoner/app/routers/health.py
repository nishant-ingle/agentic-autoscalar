from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def healthz():
    """Liveness probe indicating process is healthy."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/readyz")
async def readyz():
    """Readiness probe indicating service is ready to accept scaling evaluations."""
    return {
        "status": "ready",
        "service": "agentic-autoscaler-reasoner",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/livez")
async def livez():
    return {"status": "alive"}
