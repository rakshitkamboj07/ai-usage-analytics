from fastapi import APIRouter

print("GRAPH ROUTER LOADED")

router = APIRouter(
    prefix="/graph",
    tags=["graph"],
)


@router.get("/health")
async def graph_health():
    return {
        "status": "graph module ready"
    }