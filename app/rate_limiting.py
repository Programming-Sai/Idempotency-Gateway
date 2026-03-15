import math
import time
import threading
from collections import defaultdict
from typing import Dict, Tuple, Optional

class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Args:
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
    
    def check(self, client_id: str) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed.
        
        Returns:
            (allowed, remaining, reset_time)
            - allowed: True if request is allowed
            - remaining: Number of requests remaining in this window
            - reset_time: Seconds until the window resets
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            
            # Clean old requests
            self._requests[client_id] = [
                ts for ts in self._requests[client_id] 
                if ts > cutoff
            ]
            
            # Calculate reset time (oldest request + window)
            if self._requests[client_id]:
                oldest = min(self._requests[client_id])
                reset_time = math.ceil(self.window_seconds - (now - oldest))
            else:
                reset_time = 0
            
            # Check limit
            if len(self._requests[client_id]) >= self.max_requests:
                return False, 0, int(reset_time)
            
            # Add this request
            self._requests[client_id].append(now)
            remaining = self.max_requests - len(self._requests[client_id])
            return True, remaining, int(reset_time)
    
    def get_client_id(self, ip: str, idempotency_key: str) -> str:
        """Generate a client identifier for rate limiting."""
        # Combine IP and key prefix to group related requests
        return ip