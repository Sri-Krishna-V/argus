# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary (confirmed): technical evaluators, first.** Engineers, architects, and hiring
managers who open `argusops.vercel.app` cold to judge systems-engineering craft. This is the
DESIGN_BIBLE's own success metric (§6): Argus succeeds if an experienced engineer concludes the
architecture is modular, the data model realistic, the AI layer isolated, and evidence
prioritized over generation. They spend minutes, not hours, and judge by what the interface
makes verifiable.

**Modeled users, whose workflows are the content** (PRD §7) — design for the evaluator reading
a credible analyst's tool:

- **Portfolio managers** — rapid access to supporting evidence, high-level summaries,
  confidence assessments, traceable citations.
- **Research analysts** — deep document search, historical context, investigation workspaces,
  timeline reconstruction, entity relationships, research persistence.
- **Sector specialists** — continuous updates, knowledge evolution, cross-company
  relationships, event tracking.
- **Risk teams** — contradictory evidence, source reliability, confidence evolution,
  historical investigations.

## Product Purpose

Argus continuously ingests public financial sources (SEC EDGAR filings, news RSS) into immutable
documents, derives chunks, embeddings, canonical entities, and a provenance-carrying knowledge
graph, and produces **investigations**: persistent, reproducible, cited, confidence-scored
research artifacts — never chat sessions.

Success is not prediction accuracy. Success is that an experienced engineer recognizes
production infrastructure, and that the research workflow resembles institutional practice.

Explicit non-goals (PRD §6): no trade execution, no investment recommendations, no price
prediction, no portfolio optimization, no replacement of analysts, no competition with
Bloomberg/FactSet/Capital IQ, no unsupported conclusions.

## Positioning

**The knowledge platform is the permanent asset; the AI runtime is replaceable** — and it is
enforced, not asserted:

- AI code exists only in `agentruntime/`; one module (`adapter.py`) is the sole importer of the
  model SDK. Import direction is enforced by `import-linter`, not convention.
- Every AI output carries citations that resolve to a chunk of a real ingested document.
  Evidence without a chunk reference is rejected before it reaches a report.
- Confidence is **computed** — source diversity, recency, stance agreement — never
  LLM-generated.
- Documents are immutable (DB trigger) and events are append-only (DB trigger); derived
  artifacts are re-derivable from the raw store.

A neighboring RAG demo can copy the feature list. It cannot truthfully claim an AI boundary a
compliance team could audit.

## Operating Context

- **Surfaces today:** three app routes — Investigations (list + create), Search, Pipeline — plus
  an investigation detail view carrying the task DAG, activity timeline, hypotheses, report
  narrative, citations, and confidence meter. No landing page and no first-run onboarding exist.
- **Deployment:** Vercel frontend (`argusops.vercel.app`) over a VPS backend. Anonymous visitors
  are read-only: `ARGUS_DEMO_MODE=1` exempts only GET/HEAD/OPTIONS on `/api/*` from the API key;
  every write still requires one (ADR-0014). The app shell shows a demo banner and locks writes
  while `/health` is unresolved.
- **What is real in the demo vs. what is not** (ADR-0014): real — the corpus (SEC EDGAR + RSS
  connectors), the 7-stage pipeline, hybrid retrieval, near-duplicate dedup, source ranking, the
  task DAG, the citation gate, and every confidence score. Not real — the language model.
  `ARGUS_LLM_PROVIDER=demo` swaps in a deterministic canned runtime at the adapter boundary, so
  plans, stances, and report prose are scripted; reports say so and carry `model=canned-demo`.
- **Investigation lifecycle:** pending → running → completed/failed, cancelable in flight;
  tasks execute as a DAG whose readiness is derived on read from dependency states; work moves
  through a retrying job outbox with a dead-letter path.
- **Corpus as seeded** (2026-08-19): 86 documents, 1,343 chunks, 1,157 entity mentions.

## Capabilities and Constraints

- **Capabilities:** ingest and reprocess sources; hybrid search (Postgres FTS + pgvector, fused
  by RRF); create, run, cancel, and refresh investigations when new evidence lands; read
  versioned reports with resolved citations and computed confidence; inspect pipeline health,
  pipeline runs, and dead-lettered jobs; read a per-investigation event timeline.
- **Terminology** (`docs/DOMAIN_MODEL.md`): document, chunk, entity, mention, edge,
  investigation, task, hypothesis, evidence, stance, report, citation, confidence, pipeline run,
  event, job. Use these words on screen; they are the product's vocabulary, not internals.
- **The web SPA is a pure API consumer** (ADR-0013): anything on screen must exist as a JSON
  endpoint. New visual ideas that need new data need an endpoint first.
- **Single dark theme, no light mode** (ADR-0013) — a design commitment, not a technical limit.
- **Never advisory** (PRD §6): copy describes evidence and uncertainty. Nothing is phrased as a
  recommendation, a prediction, or advice.
- **Undecided:** the landing page and the guided first-run experience are in scope but
  unspecified. Live LLM paths are unverified — no OpenRouter key is configured, so canned output
  is the only output anyone has seen.

## Brand Commitments

- **Name:** Argus. Subtitle in the shell: "Research OS". Mark: a star glyph.
- **Dark-only "Radiant" identity is binding** (ADR-0013, confirmed): ember/steel palette, a
  dense-vertical-stroke signal-ridge motif, Geist + Geist Mono, uppercase mono micro-labels on
  wide tracking. Future work preserves this world rather than replacing it.
- **Citations and computed confidence stay visible** (confirmed): any surface that presents a
  claim shows where it came from and that its confidence was computed. Never abstracted away for
  a cleaner layout.
- **Voice:** plain about limits, confident about engineering. The README's "what is real / what
  is not" register is the model — state the canned-LLM boundary rather than softening it.

## Evidence on Hand

Real and usable:

- Live corpus of real SEC filings and news, and the deployed demo at `argusops.vercel.app`.
- `docs/ARCHITECTURE.md` (system as built), `docs/DESIGN_BIBLE.md`, `docs/PRD.md` +
  `docs/PRD-V2.md`, `docs/DOMAIN_MODEL.md`, `docs/RISKS.md`, 14 ADRs in `docs/adr/`.
- `evals/golden.json` — scored retrieval and investigation quality.
- A pytest suite gating CI, plus `import-linter` layer enforcement.
- `web/src/assets/hero.png`.

Absences that future work must not fabricate: no customers, users, testimonials, logos, press,
pricing, funding, team bios, uptime/SLA numbers, or benchmarks against commercial platforms. No
real language-model output exists in the demo. Repository counts drift between README's "By the
numbers" table and `CLAUDE.md` — verify any figure before putting it on a surface, never copy.

## Product Principles

1. **Knowledge first** — the knowledge platform is the permanent asset; the AI runtime is a
   replaceable component.
2. **Evidence first** — generated text is never a source of truth. A claim without a resolvable
   citation does not ship.
3. **Human first** — the analyst decides. Argus surfaces evidence, including contradictory
   evidence, and never advises.
4. **Evolution first** — knowledge changes continuously; an investigation that has gone stale
   says so.
5. **Legibility is the proof** — the evaluator's verdict comes from what the interface makes
   visible: provenance, the task DAG, computed confidence, and honest limits.

## Accessibility & Inclusion

No product-specific standard has been established. One constraint follows from the dark-only
commitment: there is no light-mode fallback to lean on, so text and state colors must hold their
contrast on the dark ground, and status must never be carried by hue alone — status dots,
confidence meters, and stance markers need a second channel (shape, label, or position).
