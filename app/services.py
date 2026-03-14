import time
from datetime import datetime, timezone
from fastapi import HTTPException, status

from app.storage import IdempotencyStore, IdempotencyRecord, RecordStatus
from app.hashing import generate_request_hash

class PaymentService:
    def __init__(self, store: IdempotencyStore):
        self.store = store
    
    def process_payment(
        self, 
        idempotency_key: str, 
        amount: int, 
        currency: str
    ) -> dict:
        request_hash = generate_request_hash({"amount": amount, "currency": currency})
        
        # Try to claim this key (atomic operation, lock held briefly)
        claimed = self.store.claim(idempotency_key, request_hash)
        
        if not claimed:
            # Key already exists - get it
            existing = self.store.get(idempotency_key)
            
            # Validate body matches
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a different request body."
                )
            
            # If still processing, wait for completion
            if existing.status == RecordStatus.PROCESSING:
                completed = self.store.await_completion(idempotency_key)
                if not completed or completed.status != RecordStatus.COMPLETED:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Payment processing timed out"
                    )
                return {
                    "status_code": completed.response_status,
                    "body": completed.response_body,
                    "cached": True
                }
            
            # Already completed
            return {
                "status_code": existing.response_status,
                "body": existing.response_body,
                "cached": True
            }
        
        # We claimed it - process payment (NO LOCK HELD)
        time.sleep(2)
        
        response_body = {
            "message": f"Charged {amount} {currency}",
            "status": "success"
        }
        
        # Store result and signal waiters
        self.store.complete(idempotency_key, 201, response_body)
        
        return {
            "status_code": 201,
            "body": response_body,
            "cached": False
        }