import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

class RecordStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"

@dataclass
class IdempotencyRecord:
    request_hash: str
    response_status: Optional[int]
    response_body: Optional[dict]
    status: RecordStatus
    created_at: datetime
    updated_at: datetime

class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 86400):
        self._records: Dict[str, IdempotencyRecord] = {}
        self._events: Dict[str, threading.Event] = {}
        self._records_lock = threading.Lock()  
        self.ttl_seconds = ttl_seconds

    def _is_expired(self, record: IdempotencyRecord) -> bool:
        """Check if a completed record has expired."""
        if record.status != RecordStatus.COMPLETED:
            return False
        age = (datetime.now(timezone.utc) - record.created_at).total_seconds()
        return age > self.ttl_seconds
    
    def cleanup_expired(self):
        """Manually trigger cleanup (can be called periodically)."""
        with self._records_lock:
            expired = [
                key for key, record in self._records.items()
                if self._is_expired(record)
            ]
            for key in expired:
                del self._records[key]
            return len(expired)

        
    def claim(self, key: str, request_hash: str) -> bool:
        with self._records_lock:
            existing = self._records.get(key)
            if existing:
                print(f"claim: key={key}, exists, status={existing.status}")
                if existing.status == RecordStatus.COMPLETED and self._is_expired(existing):
                    print(f"claim: expired, removing")
                    del self._records[key]
                    if key in self._events:
                        del self._events[key]
                    # Continue to create new record
                else:
                    print(f"claim: exists and not expired, returning False")
                    return False
            
            print(f"claim: creating new record for {key}")
            self._records[key] = IdempotencyRecord(
                request_hash=request_hash,
                response_status=None,
                response_body=None,
                status=RecordStatus.PROCESSING,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            return True
            
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get record if exists and not expired."""
        with self._records_lock:
            record = self._records.get(key)
            if not record:
                return None
            
            # Only check expiry for COMPLETED records
            if record.status == RecordStatus.COMPLETED and self._is_expired(record):
                del self._records[key]
                if key in self._events:
                    del self._events[key]
                return None
            
            return record
                

    
    def complete(self, key: str, status_code: int, body: dict):
        """Mark a key as completed and signal waiters"""
        with self._records_lock:
            if key in self._records:
                record = self._records[key]
                record.status = RecordStatus.COMPLETED
                record.response_status = status_code
                record.response_body = body
                record.updated_at = datetime.now(timezone.utc)
                
                # Signal anyone waiting
                if key in self._events:
                    self._events[key].set()
                    del self._events[key]
    
    def await_completion(self, key: str, timeout: float = 30.0) -> Optional[IdempotencyRecord]:
        """Wait for a processing key to complete. Returns completed record or None on timeout."""
        # Get or create event
        with self._records_lock:
            if key not in self._events:
                self._events[key] = threading.Event()
            event = self._events[key]
        
        # Wait outside lock
        event.wait(timeout)
        
        # Return whatever we have now
        with self._records_lock:
            return self._records.get(key)