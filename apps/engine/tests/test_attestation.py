"""TEE attestation 검증 테스트."""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.attestation.verifier import (
    decode_nvidia_jwt_payload,
    extract_enclave_measurement,
    extract_gpu_model_from_jwt,
    extract_nvidia_payloads,
    extract_signing_addresses,
    verify_attestation,
)

SAMPLE_REPORT = {
    "model_attestations": [
        {
            "signing_address": "0xABCD1234",
            "nvidia_payload": '{"evidence": "test"}',
        },
        {
            "signing_address": "0xEFGH5678",
            "nvidia_payload": '{"evidence": "test2"}',
        },
    ]
}

SAMPLE_REPORT_NO_NVIDIA = {
    "model_attestations": [
        {"signing_address": "0xABCD1234"},
    ]
}


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.signature"


class TestExtractSigningAddresses:
    def test_extracts_unique_addresses(self):
        addresses = extract_signing_addresses(SAMPLE_REPORT)
        assert addresses == ["0xABCD1234", "0xEFGH5678"]

    def test_empty_report(self):
        assert extract_signing_addresses({}) == []

    def test_deduplicates(self):
        report = {
            "model_attestations": [
                {"signing_address": "0xAAA"},
                {"signing_address": "0xAAA"},
            ]
        }
        assert extract_signing_addresses(report) == ["0xAAA"]


class TestExtractNvidiaPayloads:
    def test_extracts_payloads(self):
        payloads = extract_nvidia_payloads(SAMPLE_REPORT)
        assert len(payloads) == 2

    def test_no_nvidia_payloads(self):
        assert extract_nvidia_payloads(SAMPLE_REPORT_NO_NVIDIA) == []


class TestDecodeNvidiaJwt:
    def test_decode_valid_jwt(self):
        jwt = _make_jwt({"x-nvidia-overall-att-result": True, "sub": "test"})
        payload = decode_nvidia_jwt_payload(jwt)
        assert payload is not None
        assert payload["x-nvidia-overall-att-result"] is True

    def test_decode_invalid_jwt(self):
        assert decode_nvidia_jwt_payload("not.a.valid.jwt.token") is None

    def test_decode_empty(self):
        assert decode_nvidia_jwt_payload("") is None


