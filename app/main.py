from fastapi import FastAPI, Header, HTTPException, status, Request  # Add Request here
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse

from app.models import PaymentRequest, PaymentResponse, ErrorResponse
from app.rate_limiting import RateLimiter
from app.services import PaymentService
from app.storage import IdempotencyStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.store = IdempotencyStore()
    app.state.payment_service = PaymentService(app.state.store)
    yield
    # Shutdown
    # (cleanup if needed)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.store = IdempotencyStore(ttl_seconds=86400)  # 24 hours default
    app.state.payment_service = PaymentService(app.state.store)
    app.state.rate_limiter = RateLimiter(max_requests=5, window_seconds=60)  # 5 per minute
    yield
    # Shutdown (cleanup if needed)

app = FastAPI(
    title="Idempotency Gateway",
    description="Payment idempotency layer with rate limiting",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to payment endpoint."""
    if request.url.path == "/process-payment":
        # Get client IP — always use the first IP from X-Forwarded-For
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host

        allowed, remaining, reset = app.state.rate_limiter.check(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "X-RateLimit-Limit": str(app.state.rate_limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                    "Retry-After": str(reset)
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(app.state.rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response

    return await call_next(request)


@app.get("/")
def root():
    return {"message": "Idempotency Gateway is running", "status": "healthy"}



@app.post(
    "/process-payment",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse}
    }
)
def process_payment(
    request: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    result = app.state.payment_service.process_payment(
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