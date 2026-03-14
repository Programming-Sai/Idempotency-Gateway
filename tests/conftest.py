import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))
print(f"Added {root_dir} to sys.path")

import pytest
from app.storage import IdempotencyStore
from app.services import PaymentService

@pytest.fixture(autouse=True)
def setup_app_state():
    """Always reinitialize app state before each test — no stale state."""
    from app.main import app
    store = IdempotencyStore()
    service = PaymentService(store)
    app.state.store = store
    app.state.payment_service = service
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