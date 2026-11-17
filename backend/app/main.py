from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.router import router as v1_router
from app.db.session import engine

app = FastAPI(
    title="AI Usage Analytics",
    version="1.0.0"
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "AI Usage Analytics API Running"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }


@app.get("/db-check")
async def db_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {
        "database": "connected"
    }