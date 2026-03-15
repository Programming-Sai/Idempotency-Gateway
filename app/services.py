import time
from fastapi import HTTPException, status
from app.config import settings
from app.storage import IdempotencyStore, RecordStatus
from app.hashing import generate_request_hash

class PaymentService:
    def __init__(self, store: IdempotencyStore, processing_delay: float = settings.payment_processing_delay):
        self.store = store
        self.processing_delay = processing_delay
    
    def process_payment(
        self, 
        idempotency_key: str, 
        amount: int, 
        currency: str
    ) -> dict:
        request_hash = generate_request_hash({"amount": amount, "currency": currency})
        
        claimed = self.store.claim(idempotency_key, request_hash)
        
        if not claimed:
            existing = self.store.get(idempotency_key)
            
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a different request body."
                )
            
            # If still processing, wait for completion. really tricky operations. had to even switch locking mechanism multiple times
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
            
            return {
                "status_code": existing.response_status,
                "body": existing.response_body,
                "cached": True
            }
        
        time.sleep(self.processing_delay)
        
        response_body = {
            "message": f"Charged {amount} {currency}",
            "status": "success"
        }
        
        self.store.complete(idempotency_key, 201, response_body)
        
        return {
            "status_code": 201,
            "body": response_body,
            "cached": False
        }