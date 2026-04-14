"""NEAR AI Cloud TEE-protected Competitive Matching.

3개 전략(Conservative, Volume Max, Free Optimizer) + Judge.
각 역할별 최적화된 TEE 모델을 배정하여 다양성과 품질을 극대화한다.
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
_CLIENT_TIMEOUT_SEC = 60.0

# 역할별 기본 모델 — 각 전략 + Judge에 최적 모델 배정
_ROLE_MODELS: dict[str, str] = {
    "conservative": "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "volume_max": "zai-org/GLM-5-FP8",
    "free_optimizer": "openai/gpt-oss-120b",
    "judge": "Qwen/Qwen3.5-122B-A10B",
}

_DEFAULT_TEE_MODEL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "Qwen/Qwen3.5-122B-A10B",
        "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "zai-org/GLM-5-FP8",
        "openai/gpt-oss-120b",
    }
)


def _allowed_models() -> frozenset[str]:
    raw = os.environ.get("NEAR_AI_ALLOWED_MODELS", "").strip()
    if raw:
        return frozenset(m.strip() for m in raw.split(",") if m.strip())
    return _DEFAULT_TEE_MODEL_ALLOWLIST


def _model_allowed_for_cloud(model: str) -> bool:
    return model in _allowed_models()


def _get_model_for_role(role: str) -> str:
    """역할별 모델을 환경변수 또는 기본값에서 가져온다."""
    env_key = f"NEAR_AI_MODEL_{role.upper()}"
    return os.environ.get(env_key) or _ROLE_MODELS.get(role) or _ROLE_MODELS["conservative"]


def _get_base_config() -> tuple[str, str | None]:
    """base_url, api_key를 환경변수에서 가져온다."""
    base_url = os.environ.get("NEAR_AI_BASE_URL") or _DEFAULT_BASE_URL
    api_key = resolve_api_key(base_url, os.environ.get("NEAR_AI_API_KEY"))
    return base_url, api_key


def _call_tee(system_prompt: str, user_message: str, *, role: str = "conservative") -> dict:
    """역할별 TEE 호출. 역할에 따라 최적 모델을 자동 선택."""
    base_url, api_key = _get_base_config()
    model = _get_model_for_role(role)

    if not api_key:
        return {"error": "NEAR_AI_API_KEY not set"}

    if enforce_cloud_tee_allowlist(base_url) and not _model_allowed_for_cloud(model):
        return {
            "error": (
                f"model {model!r} not in TEE allowlist; set NEAR_AI_ALLOWED_MODELS or "
                "NEAR_AI_ALLOW_ANY_MODEL=1"
            ),
        }

    logger.info("TEE call: role=%s, model=%s", role, model)

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
        logger.exception("TEE call failed (role=%s, model=%s)", role, model)
        return {"error": str(exc)}

    try:
        content = response.choices[0].message.content
        if not content or not content.strip():
            return {"error": "empty model response"}
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
        logger.exception("TEE response JSON parse failed (role=%s)", role)
        return {"error": f"invalid response: {exc}"}

    if not isinstance(parsed, dict):
        return {"error": f"expected JSON object, got {type(parsed).__name__}"}

    parsed["_model"] = model
    return parsed


# ─── 3 Competing Strategies ─────────────────────────────────────

def call_conservative(orders: list[Order], fair_price: float) -> dict:
    """전략 1: 보수적 매칭 (Qwen3-30B) — 가격 품질 우선."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(CONSERVATIVE_PROMPT, user_msg, role="conservative")
    result["_strategy"] = "conservative"
    return result


def call_volume_max(orders: list[Order], fair_price: float) -> dict:
    """전략 2: 체결량 극대화 (GLM-5) — 다른 아키텍처로 다양성 확보."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(VOLUME_MAX_PROMPT, user_msg, role="volume_max")
    result["_strategy"] = "volume_max"
    return result


def call_free_optimizer(orders: list[Order], fair_price: float) -> dict:
    """전략 3: LLM 자유 최적화 (GPT OSS 120B) — 독립적 관점."""
    user_msg = build_user_message(orders, fair_price)
    result = _call_tee(FREE_OPTIMIZER_PROMPT, user_msg, role="free_optimizer")
    result["_strategy"] = "free_optimizer"
    return result


# ─── Judge ───────────────────────────────────────────────────────

def call_judge(
    orders: list[Order],
    fair_price: float,
    results: list[dict],
) -> dict:
    """심판 (Qwen3.5-122B) — 가장 강력한 모델로 공정 채점."""
    user_msg = build_judge_message(orders, fair_price, results)
    return _call_tee(JUDGE_PROMPT, user_msg, role="judge")
