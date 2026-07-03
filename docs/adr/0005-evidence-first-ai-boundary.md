# ADR-0005: Evidence-first AI boundary

**Status:** Accepted · **Serves:** Design Bible §15 (AI philosophy), §17 (evidence philosophy)

## Context

The credibility of every generated report rests on one property: AI output is synthesis of
retrieved evidence, never a source of truth. That property must be enforced by structure,
not by prompt wording.

## Decision

Three structural rules:

1. **AI exists only in `agentruntime/`.** The import linter forbids AI imports at or below
   the research engine. Documents flow through the deterministic pipeline untouched by
   agents; agents consume knowledge exclusively through the research engine's typed
   interfaces, exposed to them as tools.
2. **Citations are required at the boundary.** An evidence record must reference a chunk
   (which references an immutable document). The investigation engine rejects evidence
   without a chunk reference; the report drafter receives evidence IDs, not free text, and
   its output must carry citation markers that resolve.
3. **Confidence is computed, not generated.** Confidence is a deterministic function of
   evidence properties (independent source count, source quality tier, recency, stance
   agreement) with an inspectable breakdown. The LLM never assigns confidence.

The orchestration framework (Google ADK, Gemini) is an implementation detail confined to
`agentruntime/adapter.py`; ADK types do not cross that module's boundary, and the model
version is stamped on every execution record for replay.

## Consequences

- Hallucinations cannot silently become knowledge: uncited claims have no path into
  evidence, reports, or the graph.
- Swapping ADK for another orchestrator (or Gemini for another model) touches one module.
- Agents are somewhat constrained — they cannot "know" things outside retrieved evidence.
  That constraint is the product.