class TestVerifyAttestation:
    @pytest.mark.asyncio
    async def test_full_success(self):
        jwt = _make_jwt({"x-nvidia-overall-att-result": True})
        nvidia_resp = {"eat_token": jwt}

        with (
            patch(
                "src.attestation.verifier.fetch_attestation_report",
                new_callable=AsyncMock,
                return_value=SAMPLE_REPORT,
            ),
            patch(
                "src.attestation.verifier.verify_gpu_attestation",
                new_callable=AsyncMock,
                return_value=nvidia_resp,
            ),
        ):
            result = await verify_attestation("test-model")

        assert result.success is True
        assert result.signing_addresses == ["0xABCD1234", "0xEFGH5678"]
        assert result.gpu_verified is True
        assert len(result.gpu_results) == 2

    @pytest.mark.asyncio
    async def test_report_fetch_failure(self):
        with patch(
            "src.attestation.verifier.fetch_attestation_report",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await verify_attestation("test-model")

        assert result.success is False
        assert "조회 실패" in result.error

    @pytest.mark.asyncio
    async def test_no_signing_addresses(self):
        with patch(
            "src.attestation.verifier.fetch_attestation_report",
            new_callable=AsyncMock,
            return_value={"model_attestations": []},
        ):
            result = await verify_attestation("test-model")

        assert result.success is False
        assert "signing address" in result.error

    @pytest.mark.asyncio
    async def test_no_nvidia_payloads_still_succeeds(self):
        with patch(
            "src.attestation.verifier.fetch_attestation_report",
            new_callable=AsyncMock,
            return_value=SAMPLE_REPORT_NO_NVIDIA,
        ):
            result = await verify_attestation("test-model")

        assert result.success is True
        assert result.gpu_verified is False
        assert result.gpu_results == []

    @pytest.mark.asyncio
    async def test_nvidia_verification_failure(self):
        with (
            patch(
                "src.attestation.verifier.fetch_attestation_report",
                new_callable=AsyncMock,
                return_value=SAMPLE_REPORT,
            ),
            patch(
                "src.attestation.verifier.verify_gpu_attestation",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await verify_attestation("test-model")

        assert result.success is True
        assert result.gpu_verified is False
        assert all(not r["passed"] for r in result.gpu_results)

    @pytest.mark.asyncio
    async def test_gpu_attestation_fails(self):
        jwt = _make_jwt({"x-nvidia-overall-att-result": False})
        nvidia_resp = {"eat_token": jwt}

        with (
            patch(
                "src.attestation.verifier.fetch_attestation_report",
                new_callable=AsyncMock,
                return_value=SAMPLE_REPORT,
            ),
            patch(
                "src.attestation.verifier.verify_gpu_attestation",
                new_callable=AsyncMock,
                return_value=nvidia_resp,
            ),
        ):
            result = await verify_attestation("test-model")

        assert result.success is True
        assert result.gpu_verified is False


class TestExtractEnclaveMeasurement:
    def test_top_level(self):
        report = {"enclave_measurement": "abc123"}
        assert extract_enclave_measurement(report) == "abc123"

    def test_from_model_attestation(self):
        report = {"model_attestations": [{"enclave_measurement": "def456"}]}
        assert extract_enclave_measurement(report) == "def456"

    def test_top_level_takes_priority(self):
        report = {
            "enclave_measurement": "top",
            "model_attestations": [{"enclave_measurement": "nested"}],
        }
        assert extract_enclave_measurement(report) == "top"

    def test_empty_report(self):
        assert extract_enclave_measurement({}) == ""

    def test_no_measurement(self):
        assert extract_enclave_measurement(SAMPLE_REPORT) == ""

    def test_model_attestations_not_a_list(self):
        assert extract_enclave_measurement({"model_attestations": None}) == ""
        assert extract_enclave_measurement({"model_attestations": "bad"}) == ""

    def test_model_attestations_contains_non_dict(self):
        report = {"model_attestations": [None, "x", 42, {"enclave_measurement": "valid"}]}
        assert extract_enclave_measurement(report) == "valid"

    def test_model_attestations_all_non_dict(self):
        report = {"model_attestations": [None, "x", 42]}
        assert extract_enclave_measurement(report) == ""


class TestExtractGpuModel:
    def test_hwmodel(self):
        jwt = _make_jwt({"x-nvidia-hwmodel": "NVIDIA H100"})
        resp = {"eat_token": jwt}
        assert extract_gpu_model_from_jwt(resp) == "NVIDIA H100"

    def test_gpu_arch_fallback(self):
        jwt = _make_jwt({"x-nvidia-gpu-arch": "Hopper"})
        resp = {"eat_token": jwt}
        assert extract_gpu_model_from_jwt(resp) == "Hopper"

    def test_no_gpu_info(self):
        jwt = _make_jwt({"x-nvidia-overall-att-result": True})
        resp = {"eat_token": jwt}
        assert extract_gpu_model_from_jwt(resp) == ""

    def test_no_jwt(self):
        assert extract_gpu_model_from_jwt({}) == ""

    def test_eat_token_not_a_string(self):
        assert extract_gpu_model_from_jwt({"eat_token": 12345}) == ""
        assert extract_gpu_model_from_jwt({"eat_token": None}) == ""

    def test_eat_token_malformed_jwt(self):
        assert extract_gpu_model_from_jwt({"eat_token": "not-a-jwt"}) == ""
        assert extract_gpu_model_from_jwt({"eat_token": "a.b.c.d.e"}) == ""


class TestVerifyAttestationNewFields:
    @pytest.mark.asyncio
    async def test_enclave_and_gpu_model_populated(self):
        report_with_enclave = {
            "enclave_measurement": "enclave_abc",
            "model_attestations": [
                {
                    "signing_address": "0xABCD",
                    "nvidia_payload": '{"evidence": "test"}',
                },
            ],
        }
        jwt = _make_jwt({
            "x-nvidia-overall-att-result": True,
            "x-nvidia-hwmodel": "NVIDIA A100",
        })
        nvidia_resp = {"eat_token": jwt}

        with (
            patch(
                "src.attestation.verifier.fetch_attestation_report",
                new_callable=AsyncMock,
                return_value=report_with_enclave,
            ),
            patch(
                "src.attestation.verifier.verify_gpu_attestation",
                new_callable=AsyncMock,
                return_value=nvidia_resp,
            ),
        ):
            result = await verify_attestation("test-model")

        assert result.success is True
        assert result.enclave_measurement == "enclave_abc"
        assert result.gpu_model == "NVIDIA A100"
