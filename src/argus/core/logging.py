"""Structured JSON logging (Design Bible §8: every failure observable)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# set by the request-ID middleware (src/argus/main.py); None outside a request
# (worker/CLI logs), so it's opt-in to the log entry rather than always-present.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (rid := request_id.get()) is not None:
            entry["request_id"] = rid
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "context", None)
        if extra:
            entry.update(extra)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
