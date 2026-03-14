from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.models import PaymentRequest, PaymentResponse, ErrorResponse
from app.services import PaymentService
from app.storage import IdempotencyStore

# Initialize store and service
store = IdempotencyStore()
payment_service = PaymentService(store)
app = FastAPI(
    title="Idempotency Gateway",
    description="Payment idempotency layer for FinSafe Transactions",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "Idempotency Gateway is running", "status": "healthy"}



@app.post(
    "/process-payment",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse}
    }
)
def process_payment(
    request: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    result = payment_service.process_payment(
        idempotency_key=idempotency_key,
        amount=request.amount,
        currency=request.currency
    )
    
    # Create response with appropriate headers
    response = JSONResponse(
        status_code=result["status_code"],
        content=result["body"]
    )
    
    if result["cached"]:
        response.headers["X-Cache-Hit"] = "true"
    
    return response