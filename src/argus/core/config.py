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
    # public demo: reads on /api/* need no key, every write still does (ADR-0014)
    demo_mode: bool = False
    max_body_bytes: int = 1_048_576  # request bodies above this are rejected with 413
    # POST /api/investigations (and the UI form) per client IP; 0 disables
    rate_limit_investigations_per_minute: int = 6
    # GET /api/search per client IP — the one anonymous endpoint with real CPU cost
    # (query embedding + pgvector scan); 0 disables
    rate_limit_search_per_minute: int = 60

    pipeline_version: int = 1
    embedding_provider: str = "fastembed"  # or "fake" (tests)

    # agent runtime: any OpenRouter model id, swappable via env; the resolved model
    # version is stamped on every ExecutionRecord (ADR-0005)
    openrouter_api_key: str = ""
    # "openrouter" (live) or "demo" (deterministic canned outputs, no LLM — ADR-0014)
    llm_provider: str = "openrouter"
    llm_model: str = "google/gemini-2.5-flash"
    llm_timeout_seconds: int = 120  # per LLM call; bounded retries handled by litellm
    llm_validation_retries: int = 2  # whole-call retries on truncated/invalid JSON output
    agent_retrieval_k: int = 8  # chunks per query fed to stance classification

    # SEC asks for a descriptive User-Agent with contact info on every request
    sec_user_agent: str = "Argus Research Platform srikrishna.vundavalli@gmail.com"
    sec_watchlist: list[str] = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSM", "AVGO"]
    sec_filing_types: list[str] = ["10-K", "10-Q", "8-K"]
    # feeds must answer 200 to an unauthenticated GET; CNBC (403) and Yahoo (429)
    # blocked every pass and were dropped
    rss_feeds: list[str] = [
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.federalreserve.gov/feeds/press_all.xml",
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

    # retrieval intelligence (PRD-V2 2.1-2.5)
    dedup_cosine_threshold: float = 0.97  # chunk embeddings at/above this are duplicates
    min_evidence_per_query: int = 2  # fewer results than this flags a plan gap
    rank_w_authority: float = 0.30  # source_rank weights (sum to 1.0)
    rank_w_freshness: float = 0.25
    rank_w_independence: float = 0.20
    rank_w_corroboration: float = 0.25
    rank_freshness_halflife_days: int = 180  # freshness halves every N days
    rank_corroboration_saturation: int = 5  # corroboration score saturates at N docs


@lru_cache
def get_settings() -> Settings:
    return Settings()
