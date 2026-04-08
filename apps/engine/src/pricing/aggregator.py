"""복수 소스 가중 평균 산출, 이상치 시 단일 소스 강등."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from src.pricing.binance import fetch_binance_price
from src.pricing.pancakeswap import fetch_pancakeswap_price

logger = logging.getLogger(__name__)

PANCAKE_WEIGHT = 0.6
BINANCE_WEIGHT = 0.4


def _outlier_threshold_pct() -> float:
    try:
        return float(os.environ.get("PRICE_OUTLIER_THRESHOLD_PCT", "5.0"))
    except ValueError:
        return 5.0


def _outlier_primary() -> str:
    v = os.environ.get("PRICE_OUTLIER_PRIMARY", "binance").strip().lower()
    return v if v in ("binance", "pancake") else "binance"


@dataclass(frozen=True)
class PriceAggregateResult:
    mid: float | None
    spread: float | None
    pancake: float | None
    binance: float | None
    outlier_downgraded: bool


async def _fetch_source_prices(token_pair: str) -> tuple[float | None, float | None]:
    return await asyncio.gather(
        fetch_pancakeswap_price(token_pair),
        fetch_binance_price(token_pair),
    )


def aggregate_from_sources(
    pancake: float | None,
    binance: float | None,
) -> PriceAggregateResult:
    """두 소스가 모두 있을 때 괴리가 임계값을 넘으면 한 소스만 사용한다."""
    if pancake is not None and binance is not None:
        spread = abs(pancake - binance)
        lo = min(pancake, binance)
        diff_pct = (spread / lo * 100.0) if lo > 0 else 0.0
        threshold = _outlier_threshold_pct()
        if diff_pct > threshold:
            primary = _outlier_primary()
            if primary == "binance":
                chosen = binance
                logger.warning(
                    "price outlier downgrade: using Binance only (diff=%.2f%% > %.2f%%)",
                    diff_pct,
                    threshold,
                )
            else:
                chosen = pancake
                logger.warning(
                    "price outlier downgrade: using PancakeSwap only (diff=%.2f%% > %.2f%%)",
                    diff_pct,
                    threshold,
                )
            return PriceAggregateResult(
                mid=chosen,
                spread=spread,
                pancake=pancake,
                binance=binance,
                outlier_downgraded=True,
            )
        mid = pancake * PANCAKE_WEIGHT + binance * BINANCE_WEIGHT
        return PriceAggregateResult(
            mid=mid,
            spread=spread,
            pancake=pancake,
            binance=binance,
            outlier_downgraded=False,
        )
    if pancake is not None:
        return PriceAggregateResult(
            mid=pancake, spread=None, pancake=pancake, binance=None, outlier_downgraded=False
        )
    if binance is not None:
        return PriceAggregateResult(
            mid=binance, spread=None, pancake=None, binance=binance, outlier_downgraded=False
        )
    return PriceAggregateResult(
        mid=None, spread=None, pancake=None, binance=None, outlier_downgraded=False
    )


async def aggregate_prices(token_pair: str) -> PriceAggregateResult:
    pancake, binance = await _fetch_source_prices(token_pair)
    return aggregate_from_sources(pancake, binance)


async def get_fair_price(token_pair: str) -> float | None:
    r = await aggregate_prices(token_pair)
    return r.mid
