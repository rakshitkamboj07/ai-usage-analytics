from fastapi import APIRouter

from app.api.v1.usage import router as usage_router

router = APIRouter()
router.include_router(usage_router)


@router.get("/health", tags=["health"])
async def versioned_health() -> dict[str, str]:
    return {"status": "healthy"}
