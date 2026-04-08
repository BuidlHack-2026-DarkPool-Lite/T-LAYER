"""직전 견적 대비 mid 변동에 따른 max_slippage_bps 가산."""

from __future__ import annotations

import os


def dynamic_slippage_enabled() -> bool:
    v = os.environ.get("DYNAMIC_SLIPPAGE_ENABLED", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def compute_dynamic_max_slippage_bps(
    base_bps: int,
    prev_mid: float | None,
    current_mid: float,
) -> tuple[int, int | None, int]:
    """(최종 bps, 직전 대비 절대 변동 bps, base 대비 추가 bps)."""
    if not dynamic_slippage_enabled() or prev_mid is None or prev_mid <= 0:
        return base_bps, None, 0

    rel = abs(current_mid - prev_mid) / prev_mid
    vol_bps = int(round(rel * 10_000))

    try:
        per_pct = float(os.environ.get("DYNAMIC_SLIPPAGE_BPS_PER_VOL_PCT", "25"))
    except ValueError:
        per_pct = 25.0
    try:
        extra_cap = int(os.environ.get("DYNAMIC_SLIPPAGE_EXTRA_CAP_BPS", "200"))
    except ValueError:
        extra_cap = 200
    try:
        hard_cap = int(os.environ.get("MAX_SLIPPAGE_BPS_HARD_CAP", "500"))
    except ValueError:
        hard_cap = 500

    extra = int(rel * 100.0 * per_pct)
    extra = min(max(0, extra), max(0, extra_cap))
    out = min(max(0, base_bps) + extra, max(0, hard_cap))
    return out, vol_bps, extra
