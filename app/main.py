from fastapi import FastAPI

app = FastAPI(
    title="Idempotency Gateway",
    description="Payment idempotency layer for FinSafe Transactions",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Idempotency Gateway is running", "status": "healthy"}
