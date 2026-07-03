import json
import logging

from argus.core.config import Settings
from argus.core.logging import JsonFormatter


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.log_level == "INFO"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ARGUS_LOG_LEVEL", "DEBUG")
    assert Settings(_env_file=None).log_level == "DEBUG"


def test_json_formatter_emits_valid_json():
    record = logging.LogRecord(
        "argus.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
    )
    record.context = {"stage": "parse"}
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["stage"] == "parse"
