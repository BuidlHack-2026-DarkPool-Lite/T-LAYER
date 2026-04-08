"""매칭 결과 모델."""

from decimal import Decimal

from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    """매칭 엔진이 산출한 단건 체결 결과. 서명 후 컨트랙트로 전송."""

    swap_id: str
    maker_order_id: str
    taker_order_id: str
    maker_fill_amount: Decimal = Field(gt=0)
    taker_fill_amount: Decimal = Field(gt=0)
    exec_price: Decimal = Field(gt=0)
