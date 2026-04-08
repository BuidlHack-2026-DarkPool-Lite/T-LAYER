"""주문 저장소 단위 테스트."""

from decimal import Decimal

import pytest

from src.models import Order, OrderBook
from src.models.order import OrderSide


def _make_order(
    order_id: str = "0x01",
    side: OrderSide = "buy",
    amount: str = "100",
    limit_price: str = "600",
    token_pair: str = "BNB/USDT",
) -> Order:
    return Order(
        order_id=order_id,
        token_pair=token_pair,
        side=side,
        amount=Decimal(amount),
        limit_price=Decimal(limit_price),
        wallet_address="0xwallet",
    )


class TestOrderBookAdd:
    def test_add_order(self):
        book = OrderBook()
        order = book.add(_make_order())
        assert order.status == "pending"
        assert book.get("0x01") is order

    def test_duplicate_order_id_raises(self):
        book = OrderBook()
        book.add(_make_order())
        with pytest.raises(ValueError, match="중복"):
            book.add(_make_order())


class TestOrderBookCancel:
    def test_cancel_pending_order(self):
        book = OrderBook()
        book.add(_make_order())
        cancelled = book.cancel("0x01")
        assert cancelled.status == "cancelled"
        assert cancelled.is_active is False

    def test_cancel_nonexistent_raises(self):
        book = OrderBook()
        with pytest.raises(KeyError):
            book.cancel("0xnope")

    def test_cancel_partial_order(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        book.fill("0x01", Decimal("60"))
        cancelled = book.cancel("0x01")
        assert cancelled.status == "cancelled"
        assert cancelled.is_active is False

    def test_cancel_filled_order_raises(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        book.fill("0x01", Decimal("100"))
        with pytest.raises(ValueError, match="비활성"):
            book.cancel("0x01")

    def test_cancel_already_cancelled_raises(self):
        book = OrderBook()
        book.add(_make_order())
        book.cancel("0x01")
        with pytest.raises(ValueError, match="비활성"):
            book.cancel("0x01")


class TestOrderBookFill:
    def test_full_fill(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        filled = book.fill("0x01", Decimal("100"))
        assert filled.status == "filled"
        assert filled.remaining == Decimal("0")
        assert filled.is_active is False

    def test_partial_fill(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        partial = book.fill("0x01", Decimal("60"))
        assert partial.status == "partial"
        assert partial.remaining == Decimal("40")
        assert partial.is_active is True

    def test_multiple_partial_fills(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        book.fill("0x01", Decimal("30"))
        book.fill("0x01", Decimal("30"))
        order = book.fill("0x01", Decimal("40"))
        assert order.status == "filled"
        assert order.remaining == Decimal("0")

    def test_overfill_raises(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        with pytest.raises(ValueError, match="초과"):
            book.fill("0x01", Decimal("101"))

    def test_zero_fill_raises(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        with pytest.raises(ValueError, match="양수"):
            book.fill("0x01", Decimal("0"))

    def test_negative_fill_raises(self):
        book = OrderBook()
        book.add(_make_order(amount="100"))
        with pytest.raises(ValueError, match="양수"):
            book.fill("0x01", Decimal("-10"))

    def test_fill_cancelled_raises(self):
        book = OrderBook()
        book.add(_make_order())
        book.cancel("0x01")
        with pytest.raises(ValueError, match="비활성"):
            book.fill("0x01", Decimal("10"))

    def test_fill_nonexistent_raises(self):
        book = OrderBook()
        with pytest.raises(KeyError):
            book.fill("0xnope", Decimal("10"))


class TestOrderBookQuery:
    def test_active_orders_by_side(self):
        book = OrderBook()
        book.add(_make_order(order_id="0xbuy1", side="buy"))
        book.add(_make_order(order_id="0xbuy2", side="buy"))
        book.add(_make_order(order_id="0xsell1", side="sell"))
        book.add(_make_order(order_id="0xcancelled", side="buy"))
        book.cancel("0xcancelled")

        buys = book.active_orders("BNB/USDT", "buy")
        sells = book.active_orders("BNB/USDT", "sell")
        buy_ids = {o.order_id for o in buys}
        sell_ids = {o.order_id for o in sells}
        assert buy_ids == {"0xbuy1", "0xbuy2"}
        assert sell_ids == {"0xsell1"}
        assert "0xcancelled" not in buy_ids

    def test_active_orders_filters_token_pair(self):
        book = OrderBook()
        book.add(_make_order(order_id="0x01", token_pair="BNB/USDT"))
        bnb_orders = book.active_orders("BNB/USDT", "buy")
        eth_orders = book.active_orders("ETH/USDT", "buy")
        assert {o.order_id for o in bnb_orders} == {"0x01"}
        assert {o.order_id for o in eth_orders} == set()
