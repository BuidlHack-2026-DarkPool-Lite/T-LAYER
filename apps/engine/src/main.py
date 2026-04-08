"""DarkPool Lite TEE Backend — FastAPI entrypoint."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.models import OrderBook
from src.routes import router
from src.ws import ConnectionManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.orderbook = OrderBook()
    app.state.ws_manager = ConnectionManager()
    app.state.background_tasks: set[asyncio.Task] = set()
    yield
    # 백그라운드 태스크 정리
    tasks: set[asyncio.Task] = getattr(app.state, "background_tasks", set())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("백그라운드 태스크 %d건 정리 완료", len(tasks))


app = FastAPI(
    title="DarkPool Lite TEE Engine",
    description="TEE 기반 프라이버시 OTC 매칭 엔진",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
