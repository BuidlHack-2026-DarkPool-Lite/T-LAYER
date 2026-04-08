"""ECDSA 서명 + struct hash 단위 테스트."""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from src.signer.hash_builder import build_swap_struct_hash, to_bytes32, to_uint256
from src.signer.signer import get_signer_address, sign_swap

TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = Account.from_key(TEST_PRIVATE_KEY).address

CHAIN_ID = 97
CONTRACT_ADDR = "0x5FbDB2315678afecb367f032d93F642f64180aa3"


class TestToBytes32:
    def test_hex_string(self):
        result = to_bytes32("abcdef")
        assert len(result) == 32
        assert result[-3:] == bytes.fromhex("abcdef")
        assert result[:29] == b"\x00" * 29

    def test_with_0x_prefix(self):
        result = to_bytes32("0xabcdef")
        assert len(result) == 32

    def test_full_32_bytes(self):
        hex_str = "a" * 64
        result = to_bytes32(hex_str)
        assert len(result) == 32

    def test_exceeds_32_bytes_raises(self):
        hex_str = "a" * 66
        with pytest.raises(ValueError, match="bytes32 초과"):
            to_bytes32(hex_str)


class TestToUint256:
    def test_zero(self):
        result = to_uint256(0)
        assert len(result) == 32
        assert result == b"\x00" * 32

    def test_positive(self):
        result = to_uint256(1000)
        assert len(result) == 32
        assert int.from_bytes(result, "big") == 1000

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="음수"):
            to_uint256(-1)


class TestBuildSwapStructHash:
    def test_deterministic(self):
        args = {
            "chain_id": CHAIN_ID,
            "contract_address": CONTRACT_ADDR,
            "swap_id": "aa" * 16,
            "maker_order_id": "bb" * 16,
            "taker_order_id": "cc" * 16,
            "maker_fill_amount": 100_000_000_000_000_000_000,
            "taker_fill_amount": 60_000_000_000_000_000_000_000,
        }
        hash1 = build_swap_struct_hash(**args)
        hash2 = build_swap_struct_hash(**args)
        assert hash1 == hash2
        assert len(hash1) == 32

    def test_different_input_different_hash(self):
        base = {
            "chain_id": CHAIN_ID,
            "contract_address": CONTRACT_ADDR,
            "swap_id": "aa" * 16,
            "maker_order_id": "bb" * 16,
            "taker_order_id": "cc" * 16,
            "maker_fill_amount": 100,
            "taker_fill_amount": 60000,
        }
        hash1 = build_swap_struct_hash(**base)
        hash2 = build_swap_struct_hash(**{**base, "maker_fill_amount": 200})
        assert hash1 != hash2


class TestSignSwap:
    def test_sign_and_recover(self):
        struct_hash = build_swap_struct_hash(
            chain_id=CHAIN_ID,
            contract_address=CONTRACT_ADDR,
            swap_id="aa" * 16,
            maker_order_id="bb" * 16,
            taker_order_id="cc" * 16,
            maker_fill_amount=100,
            taker_fill_amount=60000,
        )

        signature, _ = sign_swap(struct_hash, TEST_PRIVATE_KEY)

        message = encode_defunct(struct_hash)
        recovered = Account.recover_message(message, signature=signature)
        assert recovered == TEST_ADDRESS

    def test_wrong_key_different_address(self):
        other_key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
        struct_hash = build_swap_struct_hash(
            chain_id=CHAIN_ID,
            contract_address=CONTRACT_ADDR,
            swap_id="aa" * 16,
            maker_order_id="bb" * 16,
            taker_order_id="cc" * 16,
            maker_fill_amount=100,
            taker_fill_amount=60000,
        )

        signature, _ = sign_swap(struct_hash, other_key)
        message = encode_defunct(struct_hash)
        recovered = Account.recover_message(message, signature=signature)
        assert recovered != TEST_ADDRESS


class TestGetSignerAddress:
    def test_correct_address(self):
        addr = get_signer_address(TEST_PRIVATE_KEY)
        assert addr == TEST_ADDRESS
        assert addr.startswith("0x")
        assert len(addr) == 42
