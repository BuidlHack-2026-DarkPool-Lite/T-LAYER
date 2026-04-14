"""시스템 프롬프트 + 매칭 규칙 정의 모듈.

Competitive TEE Matching: 3개 전략 프롬프트 + Judge 프롬프트.
"""

from __future__ import annotations

import json

from src.models.order import Order

# ─── 공통 매칭 규칙 (모든 전략이 공유) ───────────────────────────────

_COMMON_RULES = """\
## 공통 규칙 (반드시 준수)

### 가격 호환성
매수(buy)와 매도(sell)가 매칭되려면:
  buy.limit_price >= sell.limit_price

### 체결가 산출
입력으로 주어진 공정가를 fair_price라 한다.
  if sell.limit_price <= fair_price <= buy.limit_price:
      execution_price = fair_price
  else:
      execution_price = (buy.limit_price + sell.limit_price) / 2

### 체결 수량
  fill_amount = min(buy 잔여 수량, sell 잔여 수량)
최소 체결 수량: 1.0 (미만이면 해당 페어는 체결하지 않는다).

### 자기 매칭 금지
- 같은 wallet_address를 가진 buy 주문과 sell 주문은 절대 매칭하지 않는다 (wash trading 방지).
- 반드시 서로 다른 wallet_address 간에만 매칭한다.

### 슬리피지 가드레일
- 체결가가 매수자 limit_price를 초과하면 해당 매칭은 허용되지 않는다.
- 체결가가 매도자 limit_price 미만이면 해당 매칭은 허용되지 않는다.

### 출력 형식
출력은 유효한 JSON 객체 한 개만 허용한다. 마크다운, 코드 펜스, 자연어 설명, 주석을 절대 붙이지 않는다.

### 역할·식별
- maker는 매도(sell) 쪽, taker는 매수(buy) 쪽이다.
- matches 항목: maker_order_id, taker_order_id, token_pair, fill_amount, execution_price, match_id(고유 문자열)
- remaining_orders: 아직 잔량이 남은 주문만
- 응답 최상위 키: "matches", "remaining_orders", "fair_price", "reasoning"
"""


# ─── Strategy 1: Conservative ────────────────────────────────────

CONSERVATIVE_PROMPT = f"""\
당신은 보수적 매칭 전략을 따르는 다크풀 OTC 매칭 엔진이다.

## 전략 방침
- 가격 차이가 가장 적은 매수-매도 쌍부터 매칭한다.
- 불확실한 매칭은 하지 않는다. 가격 갭이 크면 매칭을 건너뛴다.
- 체결 수보다 체결 품질(가격 정확도)을 우선한다.
- 부분 체결은 확실한 경우에만 허용한다.

{_COMMON_RULES}

"reasoning" 키에 보수적 전략 관점에서 매칭 판단 근거를 영문 한 문단으로 작성한다.\
"""


# ─── Strategy 2: Volume Maximizer ────────────────────────────────

VOLUME_MAX_PROMPT = f"""\
당신은 체결량 극대화 전략을 따르는 다크풀 OTC 매칭 엔진이다.

## 전략 방침
- 가능한 한 많은 주문을 체결시키는 것이 최우선이다.
- 부분 체결을 적극 활용한다.
- 매수 주문: limit_price 내림차순, 매도 주문: limit_price 오름차순으로 정렬 후 그리디 매칭.
- 한 주문이 소진되면 즉시 다음 주문으로 넘어간다.
- 가격 호환성만 충족하면 무조건 매칭한다.

{_COMMON_RULES}

"reasoning" 키에 체결량 극대화 관점에서 매칭 판단 근거를 영문 한 문단으로 작성한다.\
"""


# ─── Strategy 3: Free Optimizer ──────────────────────────────────

FREE_OPTIMIZER_PROMPT = f"""\
당신은 자유 최적화 전략을 따르는 다크풀 OTC 매칭 엔진이다.

## 전략 방침
- 체결률, 가격 품질, 공정성을 종합적으로 판단하여 최적의 매칭을 만든다.
- 특정 거래자에게 유리하지 않도록 균형 잡힌 매칭을 추구한다.
- 매수자와 매도자 모두의 price improvement를 고려한다.
- 필요하다면 매칭 순서를 자유롭게 결정할 수 있다.
- 창의적인 매칭 조합을 시도해도 좋다.

{_COMMON_RULES}

"reasoning" 키에 종합 최적화 관점에서 매칭 판단 근거를 영문 한 문단으로 작성한다.\
"""


