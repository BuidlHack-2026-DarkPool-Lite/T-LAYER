"""매칭/가격 견적용 프로세스 상태 (공정가 이력, 동적 슬리피지 입력)."""


class MatchingState:
    def __init__(self) -> None:
        self._prev_fair_price: float | None = None
        self._last_pricing_mid: dict[str, float] = {}

    @property
    def prev_fair_price(self) -> float | None:
        return self._prev_fair_price

    @property
    def last_pricing_mid(self) -> float | None:
        """하위 호환. per-pair 접근은 get_last_pricing_mid()을 사용."""
        return None

    def get_last_pricing_mid(self, token_pair: str) -> float | None:
        return self._last_pricing_mid.get(token_pair)

    def update_fair_price(self, new_price: float) -> None:
        self._prev_fair_price = new_price

    def record_pricing_mid(self, token_pair: str, mid: float) -> None:
        self._last_pricing_mid[token_pair] = mid

    def reset(self) -> None:
        self._prev_fair_price = None
        self._last_pricing_mid = {}


matching_state = MatchingState()
