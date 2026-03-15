import hashlib
import json
from typing import Dict, Any



def generate_request_hash(body: Dict[str, Any]) -> str:
    """
    Generate a SHA-256 hash of the request body.
    """ 
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

