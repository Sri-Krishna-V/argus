"""FastAPI composition root: JSON API + server-rendered UI in one app.
Run: uvicorn argus.main:app (make api)."""

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from argus.api.routes import router as api_router
from argus.core.config import get_settings
from argus.core.logging import configure_logging, request_id
from argus.ui.views import router as ui_router

configure_logging(get_settings().log_level)
app = FastAPI(title="Argus", description="Enterprise Research Operating System")
app.include_router(api_router)
app.include_router(ui_router)


# ponytail: one middleware for both concerns (request-ID + API-key auth) — fewer
# moving parts than two. Starlette middleware must be async; neither concern here
# does I/O (header checks, uuid gen), so ADR-0004's sync rule doesn't apply.
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
    token = request_id.set(rid)
    try:
        settings = get_settings()
        if settings.api_key and request.url.path.startswith("/api/"):
            auth = request.headers.get("Authorization", "")
            bearer = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            key = request.headers.get("X-API-Key") or bearer
            if key != settings.api_key:
                response = JSONResponse({"detail": "invalid or missing API key"}, status_code=401)
                response.headers["X-Request-ID"] = rid
                return response
        response = await call_next(request)
    finally:
        request_id.reset(token)
    response.headers["X-Request-ID"] = rid
    return response
