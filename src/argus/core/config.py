from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARGUS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://argus:argus@localhost:5432/argus"
    raw_store_path: Path = Path("data/raw")
    log_level: str = "INFO"

    # when set, /api/* requires X-API-Key or Bearer token; empty disables auth (dev default)
    api_key: str = ""
    max_body_bytes: int = 1_048_576  # request bodies above this are rejected with 413
    # POST /api/investigations (and the UI form) per client IP; 0 disables
    rate_limit_investigations_per_minute: int = 6

    pipeline_version: int = 1
    embedding_provider: str = "fastembed"  # or "fake" (tests)

    # agent runtime: any OpenRouter model id, swappable via env; the resolved model
    # version is stamped on every ExecutionRecord (ADR-0005)
    openrouter_api_key: str = ""
    llm_model: str = "google/gemini-2.5-flash"
    llm_timeout_seconds: int = 120  # per LLM call; bounded retries handled by litellm
    agent_retrieval_k: int = 8  # chunks per query fed to stance classification

    # SEC asks for a descriptive User-Agent with contact info on every request
    sec_user_agent: str = "Argus Research Platform srikrishna.vundavalli@gmail.com"
    sec_watchlist: list[str] = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSM", "AVGO"]
    sec_filing_types: list[str] = ["10-K", "10-Q", "8-K"]
    rss_feeds: list[str] = [
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://finance.yahoo.com/news/rssindex",
    ]

    # connector schedules, seconds (Bible: RSS 15m, SEC hourly, profiles daily)
    schedule_rss: int = 900
    schedule_sec: int = 3600
    schedule_profiles: int = 86400
    worker_poll_seconds: float = 2.0
    job_lease_seconds: int = 600  # running past this with no completion is presumed crashed

    max_fetch_bytes: int = 26_214_400  # connector downloads abort past this (25 MB)
    db_statement_timeout_ms: int = 30_000  # kills runaway queries server-side
    embed_batch_size: int = 128  # chunks per provider.embed() call


@lru_cache
def get_settings() -> Settings:
    return Settings()
