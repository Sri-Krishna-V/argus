"""Planner: question → ResearchPlan. Plan precedes retrieval, never search-first
(Bible §10)."""

from argus.agentruntime import adapter
from argus.agentruntime.schemas import ExecutionRecord, ResearchPlan

INSTRUCTION = """You are a research planner for a company-research platform.
Given a research question, produce a retrieval plan:
- companies: company names central to the question, as canonically written
  (e.g. "NVIDIA CORP", "Apple Inc.")
- doc_types: the subset of ["news", "filing"] worth searching
- queries: 3-6 short keyword retrieval queries that together cover the question
- rationale: one paragraph on why these targets and queries
Plan only. Do not answer the question."""


def plan(question: str) -> tuple[ResearchPlan, ExecutionRecord]:
    return adapter.run_structured("plan", INSTRUCTION, question, ResearchPlan)
