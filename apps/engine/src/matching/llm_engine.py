"""NEAR AI Cloud TEE-protected Competitive Matching.

3개 전략(Conservative, Volume Max, Free Optimizer) + Judge.
모든 호출은 동일 NEAR AI TEE 환경, 프롬프트만 다름.
"""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from src.matching.inference_config import (
    enforce_cloud_tee_allowlist,
    resolve_api_key,
    use_structured_json_response_format,
)
from src.matching.prompt import (
    CONSERVATIVE_PROMPT,
    FREE_OPTIMIZER_PROMPT,
    JUDGE_PROMPT,
    VOLUME_MAX_PROMPT,
    build_judge_message,
    build_user_message,
)
from src.matching.schema import get_response_format
from src.models.order import Order

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://cloud-api.near.ai/v1"
_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.1"
_CLIENT_TIMEOUT_SEC = 60.0

_DEFAULT_TEE_MODEL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "deepseek-ai/DeepSeek-V3.1",
        "Qwen/Qwen3.5-122B-A10B",
        "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "zai-org/GLM-5-FP8",
    }
)


def _allowed_models() -> frozenset[str]:
    raw = os.environ.get("NEAR_AI_ALLOWED_MODELS", "").strip()
    if raw:
        return frozenset(m.strip() for m in raw.split(",") if m.strip())
    return _DEFAULT_TEE_MODEL_ALLOWLIST


def _model_allowed_for_cloud(model: str) -> bool:
    return model in _allowed_models()


def _get_client_config() -> tuple[str, str, str | None]:
    """base_url, model, api_key를 환경변수에서 가져온다."""
    base_url = os.environ.get("NEAR_AI_BASE_URL") or _DEFAULT_BASE_URL
    model = os.environ.get("NEAR_AI_MODEL") or _DEFAULT_MODEL
    api_key = resolve_api_key(base_url, os.environ.get("NEAR_AI_API_KEY"))
    return base_url, model, api_key


def _call_tee(system_prompt: str, user_message: str) -> dict:
    """공통 TEE 호출. 프롬프트만 받아서 NEAR AI에 요청."""
    base_url, model, api_key = _get_client_config()

    if not api_key:
        return {"error": "NEAR_AI_API_KEY not set"}

    if enforce_cloud_tee_allowlist(base_url) and not _model_allowed_for_cloud(model):
        return {
            "error": (
                f"model {model!r} not in TEE allowlist; set NEAR_AI_ALLOWED_MODELS or "
                "NEAR_AI_ALLOW_ANY_MODEL=1"
            ),
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
    }
    if use_structured_json_response_format(base_url):
        create_kwargs["response_format"] = get_response_format()

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=_CLIENT_TIMEOUT_SEC,
        )
        response = client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        logger.exception("TEE call failed (base_url=%s)", base_url)
        return {"error": str(exc)}

    try:
        content = response.choices[0].message.content
        if not content or not content.strip():
            return {"error": "empty model response"}
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
        logger.exception("TEE response JSON parse failed")
        return {"error": f"invalid response: {exc}"}

    if not isinstance(parsed, dict):
        return {"error": f"expected JSON object, got {type(parsed).__name__}"}

    return parsed


# ─── 3 Competing Strategies ─────────────────────────────────────

def call_conservative(orders: list[Order], fair_price: float) -> dict:
    """전략 1: 보수적 매칭. 가격 품질 우선."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(CONSERVATIVE_PROMPT, user_msg)
    result["_strategy"] = "conservative"
    return result


def call_volume_max(orders: list[Order], fair_price: float) -> dict:
    """전략 2: 체결량 극대화."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(VOLUME_MAX_PROMPT, user_msg)
    result["_strategy"] = "volume_max"
    return result


def call_free_optimizer(orders: list[Order], fair_price: float) -> dict:
    """전략 3: LLM 자유 최적화."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(FREE_OPTIMIZER_PROMPT, user_msg)
    result["_strategy"] = "free_optimizer"
    return result


# ─── Judge ───────────────────────────────────────────────────────

def call_judge(
    orders: list[Order],
    fair_price: float,
    results: list[dict],
) -> dict:
    """심판: 3개 전략 결과를 평가하고 승자를 선택한다."""
    user_msg = build_judge_message(orders, fair_price, results)
    return _call_tee(JUDGE_PROMPT, user_msg)
