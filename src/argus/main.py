"""FastAPI composition root: JSON API + server-rendered UI in one app.
Run: uvicorn argus.main:app (make api)."""

from fastapi import FastAPI

from argus.api.routes import router as api_router
from argus.core.config import get_settings
from argus.core.logging import configure_logging
from argus.ui.views import router as ui_router

configure_logging(get_settings().log_level)
app = FastAPI(title="Argus", description="Enterprise Research Operating System")
app.include_router(api_router)
app.include_router(ui_router)
