import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))
print(f"Added {root_dir} to sys.path")

import pytest
from app.storage import IdempotencyStore
from app.services import PaymentService
from app.rate_limiting import RateLimiter

@pytest.fixture(autouse=True)
def setup_app_state():
    from app.main import app
    processing_delay = 2
    num_requests = 5
    window_seconds = (processing_delay * num_requests) + 10  # buffer on top

    store = IdempotencyStore()
    service = PaymentService(store, processing_delay=processing_delay)
    rate_limiter = RateLimiter(max_requests=num_requests, window_seconds=window_seconds)
    app.state.store = store
    app.state.payment_service = service
    app.state.rate_limiter = rate_limiter
    yield
    

@pytest.fixture
def fresh_store(setup_app_state):
    """Create a fresh store and inject it into both app.state.store and the service."""
    from app.main import app
    new_store = IdempotencyStore(ttl_seconds=86400)
    new_service = PaymentService(new_store)
    app.state.store = new_store
    app.state.payment_service = new_service

    # Guarantee they share the same store instance
    assert app.state.store is app.state.payment_service.store

    yield new_store