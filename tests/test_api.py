from datetime import datetime, timezone

from fastapi.testclient import TestClient
from app.main import app
from app.storage import IdempotencyStore, RecordStatus
from app.config import settings
import concurrent.futures
import time
import pytest

@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)

@pytest.fixture
def fresh_store():
    """Create a fresh store for each test"""
    app.state.store = IdempotencyStore()
    yield

def test_first_request_success(client, fresh_store):
    """Test Story 1: First request processes with delay"""
    start = time.time()
    
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "test-1"}
    )
    
    elapsed = time.time() - start
    
    assert response.status_code == 201
    assert response.json() == {"message": "Charged 100 GHS", "status": "success"}
    assert elapsed >= settings.payment_processing_delay
    assert "x-cache-hit" not in response.headers

def test_duplicate_request_returns_cached(client, fresh_store):
    """Test Story 2: Duplicate returns cached response instantly"""
    # First request
    response1 = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "test-2"}
    )
    assert response1.status_code == 201
    
    # Second request (duplicate)
    start = time.time()
    response2 = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "test-2"}
    )
    elapsed = time.time() - start
    
    assert response2.status_code == 201
    assert response2.json() == response1.json()
    assert elapsed < 1.0
    assert response2.headers.get("x-cache-hit") == "true"

def test_same_key_different_body_returns_409(client, fresh_store):
    """Test Story 3: Same key with different body returns conflict"""
    # First request
    response1 = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "test-3"}
    )
    assert response1.status_code == 201
    
    # Second request with different amount
    response2 = client.post(
        "/process-payment",
        json={"amount": 500, "currency": "GHS"},
        headers={"Idempotency-Key": "test-3"}
    )
    
    assert response2.status_code == 409
    assert "different request body" in response2.json()["detail"]

def test_missing_idempotency_key(client, fresh_store):
    """Edge case: Missing header returns 422"""
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"}
    )
    assert response.status_code == 422

def test_invalid_amount(client, fresh_store):
    """Edge case: Amount must be positive"""
    response = client.post(
        "/process-payment",
        json={"amount": -10, "currency": "GHS"},
        headers={"Idempotency-Key": "test-4"}
    )
    assert response.status_code == 422

def test_invalid_currency(client, fresh_store):
    """Edge case: Currency must be 3 chars"""
    response = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GH"},
        headers={"Idempotency-Key": "test-5"}
    )
    assert response.status_code == 422

def test_race_condition_concurrent(client, fresh_store):
    """Test concurrent requests with same key"""
    key = "race-concurrent-test"
    
    def send_request(i):
        response = client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": key}
        )
        return response
    
    # Fire 5 requests concurrently
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_request, i) for i in range(5)]
        responses = [f.result() for f in futures]
    total_time = time.time() - start
    
    # All should succeed
    for response in responses:
        assert response.status_code == 201
    
    # Count cache hits
    cache_hits = sum(1 for r in responses if r.headers.get("x-cache-hit") == "true")
    assert cache_hits == 4  # One original, 4 cached
    assert total_time < 4.0  # Should be ~2s, not 10s

def test_lock_not_held_during_processing(client, fresh_store):
    """Verify that lock is released during processing (different keys run in parallel)"""
    def send_request(i):
        return client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": f"key-{i}"}  # Different keys!
        )
    
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_request, i) for i in range(5)]
        responses = [f.result() for f in futures]
    total_time = time.time() - start
    
    # All should succeed
    for response in responses:
        assert response.status_code == 201
    
    # With different keys, they should run in parallel
    # Total time should be ~2s, not 10s
    assert total_time < 3.0, f"Requests were serialized! Took {total_time}s"

def test_wait_does_not_block_other_keys(client, fresh_store):
    """Test that waiting for one key doesn't block requests with different keys"""
    slow_key = "slow-key"
    fast_key = "fast-key"
    
    def send_slow():
        return client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": slow_key}
        )
    
    def send_fast():
        # Small delay to ensure slow request starts first
        time.sleep(0.1)
        return client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": fast_key}
        )
    
    def send_duplicate_slow():
        time.sleep(0.2)
        return client.post(
            "/process-payment",
            json={"amount": 100, "currency": "GHS"},
            headers={"Idempotency-Key": slow_key}
        )
    
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        slow_future = executor.submit(send_slow)
        fast_future = executor.submit(send_fast)
        duplicate_future = executor.submit(send_duplicate_slow)
        
        slow_response = slow_future.result()
        fast_response = fast_future.result()
        duplicate_response = duplicate_future.result()
    total_time = time.time() - start
    
    # All should succeed
    assert slow_response.status_code == 201
    assert fast_response.status_code == 201
    assert duplicate_response.status_code == 201
    
    # Fast key should complete quickly (not blocked by slow key)
    # Duplicate should be cached
    assert duplicate_response.headers.get("x-cache-hit") == "true"
    
    # Total time should be ~2s, not 4s
    assert total_time < 3.0

def test_ttl_expiration(client, fresh_store):
    """Test that expired keys are treated as new requests."""
    # Set TTL to 1 second on BOTH the store reference and the service's internal store
    app.state.store.ttl_seconds = 1
    app.state.payment_service.store.ttl_seconds = 1  # ← this was the missing line
    print(f"\nTTL set to: {app.state.store.ttl_seconds}")

    # First request
    response1 = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "ttl-test"}
    )
    assert response1.status_code == 201
    assert response1.headers.get("x-cache-hit") is None
    print(f"Response1: {response1.status_code}, cache-hit: {response1.headers.get('x-cache-hit')}")

    # Wait for the simulated processing (2s sleep in service) to complete
    time.sleep(2.1)
    print("Processing complete")

    # Check record after completion
    with app.state.store._records_lock:
        if "ttl-test" in app.state.store._records:
            record = app.state.store._records["ttl-test"]
            age = (datetime.now(timezone.utc) - record.created_at).total_seconds()
            print(f"Record exists: status={record.status}, age={age:.2f}s, TTL={app.state.store.ttl_seconds}")
        else:
            print("Record does not exist after processing!")

    # Wait for TTL to expire
    print("Waiting for TTL to expire...")
    time.sleep(1.1)

    # Check record after TTL expiry
    with app.state.store._records_lock:
        if "ttl-test" in app.state.store._records:
            record = app.state.store._records["ttl-test"]
            age = (datetime.now(timezone.utc) - record.created_at).total_seconds()
            print(f"After TTL: record exists, age={age:.2f}s, expired={age > app.state.store.ttl_seconds}")
            if record.status == RecordStatus.COMPLETED and age > app.state.store.ttl_seconds:
                print("Record should be expired but still exists!")
        else:
            print("After TTL: record correctly removed")

    # Second request — should be treated as a brand new request, not a cache hit
    response2 = client.post(
        "/process-payment",
        json={"amount": 100, "currency": "GHS"},
        headers={"Idempotency-Key": "ttl-test"}
    )
    print(f"Response2: {response2.status_code}, cache-hit: {response2.headers.get('x-cache-hit')}")

    assert response2.status_code == 201
    assert response2.headers.get("x-cache-hit") is None
    
    