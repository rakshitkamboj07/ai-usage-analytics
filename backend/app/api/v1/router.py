from fastapi import APIRouter

from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.graph import router as graph_router
from app.api.v1.recommendations import (
    router as recommendations_router,
)
from app.api.v1.usage import router as usage_router


router = APIRouter()

router.include_router(dashboard_router)
router.include_router(usage_router)
router.include_router(recommendations_router)
router.include_router(graph_router)

@router.get("/health", tags=["health"])
async def versioned_health() -> dict[str, str]:
    return {"status": "healthy"}