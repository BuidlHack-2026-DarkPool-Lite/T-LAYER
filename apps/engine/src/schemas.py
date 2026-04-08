"""API 요청/응답 스키마."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    token_pair: str
    side: Literal["buy", "sell"]
    amount: Decimal = Field(gt=0)
    limit_price: Decimal = Field(gt=0)
    wallet_address: str


class OrderResponse(BaseModel):
    order_id: str
    token_pair: str
    side: str
    amount: str
    filled_amount: str
    remaining: str
    limit_price: str
    wallet_address: str
    status: str
    created_at: str


class ErrorResponse(BaseModel):
    detail: str
