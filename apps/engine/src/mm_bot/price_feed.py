"""PancakeSwap + Binance 가중 평균, 이상치 시 단일 소스."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from src.pricing.binance import fetch_binance_price
from src.pricing.pancakeswap import fetch_pancakeswap_price

logger = logging.getLogger(__name__)


@dataclass
class MidPriceResult:
    mid: float | None
    pancake: float | None
    binance: float | None
    outlier_downgraded: bool
    error: str | None = None


class PriceFeedListener:
    """스펙: Pancake 60% + Binance 40%, 편차 > threshold 시 한 소스 제외."""

    def __init__(
        self,
        *,
        pancake_weight: float = 0.6,
        binance_weight: float = 0.4,
        outlier_threshold_pct: float = 2.0,
        outlier_primary: str = "binance",
    ) -> None:
        self._wp = pancake_weight
        self._wb = binance_weight
        self._threshold = outlier_threshold_pct
        self._primary = outlier_primary if outlier_primary in ("binance", "pancake") else "binance"

    async def get_mid_price(self, token_pair: str) -> MidPriceResult:
        pancake, binance = await asyncio.gather(
            fetch_pancakeswap_price(token_pair),
            fetch_binance_price(token_pair),
        )

        if pancake is None and binance is None:
            return MidPriceResult(
                mid=None,
                pancake=None,
                binance=None,
                outlier_downgraded=False,
                error="all feeds failed",
            )

        if pancake is not None and binance is not None:
            spread = abs(pancake - binance)
            lo = min(pancake, binance)
            diff_pct = (spread / lo * 100.0) if lo > 0 else 0.0
            if diff_pct > self._threshold:
                chosen = binance if self._primary == "binance" else pancake
                logger.warning(
                    "MM price feed: outlier %.2f%% > %.2f%%, using %s only",
                    diff_pct,
                    self._threshold,
                    self._primary,
                )
                return MidPriceResult(
                    mid=chosen,
                    pancake=pancake,
                    binance=binance,
                    outlier_downgraded=True,
                    error=None,
                )
            mid = pancake * self._wp + binance * self._wb
            return MidPriceResult(
                mid=mid,
                pancake=pancake,
                binance=binance,
                outlier_downgraded=False,
                error=None,
            )

        if pancake is not None:
            return MidPriceResult(
                mid=pancake,
                pancake=pancake,
                binance=None,
                outlier_downgraded=False,
                error=None,
            )
        return MidPriceResult(
            mid=binance,
            pancake=None,
            binance=binance,
            outlier_downgraded=False,
            error=None,
        )

    async def poll_loop_sleep(self, interval_sec: float) -> None:
        await asyncio.sleep(interval_sec)


def wall_time() -> float:
    return time.monotonic()
