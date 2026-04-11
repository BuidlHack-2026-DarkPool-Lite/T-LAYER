"""봇 가상 재고 (테스트넷 데모용)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class InventoryState:
    initial_base: Decimal
    initial_quote: Decimal
    base: Decimal = field(init=False)
    quote: Decimal = field(init=False)

    def __post_init__(self) -> None:
        self.base = self.initial_base
        self.quote = self.initial_quote

    def base_value_usd(self, mid: Decimal) -> Decimal:
        return self.base * mid

    def total_notional_usd(self, mid: Decimal) -> Decimal:
        return self.base * mid + self.quote

    def base_share(self, mid: Decimal) -> float:
        t = self.total_notional_usd(mid)
        if t <= 0:
            return 0.5
        return float((self.base * mid) / t)

    def apply_mm_buy(self, base_received: Decimal, quote_paid: Decimal) -> None:
        self.base += base_received
        self.quote -= quote_paid

    def apply_mm_sell(self, base_sold: Decimal, quote_received: Decimal) -> None:
        self.base -= base_sold
        self.quote += quote_received
