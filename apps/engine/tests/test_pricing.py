"""pricing 모듈 테스트: aggregator, dynamic slippage, quote."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.matching.state import matching_state
from src.pricing.aggregator import PriceAggregateResult, aggregate_from_sources
from src.pricing.dynamic_slippage import compute_dynamic_max_slippage_bps
from src.pricing.quote import get_pricing_quote

# --- aggregator ---


class TestAggregatorOutlier:
    def test_weighted_when_within_threshold(self):
        r = aggregate_from_sources(600.0, 590.0)
        assert r.outlier_downgraded is False
        assert r.mid == 600.0 * 0.6 + 590.0 * 0.4
        assert r.spread == 10.0

    @patch.dict("os.environ", {"PRICE_OUTLIER_THRESHOLD_PCT": "5"}, clear=False)
    def test_downgrade_to_binance_when_wide_spread(self):
        r = aggregate_from_sources(600.0, 500.0)
        assert r.outlier_downgraded is True
        assert r.mid == 500.0

    @patch.dict(
        "os.environ",
        {"PRICE_OUTLIER_THRESHOLD_PCT": "5", "PRICE_OUTLIER_PRIMARY": "pancake"},
        clear=False,
    )
    def test_downgrade_to_pancake_when_configured(self):
        r = aggregate_from_sources(600.0, 500.0)
        assert r.outlier_downgraded is True
        assert r.mid == 600.0


class TestPriceFeed:
    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_weighted_average(self, mock_p, mock_b):
        from src.pricing.aggregator import get_fair_price

        mock_p.return_value = 600.0
        mock_b.return_value = 580.0
        assert await get_fair_price("BNB/USDT") == 592.0

    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_pancake_only(self, mock_p, mock_b):
        from src.pricing.aggregator import get_fair_price

        mock_p.return_value = 600.0
        mock_b.return_value = None
        assert await get_fair_price("BNB/USDT") == 600.0

    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_both_fail(self, mock_p, mock_b):
        from src.pricing.aggregator import get_fair_price

        mock_p.return_value = None
        mock_b.return_value = None
        assert await get_fair_price("BNB/USDT") is None


class TestBinanceFeed:
    @pytest.mark.asyncio
    async def test_fetch_success(self):
        from src.pricing.binance import fetch_binance_price

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"symbol": "BNBUSDT", "price": "612.50"}
        mock_resp.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("src.pricing.binance.httpx.AsyncClient", return_value=mock_client):
            price = await fetch_binance_price("BNB/USDT")

        assert price == 612.50

    @pytest.mark.asyncio
    async def test_unsupported_pair_returns_none(self):
        from src.pricing.binance import fetch_binance_price

        price = await fetch_binance_price("DOGE/USDT")
        assert price is None


class TestPancakeSwapFeed:
    @pytest.mark.asyncio
    async def test_fetch_success(self):
        from src.pricing.pancakeswap import fetch_pancakeswap_price

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "pools": [
                    {"token0Price": "610.25", "token1Price": "0.001638", "totalValueLockedUSD": "1"}
                ]
            }
        }
        mock_resp.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("src.pricing.pancakeswap.httpx.AsyncClient", return_value=mock_client):
            price = await fetch_pancakeswap_price("BNB/USDT")

        assert price == 610.25

    @pytest.mark.asyncio
    async def test_unsupported_pair_returns_none(self):
        from src.pricing.pancakeswap import fetch_pancakeswap_price

        price = await fetch_pancakeswap_price("DOGE/USDT")
        assert price is None


# --- dynamic slippage ---


class TestDynamicSlippage:
    def test_no_prev_returns_base(self):
        b, vol, extra = compute_dynamic_max_slippage_bps(150, None, 100.0)
        assert b == 150
        assert vol is None
        assert extra == 0

    def test_large_move_adds_extra(self):
        b, vol, extra = compute_dynamic_max_slippage_bps(150, 100.0, 102.0)
        assert vol == 200
        assert extra > 0
        assert b == 150 + extra

    @patch.dict("os.environ", {"DYNAMIC_SLIPPAGE_ENABLED": "0"}, clear=False)
    def test_disabled_returns_base(self):
        b, vol, extra = compute_dynamic_max_slippage_bps(150, 100.0, 200.0)
        assert b == 150
        assert vol is None
        assert extra == 0


# --- pricing quote ---


class TestPricingQuote:
    @pytest.mark.asyncio
    @patch("src.pricing.quote.aggregate_prices", new_callable=AsyncMock)
    async def test_success_both_sources(self, mock_agg):
        mock_agg.return_value = PriceAggregateResult(
            mid=592.0, spread=20.0, pancake=600.0, binance=580.0, outlier_downgraded=False
        )
        q = await get_pricing_quote("BNB/USDT", request_id="req-1")
        assert q.error is None
        assert q.mid_price == 592.0
        assert q.max_slippage_bps == 150

    @pytest.mark.asyncio
    @patch("src.pricing.quote.aggregate_prices", new_callable=AsyncMock)
    async def test_feed_failure(self, mock_agg):
        mock_agg.return_value = PriceAggregateResult(
            mid=None, spread=None, pancake=None, binance=None, outlier_downgraded=False
        )
        q = await get_pricing_quote("BNB/USDT")
        assert q.mid_price is None
        assert q.error is not None

    @pytest.mark.asyncio
    async def test_empty_pair(self):
        q = await get_pricing_quote("   ")
        assert q.mid_price is None
        assert q.error is not None

    @pytest.mark.asyncio
    @patch("src.pricing.quote.aggregate_prices", new_callable=AsyncMock)
    async def test_dynamic_slippage_second_quote(self, mock_agg):
        mock_agg.return_value = PriceAggregateResult(
            mid=100.0, spread=1.0, pancake=100.5, binance=99.5, outlier_downgraded=False
        )
        q1 = await get_pricing_quote("BNB/USDT")
        assert q1.max_slippage_bps == 150
        assert q1.volatility_quote_bps is None

        mock_agg.return_value = PriceAggregateResult(
            mid=102.0, spread=1.0, pancake=102.5, binance=101.5, outlier_downgraded=False
        )
        q2 = await get_pricing_quote("BNB/USDT")
        assert q2.volatility_quote_bps is not None
        assert q2.volatility_quote_bps > 0
        assert q2.max_slippage_bps >= q2.base_slippage_bps

    def test_matching_state_record_pricing_mid(self):
        matching_state.reset()
        matching_state.record_pricing_mid("BNB/USDT", 1.0)
        assert matching_state.get_last_pricing_mid("BNB/USDT") == 1.0
        assert matching_state.get_last_pricing_mid("ETH/USDT") is None

    @pytest.mark.asyncio
    @patch("src.pricing.quote.aggregate_prices", new_callable=AsyncMock)
    async def test_per_pair_slippage_isolation(self, mock_agg):
        """다른 페어 견적이 서로 간섭하지 않아야 한다."""
        mock_agg.return_value = PriceAggregateResult(
            mid=600.0, spread=1.0, pancake=600.5, binance=599.5, outlier_downgraded=False
        )
        await get_pricing_quote("BNB/USDT")

        mock_agg.return_value = PriceAggregateResult(
            mid=3000.0, spread=10.0, pancake=3005.0, binance=2995.0, outlier_downgraded=False
        )
        q_eth = await get_pricing_quote("ETH/USDT")
        # ETH/USDT는 이전 견적이 없으므로 volatility_quote_bps가 None이어야 함
        assert q_eth.volatility_quote_bps is None
        assert q_eth.dynamic_slippage_extra_bps == 0
