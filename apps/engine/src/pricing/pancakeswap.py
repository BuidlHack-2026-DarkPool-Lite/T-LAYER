"""PancakeSwap V3 Subgraph 가격 수집 모듈."""

from __future__ import annotations

import logging
from typing import Final

import httpx

logger = logging.getLogger(__name__)

SUBGRAPH_URL: Final[str] = "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v3-bsc"
REQUEST_TIMEOUT_SEC: Final[float] = 3.0

WBNB: Final[str] = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT_BSC: Final[str] = "0x55d398326f99059fF775485246999027B3197955"

_PAIR_TOKENS: Final[dict[str, tuple[str, str]]] = {
    "BNB/USDT": (WBNB, USDT_BSC),
    "WBNB/USDT": (WBNB, USDT_BSC),
}

_POOLS_QUERY: Final[str] = """
query PancakeV3TopPoolPrice($token0: String!, $token1: String!) {
  pools(
    where: { token0: $token0, token1: $token1 }
    orderBy: totalValueLockedUSD
    orderDirection: desc
    first: 1
  ) {
    token0Price
    token1Price
    totalValueLockedUSD
  }
}
"""


def _normalize_token_pair(token_pair: str) -> str | None:
    key = token_pair.strip().upper().replace(" ", "")
    if key in _PAIR_TOKENS:
        return key
    if key == "BNB-USDT":
        return "BNB/USDT"
    return None


async def fetch_pancakeswap_price(token_pair: str) -> float | None:
    """WBNB/USDT V3 풀 중 TVL 최상위 1개의 token0Price를 반환한다."""
    norm = _normalize_token_pair(token_pair)
    if norm is None:
        logger.warning("unsupported token_pair for PancakeSwap feed: %r", token_pair)
        return None

    token0, token1 = _PAIR_TOKENS[norm]
    variables = {
        "token0": token0.lower(),
        "token1": token1.lower(),
    }

    payload = {"query": _POOLS_QUERY, "variables": variables}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
            response = await client.post(SUBGRAPH_URL, json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception:
        logger.exception("PancakeSwap Subgraph request failed for pair %s", norm)
        return None

    if body.get("errors"):
        logger.warning(
            "PancakeSwap Subgraph GraphQL errors for %s: %s",
            norm,
            body["errors"],
        )
        return None

    data = body.get("data") or {}
    pools = data.get("pools")
    if not pools:
        logger.warning("PancakeSwap Subgraph returned no pools for %s", norm)
        return None

    raw_price = pools[0].get("token0Price")
    if raw_price is None:
        logger.warning("PancakeSwap pool missing token0Price for %s", norm)
        return None

    try:
        return float(raw_price)
    except (TypeError, ValueError):
        logger.exception("invalid token0Price from PancakeSwap for %s: %r", norm, raw_price)
        return None
