from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from api.routers import alerts, comparison, prices, products, reports
from config import settings
from models.database import Base

engine = create_async_engine(settings.effective_database_url, echo=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Naar Price Monitor", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(prices.router, prefix="/prices", tags=["Prices"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(comparison.router, prefix="/comparison", tags=["Comparison"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])


@app.get("/")
async def root():
    return {
        "app": "Naar Price Monitor",
        "docs": "/docs",
        "health": "/health",
        "compare_ui": "http://localhost:3000/compare",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "demo_mode": settings.DEMO_MODE,
        "production_mode": settings.is_production,
        "claude_enabled": settings.claude_enabled,
        "claude_model": settings.CLAUDE_MODEL if settings.claude_enabled else None,
    }
