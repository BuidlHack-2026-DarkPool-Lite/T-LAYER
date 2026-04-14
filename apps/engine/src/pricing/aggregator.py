"""3중 오라클: Chainlink + Binance + PancakeSwap → median 기반 공정가."""

from __future__ import annotations

import asyncio
import logging
import os
import statistics
from dataclasses import dataclass

from src.pricing.binance import fetch_binance_price
from src.pricing.chainlink import fetch_chainlink_price
from src.pricing.pancakeswap import fetch_pancakeswap_price

logger = logging.getLogger(__name__)


def _skip_pancake() -> bool:
    return os.environ.get("SKIP_PANCAKESWAP", "").lower() in ("1", "true", "yes")


def _outlier_threshold_pct() -> float:
    try:
        return float(os.environ.get("PRICE_OUTLIER_THRESHOLD_PCT", "5.0"))
    except ValueError:
        return 5.0


@dataclass(frozen=True)
class PriceAggregateResult:
    mid: float | None
    spread: float | None
    chainlink: float | None
    binance: float | None
    pancake: float | None
    outlier_downgraded: bool
    sources_used: int


async def _fetch_all(token_pair: str) -> tuple[float | None, float | None, float | None]:
    """Chainlink, Binance, PancakeSwap 동시 조회."""
    chainlink_t = fetch_chainlink_price(token_pair)
    binance_t = fetch_binance_price(token_pair)

    if _skip_pancake():
        chainlink, binance = await asyncio.gather(chainlink_t, binance_t)
        return chainlink, binance, None

    chainlink, binance, pancake = await asyncio.gather(
        chainlink_t, binance_t, fetch_pancakeswap_price(token_pair),
    )
    return chainlink, binance, pancake


def aggregate_from_sources(
    chainlink: float | None,
    binance: float | None,
    pancake: float | None,
) -> PriceAggregateResult:
    """3중 소스 median 집계. 2개 이상이면 median, 1개면 그대로."""
    prices = [p for p in (chainlink, binance, pancake) if p is not None]
    n = len(prices)

    if n == 0:
        return PriceAggregateResult(
            mid=None, spread=None, chainlink=None, binance=None,
            pancake=pancake, outlier_downgraded=False, sources_used=0,
        )

    if n == 1:
        return PriceAggregateResult(
            mid=prices[0], spread=None, chainlink=chainlink,
            binance=binance, pancake=pancake,
            outlier_downgraded=False, sources_used=1,
        )

    # 이상치 제거: median 기준 threshold 초과 소스 제외
    median_price = statistics.median(prices)
    threshold = _outlier_threshold_pct()
    filtered = []
    downgraded = False

    for p in prices:
        diff_pct = abs(p - median_price) / median_price * 100.0 if median_price > 0 else 0.0
        if diff_pct <= threshold:
            filtered.append(p)
        else:
            downgraded = True
            logger.warning(
                "Price outlier removed: %.4f (diff=%.2f%% from median %.4f)",
                p, diff_pct, median_price,
            )

    if not filtered:
        filtered = prices  # 전부 이상치면 그냥 다 쓰기

    mid = statistics.median(filtered)
    spread = max(prices) - min(prices) if n >= 2 else None

    return PriceAggregateResult(
        mid=mid,
        spread=spread,
        chainlink=chainlink,
        binance=binance,
        pancake=pancake,
        outlier_downgraded=downgraded,
        sources_used=len(filtered),
    )


async def aggregate_prices(token_pair: str) -> PriceAggregateResult:
    chainlink, binance, pancake = await _fetch_all(token_pair)
    return aggregate_from_sources(chainlink, binance, pancake)


async def get_fair_price(token_pair: str) -> float | None:
    r = await aggregate_prices(token_pair)
    return r.mid
