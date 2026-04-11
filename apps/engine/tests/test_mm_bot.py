"""MM 봇 유닛 테스트 (가격 피드 없이 순수 로직)."""

from decimal import Decimal

from src.mm_bot.order_gen import bid_ask_prices
from src.mm_bot.spread import SpreadCalculator, SpreadConfig


def test_bid_ask_symmetric_spread() -> None:
    bid, ask = bid_ask_prices(600.0, 100.0)
    assert bid < Decimal("600")
    assert ask > Decimal("600")
    mid = (bid + ask) / 2
    assert abs(mid - Decimal("600")) < Decimal("0.01")


def test_spread_volatility_increases_bps() -> None:
    base_bps = 30.0
    calc = SpreadCalculator(
        SpreadConfig(base_bps=base_bps, min_bps=10.0, max_bps=200.0, vol_window_sec=60.0)
    )
    # hi=101, lo=99, range≈2% → multiplier≈3.0 → effective≈90bps
    t = 0.0
    for p in (100.0, 100.5, 101.0, 99.0, 100.0):
        t += 1.0
        calc.record_mid(t, p)
    eff = calc.effective_spread_bps()
    # 변동성 승수가 실제로 작동했는지 확인 — base_bps 보다 엄격히 커야 한다.
    assert eff > base_bps
    assert eff >= base_bps * 2.0
