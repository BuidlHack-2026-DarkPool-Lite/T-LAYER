"""NEAR AI Cloud TEE-protected chat 추론 (OpenAI SDK)."""

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
from src.matching.prompt import SYSTEM_PROMPT, build_user_message
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


def call_matching(orders: list[Order], fair_price: float) -> dict:
    """Chat completion으로 매칭 JSON을 받는다."""
    base_url = os.environ.get("NEAR_AI_BASE_URL") or _DEFAULT_BASE_URL
    model = os.environ.get("NEAR_AI_MODEL") or _DEFAULT_MODEL

    api_key = resolve_api_key(base_url, os.environ.get("NEAR_AI_API_KEY"))
    if not api_key:
        return {"error": "NEAR_AI_API_KEY not set"}

    if enforce_cloud_tee_allowlist(base_url) and not _model_allowed_for_cloud(model):
        return {
            "error": (
                f"model {model!r} not in TEE allowlist; set NEAR_AI_ALLOWED_MODELS or "
                "NEAR_AI_ALLOW_ANY_MODEL=1 (비프로덕션만)"
            ),
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(orders, fair_price)},
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
        logger.exception("chat.completions.create failed (base_url=%s)", base_url)
        return {"error": str(exc)}

    try:
        content = response.choices[0].message.content
        if not content or not content.strip():
            return {"error": "empty model response"}
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
        logger.exception("matching response JSON parse failed")
        return {"error": f"invalid response: {exc}"}

    if not isinstance(parsed, dict):
        return {"error": f"expected JSON object, got {type(parsed).__name__}"}

    return parsed
