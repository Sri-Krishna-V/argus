# ADR-0012: V2 deliberate deferrals

**Status:** Accepted · **Serves:** PRD-V2 (all) · **Extends:** ADR-0008

Deferred capabilities are decisions, not omissions (user decision, 2026-07-06). Each PRD-V2
item below ships later, with the trigger that revisits it:

| Deferral | PRD-V2 § | Revisit trigger |
|---|---|---|
| Supermemory integration | 3.8 | See ADR-0011 |
| Investigation **merge** (branch ships in V2) | 1.4 | First real analyst workflow that produces divergent branches worth reconciling |
| Entity resolution beyond companies + people | 3.3 | Claims corpus accumulates product/fund/location subjects that fragment investigations |
| Macro Analyst specialist | 4.2 | A macroeconomic data connector exists (none planned; only news/filings/profiles today) |
| Uncertain-date estimation in timelines | 3.2 | Never as replacement for observed dates (PRD-V2 forbids); revisit only for explicitly-flagged estimates if analysts ask |
| Citation-expansion & claim-based retrieval strategies | 2.2 | A claims corpus exists to retrieve over (post-Phase-4 data accumulation) |
| Execution-cost estimation in planning | 1.1 | Enough recorded ExecutionRecords to calibrate a per-task-type cost model |
