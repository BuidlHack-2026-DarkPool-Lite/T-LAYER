"""TEE 내부 메모리 기반 주문 저장소."""

from decimal import Decimal

from src.models.order import Order, OrderSide


class OrderBook:
    """토큰 쌍별 주문을 관리하는 인메모리 저장소.

    매칭 엔진이 호출하는 조회/수정 메서드를 제공한다.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> Order:
        """주문 추가. order_id 중복 시 ValueError."""
        if order.order_id in self._orders:
            raise ValueError(f"중복 order_id: {order.order_id}")
        self._orders[order.order_id] = order
        return order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def cancel(self, order_id: str) -> Order:
        """주문 취소. 미체결 잔량은 컨트랙트에서 환불 처리."""
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"존재하지 않는 order_id: {order_id}")
        if not order.is_active:
            raise ValueError(f"이미 비활성 주문: {order_id} (status={order.status})")
        order.status = "cancelled"
        return order

    def fill(self, order_id: str, fill_amount: Decimal) -> Order:
        """체결 수량 반영. 잔량이 0이면 filled, 남으면 partial."""
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"존재하지 않는 order_id: {order_id}")
        if not order.is_active:
            raise ValueError(f"비활성 주문에 체결 불가: {order_id}")
        if fill_amount <= 0:
            raise ValueError(f"체결 수량은 양수여야 함: {fill_amount}")
        if fill_amount > order.remaining:
            raise ValueError(f"체결 수량({fill_amount})이 잔량({order.remaining})을 초과")

        order.filled_amount += fill_amount
        order.status = "filled" if order.remaining == 0 else "partial"
        return order

    def active_orders(self, token_pair: str, side: OrderSide) -> list[Order]:
        """특정 토큰 쌍 + 방향의 활성 주문 목록."""
        return [
            o
            for o in self._orders.values()
            if o.token_pair == token_pair and o.side == side and o.is_active
        ]

    def all_orders(self) -> list[Order]:
        return list(self._orders.values())
