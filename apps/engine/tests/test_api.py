"""주문 API 엔드포인트 테스트."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.attestation.verifier import AttestationResult
from src.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


class TestCreateOrder:
    def test_create_order_success(self, client):
        resp = client.post(
            "/order",
            json={
                "token_pair": "BNB/USDT",
                "side": "buy",
                "amount": "100",
                "limit_price": "600",
                "wallet_address": "0xAlice",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_pair"] == "BNB/USDT"
        assert data["side"] == "buy"
        assert data["amount"] == "100"
        assert data["filled_amount"] == "0"
        assert data["remaining"] == "100"
        assert data["status"] == "pending"
        assert data["order_id"]

    def test_create_order_invalid_amount(self, client):
        resp = client.post(
            "/order",
            json={
                "token_pair": "BNB/USDT",
                "side": "buy",
                "amount": "-1",
                "limit_price": "600",
                "wallet_address": "0xAlice",
            },
        )
        assert resp.status_code == 422

    def test_create_order_missing_field(self, client):
        resp = client.post("/order", json={"token_pair": "BNB/USDT", "side": "buy"})
        assert resp.status_code == 422


class TestGetOrderStatus:
    def test_get_existing_order(self, client):
        create_resp = client.post(
            "/order",
            json={
                "token_pair": "BNB/USDT",
                "side": "sell",
                "amount": "50",
                "limit_price": "610",
                "wallet_address": "0xBob",
            },
        )
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]

        resp = client.get(f"/order/{order_id}/status")
        assert resp.status_code == 200
        assert resp.json()["order_id"] == order_id

    def test_get_nonexistent_order(self, client):
        resp = client.get("/order/nonexistent/status")
        assert resp.status_code == 404


class TestCancelOrder:
    def test_cancel_existing_order(self, client):
        create_resp = client.post(
            "/order",
            json={
                "token_pair": "BNB/USDT",
                "side": "buy",
                "amount": "30",
                "limit_price": "600",
                "wallet_address": "0xCharlie",
            },
        )
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]

        resp = client.delete(f"/order/{order_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_nonexistent_order(self, client):
        resp = client.delete("/order/nonexistent")
        assert resp.status_code == 404

    def test_cancel_already_cancelled(self, client):
        create_resp = client.post(
            "/order",
            json={
                "token_pair": "BNB/USDT",
                "side": "sell",
                "amount": "20",
                "limit_price": "600",
                "wallet_address": "0xDave",
            },
        )
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]
        client.delete(f"/order/{order_id}")

        resp = client.delete(f"/order/{order_id}")
        assert resp.status_code == 400


class TestWebSocket:
    def test_ws_connect_disconnect(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.close()


class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAttestationVerify:
    def test_success(self, client, monkeypatch):
        monkeypatch.setattr("src.routes.NEARAI_CLOUD_API_KEY", "test-key")
        mock_result = AttestationResult(
            success=True,
            signing_addresses=["0xABC"],
            gpu_verified=True,
            gpu_results=[{"index": 0, "passed": True}],
            enclave_measurement="enclave_abc",
            gpu_model="NVIDIA H100",
        )
        with patch(
            "src.routes.verify_attestation",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get("/attestation/verify")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["enclave_measurement"] == "enclave_abc"
        assert data["signing_addresses"] == ["0xABC"]
        assert data["gpu_verified"] is True
        assert data["gpu_model"] == "NVIDIA H100"
        assert data["code_integrity"] == "matching_engine v0.1.0"
        # timestamp는 ISO 8601 파싱 가능한지 확인
        datetime.fromisoformat(data["timestamp"])

    def test_api_key_not_configured(self, client, monkeypatch):
        monkeypatch.setattr("src.routes.NEARAI_CLOUD_API_KEY", "")
        resp = client.get("/attestation/verify")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    def test_verification_failure(self, client, monkeypatch):
        monkeypatch.setattr("src.routes.NEARAI_CLOUD_API_KEY", "test-key")
        mock_result = AttestationResult(
            success=False,
            error="attestation report 조회 실패",
        )
        with patch(
            "src.routes.verify_attestation",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get("/attestation/verify")

        assert resp.status_code == 503
        assert "조회 실패" in resp.json()["detail"]

    def test_unexpected_exception(self, client, monkeypatch):
        monkeypatch.setattr("src.routes.NEARAI_CLOUD_API_KEY", "test-key")
        with patch(
            "src.routes.verify_attestation",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            resp = client.get("/attestation/verify")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"
