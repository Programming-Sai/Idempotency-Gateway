from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Rate Limiting
    rate_limit_max_requests: int = 5
    rate_limit_window_seconds: int = 60
    
    # Idempotency
    idempotency_ttl_seconds: int = 86400
    
    # CORS
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True

    payment_processing_delay: float = 2.0
    await_completion_timeout: float = 30.0
    
    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

settings = Settings()