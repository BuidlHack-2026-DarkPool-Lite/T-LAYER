"""주문 API 라우터."""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from src.matching.engine import MatchingEngine
from src.models import Order, OrderBook
from src.schemas import OrderCreateRequest, OrderResponse
from src.signer.pipeline import process_match_results
from src.ws import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_orderbook(request: Request) -> OrderBook:
    return request.app.state.orderbook


def _order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        order_id=order.order_id,
        token_pair=order.token_pair,
        side=order.side,
        amount=str(order.amount),
        filled_amount=str(order.filled_amount),
        remaining=str(order.remaining),
        limit_price=str(order.limit_price),
        wallet_address=order.wallet_address,
        status=order.status,
        created_at=order.created_at.isoformat(),
    )


async def _run_matching_cycle(
    orderbook: OrderBook,
    token_pair: str,
    ws_manager: ConnectionManager,
) -> None:
    """백그라운드 매칭 사이클: 매칭 → 서명 → 제출 → WS 알림."""
    try:
        engine = MatchingEngine(orderbook)
        results = await engine.run_matching_cycle(token_pair)
        if not results:
            return

        # 서명 + BSC 제출
        outcomes = await asyncio.to_thread(process_match_results, results)

        # WS 체결 알림
        await ws_manager.broadcast({"action": "matched", "results": outcomes})

        # 서명/제출 결과 로깅
        submitted = [o for o in outcomes if o.get("tx_hash")]
        if submitted:
            logger.info(
                "매칭 사이클 완료: %d건 체결, %d건 BSC 제출",
                len(results),
                len(submitted),
            )
        else:
            logger.info("매칭 사이클 완료: %d건 체결 (BSC 미설정)", len(results))
    except Exception:
        logger.exception("매칭 사이클 실패: token_pair=%s", token_pair)


@router.post("/order", response_model=OrderResponse, status_code=201)
async def create_order(body: OrderCreateRequest, request: Request) -> OrderResponse:
    """주문 생성. order_id는 서버에서 uuid4로 생성. 생성 후 매칭 사이클 자동 실행."""
    order_id = uuid.uuid4().hex
    order = Order(
        order_id=order_id,
        token_pair=body.token_pair,
        side=body.side,
        amount=body.amount,
        limit_price=body.limit_price,
        wallet_address=body.wallet_address,
    )
    orderbook = _get_orderbook(request)
    orderbook.add(order)
    response = _order_to_response(order)
    manager: ConnectionManager = request.app.state.ws_manager
    try:
        await manager.broadcast({"action": "created", "order": response.model_dump()})
    except Exception:
        logger.exception("broadcast 실패 (created, order_id=%s)", order_id)

    # 백그라운드 매칭 사이클 실행 (태스크 추적)
    task = asyncio.create_task(
        _run_matching_cycle(orderbook, body.token_pair, manager)
    )
    bg_tasks: set = getattr(request.app.state, "background_tasks", None) or set()
    request.app.state.background_tasks = bg_tasks
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)

    return response


@router.get("/order/{order_id}/status", response_model=OrderResponse)
async def get_order_status(order_id: str, request: Request) -> OrderResponse:
    """주문 상태 조회."""
    orderbook = _get_orderbook(request)
    order = orderbook.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없음: {order_id}")
    return _order_to_response(order)


@router.delete("/order/{order_id}", response_model=OrderResponse)
async def cancel_order(order_id: str, request: Request) -> OrderResponse:
    """주문 취소. 미체결 잔량은 컨트랙트에서 환불."""
    orderbook = _get_orderbook(request)
    try:
        order = orderbook.cancel(order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없음: {order_id}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    response = _order_to_response(order)
    try:
        manager: ConnectionManager = request.app.state.ws_manager
        await manager.broadcast({"action": "cancelled", "order": response.model_dump()})
    except Exception:
        logger.exception("broadcast 실패 (cancelled, order_id=%s)", order_id)
    return response


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """실시간 체결 알림 WebSocket."""
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
