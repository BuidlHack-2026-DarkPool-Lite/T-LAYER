"""validator 모듈 테스트."""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from src.matching.validator import validate_matching_result
from src.models.order import Order


def sample_orders() -> list[Order]:
    return [
        Order(
            order_id="order_alice_1",
            side="sell",
            token_pair="BNB/USDT",
            amount=Decimal("100"),
            limit_price=Decimal("580"),
            wallet_address="0xAlice",
        ),
        Order(
            order_id="order_bob_1",
            side="buy",
            token_pair="BNB/USDT",
            amount=Decimal("60"),
            limit_price=Decimal("585"),
            wallet_address="0xBob",
        ),
    ]


def valid_match_dict() -> dict:
    return {
        "match_id": "m_001",
        "maker_order_id": "order_alice_1",
        "maker_wallet": "0xAlice",
        "taker_order_id": "order_bob_1",
        "taker_wallet": "0xBob",
        "token_pair": "BNB/USDT",
        "fill_amount": 60.0,
        "execution_price": 582.0,
    }


def make_raw_result(*matches: dict) -> dict:
    return {"matches": list(matches)}


@pytest.fixture
def standard_orders() -> list[Order]:
    return sample_orders()


@pytest.fixture
def base_match() -> dict:
    return copy.deepcopy(valid_match_dict())


def test_validate_ok(standard_orders, base_match):
    r = validate_matching_result(
        make_raw_result(base_match), standard_orders, fair_price=582.0, prev_fair_price=None
    )
    assert len(r.accepted) == 1
    assert r.rejected == []
    assert r.round_held is False


def test_reject_execution_above_taker_limit(standard_orders, base_match):
    bad = {**base_match, "execution_price": 586.0}
    r = validate_matching_result(
        make_raw_result(bad), standard_orders, fair_price=582.0, prev_fair_price=None
    )
    assert r.accepted == []
    assert len(r.rejected) == 1
    assert "매수 limit_price" in r.rejected[0]["reason"]


def test_reject_execution_below_maker_limit(standard_orders, base_match):
    bad = {**base_match, "execution_price": 579.0}
    r = validate_matching_result(
        make_raw_result(bad), standard_orders, fair_price=582.0, prev_fair_price=None
    )
    assert r.accepted == []
    assert "매도 limit_price" in r.rejected[0]["reason"]


def test_reject_cumulative_fill_exceeds(standard_orders, base_match):
    over = {**base_match, "fill_amount": 70.0}
    r = validate_matching_result(
        make_raw_result(over), standard_orders, fair_price=582.0, prev_fair_price=None
    )
    assert r.accepted == []
    assert "원 수량" in r.rejected[0]["reason"]


def test_reject_unknown_order_id(standard_orders, base_match):
    bad = {**base_match, "maker_order_id": "no_such_order"}
    r = validate_matching_result(
        make_raw_result(bad), standard_orders, fair_price=582.0, prev_fair_price=None
    )
    assert r.accepted == []
    assert "존재하지 않는 maker_order_id" in r.rejected[0]["reason"]


def test_round_held_fair_price_move_over_2_percent(standard_orders, base_match):
    r = validate_matching_result(
        make_raw_result(base_match), standard_orders, fair_price=103.0, prev_fair_price=100.0
    )
    assert r.round_held is True
    assert r.accepted == []
    assert "라운드 보류" in r.rejected[0]["reason"]


def test_fair_price_move_1_5_percent_passes(standard_orders, base_match):
    r = validate_matching_result(
        make_raw_result(base_match), standard_orders, fair_price=101.5, prev_fair_price=100.0
    )
    assert r.round_held is False
    assert len(r.accepted) == 1


def test_prev_fair_price_none_skips_volatility(standard_orders, base_match):
    r = validate_matching_result(
        make_raw_result(base_match), standard_orders, fair_price=103.0, prev_fair_price=None
    )
    assert r.round_held is False
    assert len(r.accepted) == 1
