"""EIP-191 ECDSA 서명 생성."""

from eth_account import Account
from eth_account.messages import encode_defunct


def sign_swap(struct_hash: bytes, private_key: str) -> tuple[bytes, str]:
    """struct hash에 EIP-191 서명을 생성한다."""
    message = encode_defunct(struct_hash)
    signed = Account.sign_message(message, private_key=private_key)
    return signed.signature, signed.message_hash.hex()


def get_signer_address(private_key: str) -> str:
    """private key에서 Ethereum 주소를 도출한다."""
    account = Account.from_key(private_key)
    return account.address
