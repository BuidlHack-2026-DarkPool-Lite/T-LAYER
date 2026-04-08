"""규칙 기반 매칭 엔진 단위 테스트."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.matching.rules_engine import RulesEngine
from src.models import Order, OrderBook

FAIR_PRICE = Decimal("600")


def _order(
    order_id: str,
    side: str,
    amount: str,
    limit_price: str,
    created_offset_sec: int = 0,
) -> Order:
    return Order(
        order_id=order_id,
        token_pair="BNB/USDT",
        side=side,
        amount=Decimal(amount),
        limit_price=Decimal(limit_price),
        wallet_address=f"0x{order_id}",
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=created_offset_sec),
    )


class TestPriceCompatibility:
    def test_compatible_prices_match(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "610"))
        book.add(_order("sell1", "sell", "100", "600"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1
        assert results[0].maker_fill_amount == Decimal("100")

    def test_incompatible_prices_no_match(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "590"))
        book.add(_order("sell1", "sell", "100", "600"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 0

    def test_equal_prices_match(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "600"))
        book.add(_order("sell1", "sell", "100", "600"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1


class TestPricePriority:
    def test_highest_buy_matched_first(self):
        book = OrderBook()
        book.add(_order("buy_low", "buy", "50", "600", created_offset_sec=0))
        book.add(_order("buy_high", "buy", "50", "610", created_offset_sec=1))
        book.add(_order("sell1", "sell", "50", "595"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1
        assert results[0].taker_order_id == "buy_high"

    def test_lowest_sell_matched_first(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "50", "610"))
        book.add(_order("sell_high", "sell", "50", "605", created_offset_sec=0))
        book.add(_order("sell_low", "sell", "50", "600", created_offset_sec=1))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1
        assert results[0].maker_order_id == "sell_low"


class TestTimePriority:
    def test_earlier_buy_matched_first(self):
        book = OrderBook()
        book.add(_order("buy_late", "buy", "50", "610", created_offset_sec=10))
        book.add(_order("buy_early", "buy", "50", "610", created_offset_sec=0))
        book.add(_order("sell1", "sell", "50", "600"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert results[0].taker_order_id == "buy_early"


class TestPartialFill:
    def test_partial_fill_remainder_stays(self):
        book = OrderBook()
        book.add(_order("sell1", "sell", "100", "600"))
        book.add(_order("buy1", "buy", "60", "610"))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1
        assert results[0].maker_fill_amount == Decimal("60")

        sell = book.get("sell1")
        assert sell.remaining == Decimal("40")
        assert sell.status == "partial"

        buy = book.get("buy1")
        assert buy.remaining == Decimal("0")
        assert buy.status == "filled"

    def test_multiple_partial_fills_in_one_cycle(self):
        book = OrderBook()
        book.add(_order("sell1", "sell", "100", "600"))
        book.add(_order("buy1", "buy", "30", "610", created_offset_sec=0))
        book.add(_order("buy2", "buy", "40", "610", created_offset_sec=1))
        engine = RulesEngine(book, min_fill=0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 2
        assert results[0].maker_fill_amount == Decimal("30")
        assert results[1].maker_fill_amount == Decimal("40")

        sell = book.get("sell1")
        assert sell.remaining == Decimal("30")


class TestSlippage:
    def test_within_slippage_matches(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "10", "600"))
        book.add(_order("sell1", "sell", "10", "600"))
        engine = RulesEngine(book, slippage_pct=1.5, min_fill=0)

        results = engine.try_match("BNB/USDT", Decimal("609"))
        assert len(results) == 1

    def test_buy_exceeds_slippage_rejected(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "10", "600"))
        book.add(_order("sell1", "sell", "10", "590"))
        engine = RulesEngine(book, slippage_pct=1.5, min_fill=0)

        results = engine.try_match("BNB/USDT", Decimal("620"))
        assert len(results) == 0

    def test_sell_exceeds_slippage_rejected(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "10", "610"))
        book.add(_order("sell1", "sell", "10", "600"))
        engine = RulesEngine(book, slippage_pct=1.5, min_fill=0)

        results = engine.try_match("BNB/USDT", Decimal("580"))
        assert len(results) == 0


class TestMinFillAmount:
    def test_below_min_fill_skipped(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "0.5", "610"))
        book.add(_order("sell1", "sell", "0.5", "600"))
        engine = RulesEngine(book, min_fill=1.0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 0

    def test_above_min_fill_matches(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "2", "610"))
        book.add(_order("sell1", "sell", "2", "600"))
        engine = RulesEngine(book, min_fill=1.0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1

    def test_min_fill_does_not_block_subsequent_match(self):
        book = OrderBook()
        book.add(_order("buy_small", "buy", "0.3", "610", created_offset_sec=0))
        book.add(_order("buy_big", "buy", "5", "610", created_offset_sec=1))
        book.add(_order("sell1", "sell", "5", "600"))
        engine = RulesEngine(book, min_fill=1.0)

        results = engine.try_match("BNB/USDT", FAIR_PRICE)
        assert len(results) == 1
        assert results[0].taker_order_id == "buy_big"


class TestFairPriceValidation:
    def test_zero_fair_price_returns_empty(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "10", "610"))
        book.add(_order("sell1", "sell", "10", "600"))
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("BNB/USDT", Decimal("0")) == []

    def test_negative_fair_price_returns_empty(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "10", "610"))
        book.add(_order("sell1", "sell", "10", "600"))
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("BNB/USDT", Decimal("-100")) == []


class TestNoMatch:
    def test_no_sell_orders(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "610"))
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("BNB/USDT", FAIR_PRICE) == []

    def test_no_buy_orders(self):
        book = OrderBook()
        book.add(_order("sell1", "sell", "100", "600"))
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("BNB/USDT", FAIR_PRICE) == []

    def test_different_token_pair_no_match(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "610"))
        book.add(_order("sell1", "sell", "100", "600"))
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("ETH/USDT", FAIR_PRICE) == []

    def test_cancelled_orders_not_matched(self):
        book = OrderBook()
        book.add(_order("buy1", "buy", "100", "610"))
        book.add(_order("sell1", "sell", "100", "600"))
        book.cancel("buy1")
        engine = RulesEngine(book, min_fill=0)
        assert engine.try_match("BNB/USDT", FAIR_PRICE) == []
