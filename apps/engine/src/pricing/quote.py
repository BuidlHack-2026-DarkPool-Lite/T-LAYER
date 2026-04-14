"""다중 소스 가격 견적 + 동적 슬리피지."""

from __future__ import annotations

import os
import time

from src.matching.state import matching_state
from src.pricing.aggregator import aggregate_prices
from src.pricing.dynamic_slippage import compute_dynamic_max_slippage_bps
from src.pricing.types import PricingQuoteResponse

_DEFAULT_MAX_SLIPPAGE_BPS = 150


def _base_max_slippage_bps() -> int:
    raw = os.environ.get("MAX_SLIPPAGE_BPS", str(_DEFAULT_MAX_SLIPPAGE_BPS))
    try:
        v = int(raw)
        return max(0, v)
    except ValueError:
        return _DEFAULT_MAX_SLIPPAGE_BPS


async def get_pricing_quote(
    token_pair: str,
    *,
    request_id: str | None = None,
) -> PricingQuoteResponse:
    """다소스 시세, 이상치 처리, 동적 슬리피지를 반영한 견적."""
    ts = time.time()
    pair = token_pair.strip()
    if not pair:
        return PricingQuoteResponse(
            token_pair=token_pair,
            request_id=request_id,
            mid_price=None,
            spread=None,
            chainlink_mid=None,
            pancake_mid=None,
            binance_mid=None,
            sources_used=None,
            outlier_downgraded=None,
            timestamp=ts,
            max_slippage_bps=None,
            base_slippage_bps=None,
            volatility_quote_bps=None,
            dynamic_slippage_extra_bps=None,
            error="token_pair is empty",
        )

    agg = await aggregate_prices(pair)
    if agg.mid is None:
        return PricingQuoteResponse(
            token_pair=pair,
            request_id=request_id,
            mid_price=None,
            spread=agg.spread,
            chainlink_mid=agg.chainlink,
            pancake_mid=agg.pancake,
            binance_mid=agg.binance,
            sources_used=agg.sources_used,
            outlier_downgraded=agg.outlier_downgraded,
            timestamp=ts,
            max_slippage_bps=None,
            base_slippage_bps=None,
            volatility_quote_bps=None,
            dynamic_slippage_extra_bps=None,
            error="price feed failed (all sources)",
        )

    base_bps = _base_max_slippage_bps()
    max_bps, vol_bps, extra_bps = compute_dynamic_max_slippage_bps(
        base_bps,
        matching_state.get_last_pricing_mid(pair),
        agg.mid,
    )
    matching_state.record_pricing_mid(pair, agg.mid)

    return PricingQuoteResponse(
        token_pair=pair,
        request_id=request_id,
        mid_price=agg.mid,
        spread=agg.spread,
        chainlink_mid=agg.chainlink,
        pancake_mid=agg.pancake,
        binance_mid=agg.binance,
        sources_used=agg.sources_used,
        outlier_downgraded=agg.outlier_downgraded,
        timestamp=ts,
        max_slippage_bps=max_bps,
        base_slippage_bps=base_bps,
        volatility_quote_bps=vol_bps,
        dynamic_slippage_extra_bps=extra_bps,
        error=None,
    )
