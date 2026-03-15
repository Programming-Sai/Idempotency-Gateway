from fastapi import FastAPI, Header, status, Request  # Add Request here
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware  
from app.models import PaymentRequest, PaymentResponse, ErrorResponse
from app.rate_limiting import RateLimiter
from app.services import PaymentService
from app.storage import IdempotencyStore
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.store = IdempotencyStore(ttl_seconds=settings.idempotency_ttl_seconds)  
    app.state.payment_service = PaymentService(app.state.store)
    app.state.rate_limiter = RateLimiter(max_requests=settings.rate_limit_max_requests, window_seconds=settings.rate_limit_window_seconds)
    yield

app = FastAPI(
    title="Idempotency Gateway",
    description="""
    A payment processing API that guarantees exactly-once execution using idempotency keys.
    
    Features
    - Idempotency: Same key + same body = cached response
    - Conflict Detection: Same key + different body = 409 error
    - Race Conditions: Concurrent requests handled safely
    - Rate Limiting: 5 requests per minute per IP
    - TTL: Keys expire after 24 hours
    - CORS: Enabled for browser clients
    
    How to Use
    1. Generate a unique UUID for each payment attempt
    2. Send it in the `Idempotency-Key` header
    3. Retry safely if you don't get a response
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # In production, replace with specific domains
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
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
def health():
    return {"message": "Idempotency Gateway is running", "status": "healthy"}



@app.post(
    "/process-payment",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process a payment with idempotency guarantee",
    description="""
    Process a payment exactly once using an idempotency key.
    
    - First request: Processes payment, returns 201
    - Duplicate request: Returns cached response with X-Cache-Hit: true
    - Conflict: Same key, different body → 409 error
    - Rate limited: Over 5 requests/minute → 429 error
    """,
    responses={
        201: {"description": "Payment processed successfully"},
        409: {"model": ErrorResponse, "description": "Idempotency key conflict"},
        422: {"model": ErrorResponse, "description": "General validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
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