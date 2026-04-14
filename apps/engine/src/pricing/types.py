"""가격 견적 요청/응답 모델."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PricingQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_pair: str = Field(..., examples=["BNB/USDT"])
    request_id: str | None = Field(default=None)


class PricingQuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_pair: str
    request_id: str | None = None
    mid_price: float | None = Field(default=None)
    spread: float | None = Field(default=None)
    chainlink_mid: float | None = Field(default=None)
    pancake_mid: float | None = Field(default=None)
    binance_mid: float | None = Field(default=None)
    sources_used: int | None = Field(default=None)
    outlier_downgraded: bool | None = Field(default=None)
    timestamp: float = Field(...)
    max_slippage_bps: int | None = Field(default=None)
    base_slippage_bps: int | None = Field(default=None)
    volatility_quote_bps: int | None = Field(default=None)
    dynamic_slippage_extra_bps: int | None = Field(default=None)
    error: str | None = Field(default=None)
