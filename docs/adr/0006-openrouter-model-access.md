# ADR-0006: Models via OpenRouter, orchestration via ADK

**Status:** Accepted · **Serves:** Design Bible §10 (framework independence)

## Context

ADR-0005 confines AI to `agentruntime/adapter.py` and named Gemini as the model.
Binding the runtime to one provider's API makes model choice a code change; we want
the model to be swappable at any time without touching code.

## Decision

Google ADK remains the orchestration framework (as documented), but models are served
through OpenRouter via ADK's `LiteLlm` wrapper. The model is configuration:
`ARGUS_LLM_MODEL` (any OpenRouter model id, e.g. `google/gemini-2.5-flash`), with
`ARGUS_OPENROUTER_API_KEY` for auth. The full model id is stamped on every
`ExecutionRecord`, so replay always knows exactly what produced an output.

## Consequences

- Changing models is an env-var edit — no deploy, no code review, provider-agnostic.
- One extra dependency (`litellm`) and one HTTP hop through OpenRouter; acceptable at
  V1 call volumes.
- Structured output rides ADK's `output_schema` → LiteLLM `response_format`
  translation, which adapts per provider; adapter-side pydantic validation remains the
  hard gate either way (ADR-0005: unparseable output never becomes evidence).
