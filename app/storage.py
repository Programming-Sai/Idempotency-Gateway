import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class IdempotencyRecord:
    """What we store for each idempotency key"""
    request_hash: str
    response_status: int
    response_body: dict
    status: str  # "processing" or "completed"
    created_at: datetime

class IdempotencyStore:
    def __init__(self):
        # Main storage: key -> record
        self._records: Dict[str, IdempotencyRecord] = {}
        
        # Per-key locks for race condition
        self._locks: Dict[str, asyncio.Lock] = {}
        
        # Lock for modifying the _locks dict itself
        self._dict_lock = asyncio.Lock()
    
    async def get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific key"""
        async with self._dict_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]
    
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Retrieve a record if it exists"""
        return self._records.get(key)
    
    def save(self, key: str, record: IdempotencyRecord) -> None:
        """Store a completed record"""
        self._records[key] = record
    
    def exists(self, key: str) -> bool:
        """Check if key has been used"""
        return key in self._records