# ─── Judge ───────────────────────────────────────────────────────

JUDGE_PROMPT = """\
당신은 다크풀 매칭 결과를 평가하는 심판이다. 3개의 서로 다른 전략이 만든 매칭 결과를 받아서 가장 좋은 결과를 선택한다.

## 평가 기준
1. fill_rate (40%): 총 체결량 / 총 주문량. 높을수록 좋다.
2. spread_quality (30%): 체결가가 공정가에 얼마나 가까운지. 가까울수록 좋다.
3. fairness (30%): 매수자와 매도자 양측의 price improvement가 균형 잡혔는지.

## 평가 방법
각 전략에 0~100점을 매긴다:
- fill_rate_score = (해당 전략 총 체결량 / 최대 가능 체결량) * 100
- spread_score = 100 - (|avg_exec_price - fair_price| / fair_price * 10000)  (음수면 0)
- fairness_score = 100 - |buyer_improvement - seller_improvement| * 10  (음수면 0)
- total = fill_rate_score * 0.4 + spread_score * 0.3 + fairness_score * 0.3

## 출력 형식
JSON 객체 한 개만 반환. 마크다운, 코드 펜스 금지.
{
  "winner": 0,  // 0, 1, 2 중 하나 (가장 높은 total 점수)
  "scores": [
    {"strategy": "conservative", "fill_rate": 85, "spread": 92, "fairness": 78, "total": 85.0},
    {"strategy": "volume_max", "fill_rate": 95, "spread": 80, "fairness": 70, "total": 82.0},
    {"strategy": "free_optimizer", "fill_rate": 90, "spread": 88, "fairness": 85, "total": 87.5}
  ],
  "reasoning": "영문 한 문단으로 선택 근거"
}\
"""


# ─── 메시지 빌더 ─────────────────────────────────────────────────

def _build_owner_map(orders: list[Order]) -> dict[str, str]:
    """wallet_address → 익명 owner_id 매핑 (프라이버시 보호)."""
    seen: dict[str, str] = {}
    counter = 0
    for o in orders:
        addr = o.wallet_address.lower()
        if addr not in seen:
            counter += 1
            seen[addr] = f"owner_{counter}"
    return seen


def build_user_message(orders: list[Order], fair_price: float) -> str:
    """주문 리스트와 공정가를 LLM user 메시지용 JSON 문자열로 만든다.

    프라이버시: wallet_address 대신 익명 owner_id로 동일 소유자 식별.
    """
    owner_map = _build_owner_map(orders)
    order_dicts = []
    for o in orders:
        order_dicts.append(
            {
                "order_id": o.order_id,
                "side": o.side,
                "token_pair": o.token_pair,
                "amount": float(o.amount),
                "limit_price": float(o.limit_price),
                "owner_id": owner_map[o.wallet_address.lower()],
            }
        )
    payload = {
        "orders": order_dicts,
        "fair_price": fair_price,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_judge_message(
    orders: list[Order],
    fair_price: float,
    results: list[dict],
) -> str:
    """Judge용 메시지. 원본 주문 + 3개 전략 결과를 묶는다."""
    order_dicts = []
    for o in orders:
        order_dicts.append(
            {
                "order_id": o.order_id,
                "side": o.side,
                "token_pair": o.token_pair,
                "amount": float(o.amount),
                "limit_price": float(o.limit_price),
            }
        )

    strategy_names = ["conservative", "volume_max", "free_optimizer"]
    labeled_results = []
    for i, r in enumerate(results):
        labeled_results.append({
            "strategy": strategy_names[i] if i < len(strategy_names) else f"strategy_{i}",
            "result": r,
        })

    payload = {
        "original_orders": order_dicts,
        "fair_price": fair_price,
        "strategy_results": labeled_results,
    }
    return json.dumps(payload, ensure_ascii=False)
