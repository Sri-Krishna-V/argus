"""FastAPI composition root: JSON API + static React SPA (web/dist) in one app.
Run: uvicorn argus.main:app (make api)."""

import secrets
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from argus.api.routes import router as api_router
from argus.core.config import get_settings
from argus.core.logging import configure_logging, request_id
from argus.investigations.orchestrator import register as _register_investigation_handler

configure_logging(get_settings().log_level)
_register_investigation_handler()
app = FastAPI(title="Argus", description="Enterprise Research Operating System")
app.include_router(api_router)

_WEB_DIST = Path(__file__).parent.parent.parent / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="spa-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(_WEB_DIST / "index.html")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
    ),
}

# rate-limited routes: (method, path) -> settings attribute holding its per-minute cap
_RATE_LIMITED = {
    ("POST", "/api/investigations"): "rate_limit_investigations_per_minute",
    ("GET", "/api/search"): "rate_limit_search_per_minute",
}
# demo mode leaves these open on /api/*; everything else still needs the API key
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# ponytail: in-process bucket; move to a proxy/redis limiter if multiple API replicas
_buckets: dict[str, tuple[float, float]] = {}  # client key -> (tokens, last_refill_monotonic)
_buckets_lock = threading.Lock()


def _rate_limited(key: str, rate_per_minute: int) -> bool:
    """Token bucket, refilled continuously at rate_per_minute/60s; burst == rate_per_minute."""
    if rate_per_minute <= 0:
        return False
    now = time.monotonic()
    with _buckets_lock:
        tokens, last = _buckets.get(key, (float(rate_per_minute), now))
        tokens = min(rate_per_minute, tokens + (now - last) * (rate_per_minute / 60.0))
        if tokens < 1:
            _buckets[key] = (tokens, now)
            return True
        _buckets[key] = (tokens - 1, now)
        return False


def _with_security_headers(response, rid: str):
    response.headers["X-Request-ID"] = rid
    response.headers.update(SECURITY_HEADERS)
    return response


# ponytail: one middleware for both concerns (request-ID + API-key auth) — fewer
# moving parts than two. Starlette middleware must be async; neither concern here
# does I/O (header checks, uuid gen), so ADR-0004's sync rule doesn't apply.
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
    token = request_id.set(rid)
    try:
        settings = get_settings()

        # ponytail: Content-Length check only; a lying client is bounded by uvicorn's own limits
        content_length = request.headers.get("Content-Length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > settings.max_body_bytes
        ):
            return _with_security_headers(
                JSONResponse({"detail": "request body too large"}, status_code=413), rid
            )

        client = request.client.host if request.client else "unknown"
        limit_attr = _RATE_LIMITED.get((request.method, request.url.path))
        if limit_attr and _rate_limited(f"{limit_attr}:{client}", getattr(settings, limit_attr)):
            return _with_security_headers(
                JSONResponse({"detail": "rate limit exceeded"}, status_code=429), rid
            )

        # demo deployments serve reads anonymously; writes always need the key (ADR-0014)
        needs_key = request.url.path.startswith("/api/") and not (
            settings.demo_mode and request.method in _SAFE_METHODS
        )
        if settings.api_key and needs_key:
            auth = request.headers.get("Authorization", "")
            bearer = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            key = request.headers.get("X-API-Key") or bearer
            if not secrets.compare_digest(key or "", settings.api_key):
                return _with_security_headers(
                    JSONResponse({"detail": "invalid or missing API key"}, status_code=401), rid
                )
        response = await call_next(request)
    finally:
        request_id.reset(token)
    return _with_security_headers(response, rid)
