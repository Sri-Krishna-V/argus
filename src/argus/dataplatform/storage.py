"""Content-addressed raw store (Bible §14: raw data is permanent, never modified).
Filesystem-backed, object-store-shaped: swap for S3 by reimplementing these four
functions."""

import hashlib
from pathlib import Path

from argus.core.config import get_settings


def _root() -> Path:
    return get_settings().raw_store_path


def write_raw(content: bytes) -> tuple[str, str]:
    """Store bytes by sha256. Returns (checksum, relative path). Idempotent."""
    checksum = hashlib.sha256(content).hexdigest()
    path = _root() / checksum[:2] / checksum
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return checksum, str(path)


def read_raw(raw_path: str) -> bytes:
    return Path(raw_path).read_bytes()


def write_parsed(checksum: str, pipeline_version: int, text: str) -> Path:
    """Parsed layer is derived and disposable; path is deterministic."""
    path = _root().parent / "parsed" / f"{checksum}_v{pipeline_version}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def read_parsed(checksum: str, pipeline_version: int) -> str:
    return (_root().parent / "parsed" / f"{checksum}_v{pipeline_version}.txt").read_text()
