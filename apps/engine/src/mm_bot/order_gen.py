"""호가 가격 산출."""

from __future__ import annotations

from decimal import Decimal


def bid_ask_prices(mid: float, spread_bps: float) -> tuple[Decimal, Decimal]:
    """bid = mid * (1 - spread/2), ask = mid * (1 + spread/2). spread_bps 총폭."""
    sf = spread_bps / 10_000.0
    m = Decimal(str(mid))
    bid = m * (Decimal(1) - Decimal(str(sf)) / Decimal(2))
    ask = m * (Decimal(1) + Decimal(str(sf)) / Decimal(2))
    return bid, ask
