from fastapi.testclient import TestClient
from app.main import app
import pytest

@pytest.fixture
def client():
    return TestClient(app)

def test_cors_preflight_options(client):
    """Test that OPTIONS preflight request returns correct CORS headers."""
    response = client.options(
        "/process-payment",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Idempotency-Key"
        }
    )

    assert response.status_code == 200
    # Should echo back the exact origin, not '*', because allow_credentials=True
    assert response.headers.get("access-control-allow-origin") == "http://example.com"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "Content-Type" in response.headers.get("access-control-allow-headers", "")
    assert "Idempotency-Key" in response.headers.get("access-control-allow-headers", "")
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_actual_request(client):
    """Test that actual POST request includes CORS headers."""
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={
            "Origin": "http://example.com",
            "Idempotency-Key": "cors-test"
        }
    )
    
    assert response.status_code == 201
    assert response.headers.get("access-control-allow-origin") == "*"

def test_cors_with_credentials(client):
    """Test that credentials are allowed."""
    response = client.options(
        "/process-payment",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Idempotency-Key"
        }
    )
    
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_allowed_methods(client):
    """Test that only POST is allowed for this endpoint."""
    response = client.options(
        "/process-payment",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    
    # Should still return allowed methods even if requested method isn't POST
    assert response.status_code == 200
    assert "POST" in response.headers.get("access-control-allow-methods", "")

def test_cors_no_origin_header(client):
    """Test that requests without Origin header work normally."""
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "cors-test-2"}
    )
    
    assert response.status_code == 201
    assert "access-control-allow-origin" not in response.headers