from pydantic import BaseModel, Field, validator
from typing import Optional

class PaymentRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount in smallest currency unit")
    currency: str = Field(min_length=3, max_length=3, description="ISO currency code")
    
    @validator('currency')
    def currency_must_be_uppercase(cls, v):
        return v.upper()

class PaymentResponse(BaseModel):
    message: str
    status: str = "success"

class ErrorResponse(BaseModel):
    detail: str