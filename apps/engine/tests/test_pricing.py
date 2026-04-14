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
    def test_median_two_sources(self):
        """2개 소스 → median = 두 값의 평균."""
        r = aggregate_from_sources(None, 590.0, 600.0)
        assert r.outlier_downgraded is False
        assert r.mid == 595.0  # median of [590, 600]
        assert r.spread == 10.0
        assert r.sources_used == 2

    def test_median_three_sources(self):
        """3개 소스 → median = 중앙값."""
        r = aggregate_from_sources(595.0, 590.0, 600.0)
        assert r.outlier_downgraded is False
        assert r.mid == 595.0  # median of [590, 595, 600]
        assert r.sources_used == 3

    @patch.dict("os.environ", {"PRICE_OUTLIER_THRESHOLD_PCT": "5"}, clear=False)
    def test_outlier_removed(self):
        """이상치(5% 초과)는 제거되고 나머지로 median 산출."""
        r = aggregate_from_sources(590.0, 585.0, 700.0)
        assert r.outlier_downgraded is True
        # 700 은 median(585,590,700)=590 대비 18.6% → 제거
        # 남은 [585, 590] → median = 587.5
        assert r.mid == 587.5
        assert r.sources_used == 2

    def test_single_source(self):
        r = aggregate_from_sources(None, 500.0, None)
        assert r.mid == 500.0
        assert r.sources_used == 1


class TestPriceFeed:
    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_chainlink_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_median(self, mock_p, mock_b, mock_c):
        from src.pricing.aggregator import get_fair_price

        mock_c.return_value = 595.0
        mock_b.return_value = 580.0
        mock_p.return_value = 600.0
        # median of [595, 580, 600] = 595
        assert await get_fair_price("BNB/USDT") == 595.0

    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_chainlink_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_single_source(self, mock_p, mock_b, mock_c):
        from src.pricing.aggregator import get_fair_price

        mock_c.return_value = None
        mock_b.return_value = None
        mock_p.return_value = 600.0
        assert await get_fair_price("BNB/USDT") == 600.0

    @pytest.mark.asyncio
    @patch("src.pricing.aggregator.fetch_chainlink_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_binance_price", new_callable=AsyncMock)
    @patch("src.pricing.aggregator.fetch_pancakeswap_price", new_callable=AsyncMock)
    async def test_get_fair_price_all_fail(self, mock_p, mock_b, mock_c):
        from src.pricing.aggregator import get_fair_price

        mock_c.return_value = None
        mock_b.return_value = None
        mock_p.return_value = None
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

        # sqrtPriceX96 for ~$610.25: sqrt(1/610.25) * 2^96 ≈ 3208...
        # 역산: price = 1 / (sqrtPriceX96 / 2^96)^2
        # sqrtPriceX96 = 2^96 / sqrt(610.25) ≈ 3204...
        import math
        target_price = 610.25
        sqrt_price_x96 = int(2**96 / math.sqrt(target_price))

        mock_slot0 = MagicMock()
        mock_slot0.call.return_value = (sqrt_price_x96, -64200, 0, 0, 0, 0, True)

        mock_functions = MagicMock()
        mock_functions.slot0.return_value = mock_slot0

        mock_contract = MagicMock()
        mock_contract.functions = mock_functions

        with patch("src.pricing.pancakeswap.Web3") as mock_web3_cls:
            mock_w3 = MagicMock()
            mock_w3.eth.contract.return_value = mock_contract
            mock_web3_cls.return_value = mock_w3
            mock_web3_cls.to_checksum_address = lambda x: x
            mock_web3_cls.HTTPProvider = MagicMock()

            price = await fetch_pancakeswap_price("BNB/USDT")

        assert price is not None
        assert abs(price - target_price) < 0.01

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
            mid=592.0, spread=20.0, chainlink=595.0, binance=580.0, pancake=600.0,
            outlier_downgraded=False, sources_used=3,
        )
        q = await get_pricing_quote("BNB/USDT", request_id="req-1")
        assert q.error is None
        assert q.mid_price == 592.0
        assert q.max_slippage_bps == 150

    @pytest.mark.asyncio
    @patch("src.pricing.quote.aggregate_prices", new_callable=AsyncMock)
    async def test_feed_failure(self, mock_agg):
        mock_agg.return_value = PriceAggregateResult(
            mid=None, spread=None, chainlink=None, binance=None, pancake=None,
            outlier_downgraded=False, sources_used=0,
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
            mid=100.0, spread=1.0, chainlink=None, binance=99.5, pancake=100.5,
            outlier_downgraded=False, sources_used=2,
        )
        q1 = await get_pricing_quote("BNB/USDT")
        assert q1.max_slippage_bps == 150
        assert q1.volatility_quote_bps is None

        mock_agg.return_value = PriceAggregateResult(
            mid=102.0, spread=1.0, chainlink=None, binance=101.5, pancake=102.5,
            outlier_downgraded=False, sources_used=2,
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
            mid=600.0, spread=1.0, chainlink=None, binance=599.5, pancake=600.5,
            outlier_downgraded=False, sources_used=2,
        )
        await get_pricing_quote("BNB/USDT")

        mock_agg.return_value = PriceAggregateResult(
            mid=3000.0, spread=10.0, chainlink=None, binance=2995.0, pancake=3005.0,
            outlier_downgraded=False, sources_used=2,
        )
        q_eth = await get_pricing_quote("ETH/USDT")
        # ETH/USDT는 이전 견적이 없으므로 volatility_quote_bps가 None이어야 함
        assert q_eth.volatility_quote_bps is None
        assert q_eth.dynamic_slippage_extra_bps == 0
