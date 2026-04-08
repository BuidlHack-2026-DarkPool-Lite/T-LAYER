"""컨트랙트 호환 swap struct hash 생성."""

from web3 import Web3


def to_bytes32(hex_str: str) -> bytes:
    """hex 문자열을 32바이트로 변환. 짧으면 왼쪽 zero-pad."""
    raw = bytes.fromhex(hex_str.removeprefix("0x"))
    if len(raw) > 32:
        raise ValueError(f"bytes32 초과: {len(raw)} bytes")
    return raw.rjust(32, b"\x00")


_UINT256_MAX = 2**256 - 1


def to_uint256(value: int) -> bytes:
    """정수를 uint256 (32바이트 big-endian)으로 변환."""
    if value < 0:
        raise ValueError(f"uint256은 음수 불가: {value}")
    if value > _UINT256_MAX:
        raise ValueError(f"uint256 overflow: {value}")
    return value.to_bytes(32, byteorder="big")


def build_swap_struct_hash(
    chain_id: int,
    contract_address: str,
    swap_id: str,
    maker_order_id: str,
    taker_order_id: str,
    maker_fill_amount: int,
    taker_fill_amount: int,
) -> bytes:
    """컨트랙트의 getSwapStructHash와 동일한 keccak256 해시 생성."""
    packed = b"".join(
        [
            to_uint256(chain_id),
            bytes.fromhex(contract_address.removeprefix("0x").lower()),
            to_bytes32(swap_id),
            to_bytes32(maker_order_id),
            to_bytes32(taker_order_id),
            to_uint256(maker_fill_amount),
            to_uint256(taker_fill_amount),
        ]
    )
    return Web3.keccak(packed)
