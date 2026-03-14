import asyncio
from datetime import datetime
from fastapi import HTTPException, status

from app.storage import IdempotencyStore, IdempotencyRecord, RecordStatus
from app.hashing import hash_request_body



class PaymentService:
    def __init__(self, store: IdempotencyStore):
        self.store = store
    
    async def process_payment(
        self, 
        idempotency_key: str, 
        amount: int, 
        currency: str
    ) -> dict:
        """
        Process a payment with idempotency guarantees.
        
        Returns:
            dict: Response to send to client
        
        Raises:
            HTTPException: 409 if key reused with different body
        """
        # Generate hash of request
        request_body = {"amount": amount, "currency": currency}
        request_hash = hash_request_body(request_body)
        
        # Get the lock for this key
        lock = await self.store.get_lock(idempotency_key)
        
        # This is where the magic happens - only one request per key gets through
        async with lock:
            # Check if we've seen this key before
            existing = self.store.get(idempotency_key)
            
            if existing:
                # Key exists - check if request body matches
                if existing.request_hash != request_hash:
                    # Same key, different body → CONFLICT
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key already used for a different request body."
                    )
                
                if existing.status != RecordStatus.COMPLETED:
                    # This shouldn't happen due to lock, but just in case
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Inconsistent state"
                    )
                
                # Same key, same body → DUPLICATE
                # Return cached response
                return {
                    "status_code": existing.response_status,
                    "body": existing.response_body,
                    "cached": True  # We'll use this to set X-Cache-Hit header
                }
            
            # First time seeing this key → PROCESS
            # Create processing record
            record = IdempotencyRecord(
                request_hash=request_hash,
                response_status=None,  # We'll set this
                response_body=None,  # We'll fill this after processing
                status=RecordStatus.PROCESSING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Store processing record
            self.store.save(idempotency_key, record)
        
        # Simulate payment processing (2 seconds)
        await asyncio.sleep(2)
        
        # Generate response
        response_body = {
            "message": f"Charged {amount} {currency}",
            "status": "success"
        }
        
        # Update record with completed status
        completed_record = IdempotencyRecord(
            request_hash=request_hash,
            response_status=201,
            response_body=response_body,
            status=RecordStatus.COMPLETED,
            created_at=record.created_at, 
            updated_at=datetime.utcnow()
        )
        self.store.save(idempotency_key, completed_record)
        
        return {
            "status_code": 201,
            "body": response_body,
            "cached": False
        }