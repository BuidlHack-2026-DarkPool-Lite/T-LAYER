"""도메인 모델 단위 테스트."""

from decimal import Decimal

import pytest

from src.models import MatchResult, Order


class TestOrder:
    def test_create_buy_order(self):
        order = Order(
            order_id="0xabc1",
            token_pair="BNB/USDT",
            side="buy",
            amount=Decimal("100"),
            limit_price=Decimal("600.5"),
            wallet_address="0x1234",
        )
        assert order.status == "pending"
        assert order.filled_amount == Decimal("0")
        assert order.remaining == Decimal("100")
        assert order.is_active is True

    def test_remaining_after_partial_fill(self):
        order = Order(
            order_id="0xabc2",
            token_pair="BNB/USDT",
            side="sell",
            amount=Decimal("100"),
            limit_price=Decimal("600"),
            wallet_address="0x5678",
        )
        order.filled_amount = Decimal("60")
        order.status = "partial"
        assert order.remaining == Decimal("40")
        assert order.is_active is True

    def test_filled_order_not_active(self):
        order = Order(
            order_id="0xabc3",
            token_pair="BNB/USDT",
            side="buy",
            amount=Decimal("50"),
            limit_price=Decimal("600"),
            wallet_address="0x9999",
            status="filled",
            filled_amount=Decimal("50"),
        )
        assert order.remaining == Decimal("0")
        assert order.is_active is False

    def test_cancelled_order_not_active(self):
        order = Order(
            order_id="0xabc4",
            token_pair="BNB/USDT",
            side="sell",
            amount=Decimal("10"),
            limit_price=Decimal("600"),
            wallet_address="0xaaaa",
            status="cancelled",
        )
        assert order.is_active is False

    def test_invalid_amount_rejected(self):
        with pytest.raises(ValueError):
            Order(
                order_id="0xbad",
                token_pair="BNB/USDT",
                side="buy",
                amount=Decimal("-1"),
                limit_price=Decimal("600"),
                wallet_address="0x0000",
            )

    def test_invalid_limit_price_rejected(self):
        with pytest.raises(ValueError):
            Order(
                order_id="0xbad2",
                token_pair="BNB/USDT",
                side="buy",
                amount=Decimal("100"),
                limit_price=Decimal("0"),
                wallet_address="0x0000",
            )

    def test_filled_exceeds_amount_rejected(self):
        with pytest.raises(ValueError, match="초과"):
            Order(
                order_id="0xbad3",
                token_pair="BNB/USDT",
                side="buy",
                amount=Decimal("100"),
                filled_amount=Decimal("101"),
                limit_price=Decimal("600"),
                wallet_address="0x0000",
            )


class TestMatchResult:
    def test_create_match_result(self):
        result = MatchResult(
            swap_id="0xswap1",
            maker_order_id="0xmaker",
            taker_order_id="0xtaker",
            maker_fill_amount=Decimal("60"),
            taker_fill_amount=Decimal("36000"),
            exec_price=Decimal("600"),
        )
        assert result.swap_id == "0xswap1"
        assert result.maker_fill_amount == Decimal("60")

    def test_zero_fill_rejected(self):
        with pytest.raises(ValueError):
            MatchResult(
                swap_id="0xswap2",
                maker_order_id="0xmaker",
                taker_order_id="0xtaker",
                maker_fill_amount=Decimal("0"),
                taker_fill_amount=Decimal("100"),
                exec_price=Decimal("600"),
            )
