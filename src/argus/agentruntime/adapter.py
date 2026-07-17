"""The only module that imports ADK (ADR-0005). One entry point: run a single
structured-output LLM call synchronously and return (parsed schema, ExecutionRecord).
Models are served via OpenRouter through ADK's LiteLlm wrapper, so the model is
plain config (ARGUS_LLM_MODEL) — swappable anytime, no code change. ADK types never
leave this module."""

import time
import uuid
from datetime import UTC, datetime

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ValidationError

from argus.agentruntime.schemas import ExecutionRecord
from argus.core.config import get_settings

APP_NAME = "argus"
USER_ID = "argus"


def run_structured[T: BaseModel](
    operation: str, instruction: str, message: str, schema: type[T]
) -> tuple[T, ExecutionRecord]:
    """One LLM call with structured JSON output. Validation errors propagate — an
    unparseable response must never silently become evidence. Providers sometimes
    return truncated JSON on a 200 (finish_reason "error"), which LiteLlm's
    transport retries never see — so the whole call retries on ValidationError
    (PRD-V2 4.5 execution recovery)."""
    settings = get_settings()
    last_error: ValidationError | None = None
    for _ in range(settings.llm_validation_retries + 1):
        try:
            return _run_once(operation, instruction, message, schema, settings)
        except ValidationError as exc:
            last_error = exc
    raise last_error


def _run_once[T: BaseModel](
    operation: str, instruction: str, message: str, schema: type[T], settings
) -> tuple[T, ExecutionRecord]:
    model = f"openrouter/{settings.llm_model}"
    runner = Runner(
        agent=LlmAgent(
            name=operation,
            model=LiteLlm(
                model=model,
                api_key=settings.openrouter_api_key,
                timeout=settings.llm_timeout_seconds,
                num_retries=2,
            ),
            instruction=instruction,
            output_schema=schema,
        ),
        app_name=APP_NAME,
        # ponytail: fresh throwaway session per call; argus persists its own state
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )

    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    response_text = ""
    for event in runner.run(
        user_id=USER_ID,
        session_id=uuid.uuid4().hex,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            response_text = "".join(p.text for p in event.content.parts if p.text)

    return schema.model_validate_json(response_text), ExecutionRecord(
        operation=operation,
        model=model,
        prompt=f"{instruction}\n\n{message}",
        response_text=response_text,
        started_at=started_at,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
