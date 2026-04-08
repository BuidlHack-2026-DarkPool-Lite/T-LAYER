"""signer/pipeline 단위 테스트."""

from decimal import Decimal
from unittest.mock import patch

from src.models.match import MatchResult
from src.signer.pipeline import process_match_results, sign_match


def _match() -> MatchResult:
    return MatchResult(
        swap_id="aa" * 16,
        maker_order_id="bb" * 16,
        taker_order_id="cc" * 16,
        maker_fill_amount=Decimal("60"),
        taker_fill_amount=Decimal("36000"),
        exec_price=Decimal("600"),
    )


class TestSignMatch:
    def test_no_private_key_returns_none(self):
        with patch("src.signer.pipeline.TEE_PRIVATE_KEY", ""):
            assert sign_match(_match()) is None

    def test_no_contract_address_returns_none(self):
        with (
            patch(
                "src.signer.pipeline.TEE_PRIVATE_KEY",
                "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
            ),
            patch("src.signer.pipeline.ESCROW_CONTRACT_ADDRESS", ""),
        ):
            assert sign_match(_match()) is None

    def test_sign_succeeds_with_valid_config(self):
        with (
            patch(
                "src.signer.pipeline.TEE_PRIVATE_KEY",
                "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
            ),
            patch(
                "src.signer.pipeline.ESCROW_CONTRACT_ADDRESS",
                "0x5FbDB2315678afecb367f032d93F642f64180aa3",
            ),
        ):
            result = sign_match(_match())
            assert result is not None
            signature, struct_hash = result
            assert len(signature) == 65
            assert len(struct_hash) == 32


class TestProcessMatchResults:
    def test_no_key_skips_signing(self):
        with patch("src.signer.pipeline.TEE_PRIVATE_KEY", ""):
            outcomes = process_match_results([_match()])
            assert len(outcomes) == 1
            assert outcomes[0]["signed"] is False
            assert outcomes[0]["tx_hash"] is None

    def test_empty_results(self):
        outcomes = process_match_results([])
        assert outcomes == []
