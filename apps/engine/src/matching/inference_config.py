"""NEAR AI Cloud TEE-protected 추론 설정."""

from __future__ import annotations

import os

__all__ = [
    "enforce_cloud_tee_allowlist",
    "resolve_api_key",
    "use_structured_json_response_format",
]


def enforce_cloud_tee_allowlist(_base_url: str) -> bool:
    v = os.environ.get("NEAR_AI_ALLOW_ANY_MODEL", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return False
    return True


def resolve_api_key(_base_url: str, explicit_key: str | None) -> str | None:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    return None


def use_structured_json_response_format(_base_url: str) -> bool:
    override = os.environ.get("NEAR_AI_JSON_RESPONSE_FORMAT", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    return True
