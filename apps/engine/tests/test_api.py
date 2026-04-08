"""주문 API 엔드포인트 테스트."""

import pytest
from fastapi.testclient import TestClient

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
