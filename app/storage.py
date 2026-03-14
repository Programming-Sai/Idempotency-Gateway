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
    def __init__(self):
        self._records: Dict[str, IdempotencyRecord] = {}
        self._events: Dict[str, threading.Event] = {}
        self._records_lock = threading.Lock()  # Single lock for all operations
    
    def claim(self, key: str, request_hash: str) -> bool:
        """
        Try to claim this key for processing.
        Returns True if this caller should process, False if already exists.
        """
        with self._records_lock:
            if key in self._records:
                return False
            
            # Create processing record
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
        """Get record if exists"""
        with self._records_lock:
            return self._records.get(key)
    
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