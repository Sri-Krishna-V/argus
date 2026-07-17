"""Planner: question → ResearchPlan. Plan precedes retrieval, never search-first
(Bible §10)."""

from argus.agentruntime import adapter
from argus.agentruntime.schemas import ExecutionRecord, ResearchPlan

INSTRUCTION = """You are a research planner for a company-research platform.
Given a research question, produce a retrieval plan:
- investigation_type: one of company_research, industry_analysis, executive_profiling,
  risk_assessment, event_investigation, earnings_analysis, competitive_analysis, general
- objective: one sentence stating what the investigation must determine
- companies: company names central to the question, as canonically written
  (e.g. "NVIDIA CORP", "Apple Inc.")
- doc_types: the subset of ["news", "filing"] worth searching
- queries: 3-6 short keyword retrieval queries; each carries an objective explaining
  what evidence it targets, and MAY set: priority (int, higher runs first; default
  0), timeframe (free-form period, e.g. "2024Q3"; default ""), evidence_target
  (the fact/artifact this query should establish; default ""), source_types
  (subset of ["news", "filing"]; default [])
- rationale: one paragraph on why these targets and queries
Plan only. Do not answer the question."""


def plan(question: str) -> tuple[ResearchPlan, ExecutionRecord]:
    return adapter.run_structured("plan", INSTRUCTION, question, ResearchPlan)
