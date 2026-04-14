"""PancakeSwap V3 온체인 가격 — slot0() 직접 호출."""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from web3 import Web3

logger = logging.getLogger(__name__)

# BSC Mainnet (읽기 전용)
_BSC_MAINNET_RPC: Final[str] = "https://bsc-dataseed1.binance.org"

# PancakeSwap V3 Pool: WBNB/USDT (fee 500 — 가장 유동성 높은 tier)
_POOL_ADDRESSES: Final[dict[str, str]] = {
    "BNB/USDT": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
}

_SLOT0_ABI = [
    {
        "name": "slot0",
        "type": "function",
        "inputs": [],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint32"},
            {"name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
    }
]

_Q96 = 2**96


def _normalize_pair(token_pair: str) -> str | None:
    key = token_pair.strip().upper().replace(" ", "").replace("-", "/")
    if key in _POOL_ADDRESSES:
        return key
    if key == "WBNB/USDT":
        return "BNB/USDT"
    return None


def _sqrt_price_to_price(sqrt_price_x96: int) -> float:
    """sqrtPriceX96 → token1/token0 가격.

    WBNB(token0, 18 dec) / USDT(token1, 18 dec) 이므로
    price = (sqrtPriceX96 / 2^96)^2 → USDT per BNB = 1/price.
    """
    ratio = (sqrt_price_x96 / _Q96) ** 2
    if ratio <= 0:
        return 0.0
    return 1.0 / ratio  # USDT per BNB


async def fetch_pancakeswap_price(token_pair: str) -> float | None:
    """PancakeSwap V3 Pool의 slot0()에서 현재 가격을 읽는다."""
    norm = _normalize_pair(token_pair)
    if norm is None:
        logger.warning("unsupported token_pair for PancakeSwap feed: %r", token_pair)
        return None

    pool_addr = _POOL_ADDRESSES[norm]

    try:
        w3 = Web3(
            Web3.HTTPProvider(_BSC_MAINNET_RPC, request_kwargs={"timeout": 10})
        )
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(pool_addr),
            abi=_SLOT0_ABI,
        )
        data = await asyncio.to_thread(contract.functions.slot0().call)
        sqrt_price_x96 = data[0]

        if sqrt_price_x96 == 0:
            logger.warning("PancakeSwap slot0 returned zero sqrtPriceX96 for %s", norm)
            return None

        price = _sqrt_price_to_price(sqrt_price_x96)
        logger.info("PancakeSwap %s: $%.4f (onchain slot0)", norm, price)
        return price
    except Exception:
        logger.exception("PancakeSwap onchain price fetch failed: %s", norm)
        return None
