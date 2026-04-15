"""T-LAYER TEE Backend — FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.matching.runner import run_matching_cycle
from src.mm_bot.bot import MMBot
from src.mm_bot.config import load_mm_settings
from src.models import OrderBook
from src.routes import router
from src.ws import ConnectionManager

load_dotenv()

# Railway/Docker 환경에서 stderr 로그는 전부 빨갛게 표시됨.
# INFO/DEBUG → stdout, WARNING 이상 → stderr 로 분리.
_log_fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setLevel(logging.DEBUG)
_stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
_stdout_handler.setFormatter(_log_fmt)

_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setLevel(logging.WARNING)
_stderr_handler.setFormatter(_log_fmt)

_root = logging.getLogger()
_root.setLevel(logging.INFO)
# basicConfig 가 이미 붙였을 수 있는 기본 핸들러 제거
for _h in list(_root.handlers):
    _root.removeHandler(_h)
_root.addHandler(_stdout_handler)
_root.addHandler(_stderr_handler)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.orderbook = OrderBook()
    app.state.ws_manager = ConnectionManager()
    app.state.background_tasks: set[asyncio.Task] = set()
    app.state.mm_bot = None

    mm_settings = load_mm_settings()
    if mm_settings.enabled:
        mm_bot = MMBot(
            settings=mm_settings,
            orderbook=app.state.orderbook,
            ws_manager=app.state.ws_manager,
        )
        app.state.mm_bot = mm_bot
        mm_task = asyncio.create_task(mm_bot.run_forever())
        app.state.background_tasks.add(mm_task)
        mm_task.add_done_callback(app.state.background_tasks.discard)
        logger.info("MM 봇 태스크 등록됨 (mm_config.yaml enabled=true)")

    # 주기적 매칭 스위퍼 — 유저 주문이 MM 호가 갱신을 놓쳐도 10초 안에
    # 체결되도록 한다. pair lock 이 중복 실행을 막아준다.
    async def _matching_sweeper() -> None:
        orderbook = app.state.orderbook
        ws_manager = app.state.ws_manager
        while True:
            try:
                await asyncio.sleep(10.0)
                pairs = {o.token_pair for o in orderbook.all_orders() if o.is_active}
                mm = getattr(app.state, "mm_bot", None)
                for pair in pairs:
                    asyncio.create_task(
                        run_matching_cycle(orderbook, pair, ws_manager, mm_bot=mm)
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("매칭 스위퍼 실패")

    sweeper_task = asyncio.create_task(_matching_sweeper())
    app.state.background_tasks.add(sweeper_task)
    sweeper_task.add_done_callback(app.state.background_tasks.discard)
    logger.info("매칭 스위퍼 등록됨 (10초 주기)")

    yield

    mm = getattr(app.state, "mm_bot", None)
    if mm is not None:
        mm.stop()

    # 백그라운드 태스크 정리
    tasks: set[asyncio.Task] = getattr(app.state, "background_tasks", set())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("백그라운드 태스크 %d건 정리 완료", len(tasks))


app = FastAPI(
    title="T-LAYER TEE Engine",
    description="TEE 기반 프라이버시 OTC 매칭 엔진",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
