# tests/test_rate_limit.py
from fastapi.testclient import TestClient
from app.main import app
from app.rate_limiting import RateLimiter
from unittest.mock import patch
import time
import pytest
from app.config import settings


@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def setup_rate_limiter():
    if not hasattr(app.state, 'rate_limiter'):
        app.state.rate_limiter = RateLimiter(max_requests=settings.rate_limit_max_requests, window_seconds=settings.rate_limit_window_seconds)
    app.state.rate_limiter._requests.clear()
    app.state.rate_limiter.window_seconds = settings.rate_limit_window_seconds  # reset window each test
    yield


def test_rate_limit_allows_requests_under_limit(client):
    with patch("app.services.time.sleep"):
        for i in range(5):
            response = client.post(
                "/process-payment",
                json={"amount": 100, "currency": "GHS"},
                headers={"Idempotency-Key": f"rate-test-{i}"}
            )
            assert response.status_code == 201
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            assert remaining == 4 - i


def test_rate_limit_blocks_requests_over_limit(client):
    with patch("app.services.time.sleep"):
        for i in range(5):
            response = client.post(
                "/process-payment",
                json={"amount": 100, "currency": "GHS"},
                headers={"Idempotency-Key": f"rate-test-{i}"}
            )
            assert response.status_code == 201

        response = client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": "rate-test-6"}
        )
        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded. Try again later."
        assert response.headers.get("X-RateLimit-Remaining") == "0"
        assert response.headers.get("Retry-After") is not None


def test_rate_limit_resets_after_window(client):
    for i in range(5):
        response = client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={
                "Idempotency-Key": f"reset-test-{i}",
                "X-Forwarded-For": "192.168.1.100"
            }
        )
        assert response.status_code == 201

    # 6th should be immediately blocked
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={
            "Idempotency-Key": "reset-test-6",
            "X-Forwarded-For": "192.168.1.100"
        }
    )
    assert response.status_code == 429

    reset_seconds = int(response.headers.get("X-RateLimit-Reset", 2))
    print("Resets", response.headers)
    time.sleep(reset_seconds + 0.5)

    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={
            "Idempotency-Key": "reset-test-7",
            "X-Forwarded-For": "192.168.1.100"
        }
    )
    assert response.status_code == 201


def test_different_clients_have_separate_limits(client):
    with patch("app.services.time.sleep"):
        for i in range(5):
            response = client.post(
                "/process-payment",
                json={"amount": 100, "currency": "GHS"},
                headers={
                    "Idempotency-Key": f"separate-test-client1-{i}",
                    "X-Forwarded-For": "192.168.1.1"
                }
            )
            assert response.status_code == 201

        # Client 2 uses different keys so it doesn't hit the idempotency cache
        for i in range(5):
            response = client.post(
                "/process-payment",
                json={"amount": 100, "currency": "GHS"},
                headers={
                    "Idempotency-Key": f"separate-test-client2-{i}",
                    "X-Forwarded-For": "192.168.1.2"
                }
            )
            assert response.status_code == 201
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            assert remaining == 4 - i

        # Client 1 should now be blocked
        response = client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={
                "Idempotency-Key": "separate-test-client1-6",
                "X-Forwarded-For": "192.168.1.1"
            }
        )
        assert response.status_code == 429


def test_rate_limit_headers_present(client):
    with patch("app.services.time.sleep"):
        response = client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": "headers-test"}
        )

        assert response.status_code == 201
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers.get("X-RateLimit-Limit") == "5"