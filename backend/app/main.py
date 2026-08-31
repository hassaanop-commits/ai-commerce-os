from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware

app = FastAPI(title="AI Commerce OS API")

app.add_middleware(CSRFMiddleware)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health_check():
    return {"status": "ok"}
