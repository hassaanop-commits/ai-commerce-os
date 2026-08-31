from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.logging import configure_logging
from app.core.request_context import RequestIDMiddleware
from app.core.sentry import configure_sentry

configure_logging()
configure_sentry()

app = FastAPI(title="AI Commerce OS API")

app.add_middleware(CSRFMiddleware)
# Added after CSRFMiddleware so it wraps *outside* it (Starlette makes the
# most-recently-added middleware outermost) -- request ID/route context
# needs to exist before CSRF (or anything else) runs, and the summary log
# line needs the final status code after everything downstream completes.
app.add_middleware(RequestIDMiddleware)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health_check():
    return {"status": "ok"}
