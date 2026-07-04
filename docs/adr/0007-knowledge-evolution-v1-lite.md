# ADR-0007: Knowledge evolution V1-lite — staleness on read, manual refresh

**Status:** Accepted · **Serves:** PRD §11, Design Bible §14

## Context

PRD §11 requires investigations to react to new knowledge. Full automatic
re-evaluation (agent re-runs on every relevant document) multiplies LLM cost by
corpus velocity and can silently rewrite conclusions a user has already read.

## Decision

V1 ships staleness *detection* plus user-triggered refresh:

- "New evidence available" is **computed on read** (`engine.has_new_evidence`): an
  enriched document linked to the investigation's companies with
  `ingested_at > last_refreshed_at`. No event consumer, no flag column — the signal
  is derived from state that already exists and cannot drift out of sync.
- Refresh is explicit (`POST /api/investigations/{id}/refresh`): re-runs evidence
  collection with the stored plan, appends a new versioned report, recomputes
  confidence. The prior report version is preserved.

## Consequences

- The staleness query runs per workspace render; fine at V1 scale. If it ever
  shows up in profiles, promote to an event-consumer-maintained flag column —
  the read-side contract doesn't change.
- Fully automatic re-evaluation remains deferred, deliberately: conclusions only
  change when a user asks them to.
