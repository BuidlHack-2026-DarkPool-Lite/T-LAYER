"""mm_config.yaml 로드."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger(__name__)


@dataclass
class MMOnchainConfig:
    base_token: str
    quote_token: str
    gas_price_gwei: int = 10


@dataclass
class MMPairConfig:
    token_pair: str
    initial_inventory_base: float = 1000.0
    initial_inventory_quote: float = 300_000.0


@dataclass
class MMSettings:
    enabled: bool = False
    pairs: list[MMPairConfig] = field(default_factory=list)
    pricing: dict[str, Any] = field(default_factory=dict)
    spread: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    order: dict[str, Any] = field(default_factory=dict)
    onchain: MMOnchainConfig | None = None


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "mm_config.yaml"


def load_mm_settings(path: Path | None = None) -> MMSettings:
    if yaml is None:
        logger.warning("PyYAML 미설치 — MM 봇 비활성 (uv sync 로 pyyaml 설치)")
        return MMSettings(enabled=False)

    cfg_path = path or _default_config_path()
    if not cfg_path.is_file():
        logger.info("mm_config.yaml 없음 — MM 봇 비활성: %s", cfg_path)
        return MMSettings(enabled=False)

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("mm_config.yaml 파싱 실패 — MM 봇 비활성")
        return MMSettings(enabled=False)

    mm = raw.get("mm_bot") or {}
    if not mm.get("enabled", False):
        return MMSettings(enabled=False)

    pairs_raw = mm.get("pairs") or []
    pairs: list[MMPairConfig] = []
    for p in pairs_raw:
        if not isinstance(p, dict):
            continue
        tp = (p.get("token_pair") or f"{p.get('base', 'BNB')}/{p.get('quote', 'USDT')}").strip()
        pairs.append(
            MMPairConfig(
                token_pair=tp,
                initial_inventory_base=float(p.get("initial_inventory_base", 1000)),
                initial_inventory_quote=float(p.get("initial_inventory_quote", 300_000)),
            )
        )

    oc = mm.get("onchain") or {}
    onchain = MMOnchainConfig(
        base_token=str(oc.get("base_token", "")).strip(),
        quote_token=str(oc.get("quote_token", "")).strip(),
        gas_price_gwei=int(oc.get("gas_price_gwei", 10)),
    )

    return MMSettings(
        enabled=True,
        pairs=pairs or [MMPairConfig(token_pair="BNB/USDT")],
        pricing=mm.get("pricing") or {},
        spread=mm.get("spread") or {},
        risk=mm.get("risk") or {},
        order=mm.get("order") or {},
        onchain=onchain,
    )
