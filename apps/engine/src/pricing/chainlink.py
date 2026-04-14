"""Chainlink Price Feed — BSC Mainnet에서 공정가를 읽는다."""

from __future__ import annotations

import logging

from web3 import Web3

logger = logging.getLogger(__name__)

# BSC Mainnet RPC (읽기 전용 — 테스트넷 트랜잭션과 무관)
_BSC_MAINNET_RPC = "https://bsc-dataseed1.binance.org"

# Chainlink Price Feed 주소 (BSC Mainnet)
FEEDS: dict[str, str] = {
    "BNB/USD": "0x0567F2323251f0Aab15c8dFb1967E4e8A7D42aeE",
    "BTC/USD": "0x264990fbd0A4796A3E3d8E37C4d5F87a3aCa5eBF",
    "ETH/USD": "0x9ef1B8c0E4F7dc8bF5719Ea496883DC6401d5b2e",
}

_AGG_V3_ABI = [
    {
        "name": "latestRoundData",
        "type": "function",
        "inputs": [],
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
    },
    {
        "name": "decimals",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
]


def _pair_to_feed(token_pair: str) -> str | None:
    """BNB/USDT → BNB/USD 매핑."""
    base = token_pair.split("/")[0].upper()
    feed_key = f"{base}/USD"
    return FEEDS.get(feed_key)


async def fetch_chainlink_price(token_pair: str) -> float | None:
    """BSC Mainnet Chainlink에서 최신 가격을 읽는다 (읽기 전용 RPC)."""
    feed_addr = _pair_to_feed(token_pair)
    if not feed_addr:
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(_BSC_MAINNET_RPC, request_kwargs={"timeout": 10}))
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(feed_addr),
            abi=_AGG_V3_ABI,
        )
        decimals = contract.functions.decimals().call()
        round_data = contract.functions.latestRoundData().call()
        answer = round_data[1]  # int256
        if answer <= 0:
            logger.warning("Chainlink %s: answer <= 0", token_pair)
            return None
        price = answer / (10 ** decimals)
        logger.info("Chainlink %s: $%.4f", token_pair, price)
        return price
    except Exception:
        logger.exception("Chainlink price fetch failed: %s", token_pair)
        return None
