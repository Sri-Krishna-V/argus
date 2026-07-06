"""Agent I/O contracts. Pure pydantic — no ADK here; these are the types that cross
the adapter boundary, so the orchestration framework stays replaceable (Bible §10)."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class PlannedQuery(BaseModel):
    """One retrieval query with the reason it exists (PRD-V2 2.1: queries are
    explainable). Priority/timeframe arrive with Retrieval Intelligence (Phase 3)."""

    query: str = Field(min_length=1, description="short keyword retrieval query")
    objective: str = Field(default="", description="what evidence this query targets")


class ResearchPlan(BaseModel):
    """Planner output: plan precedes retrieval, never search-first."""

    investigation_type: str = Field(
        default="general",
        description="one of: company_research, industry_analysis, executive_profiling, "
        "risk_assessment, event_investigation, earnings_analysis, competitive_analysis, "
        "general",
    )
    objective: str = Field(default="", description="one sentence: the investigation goal")
    companies: list[str] = Field(description="company names central to the question")
    doc_types: list[str] = Field(description="document types to search: news, filing")
    queries: list[PlannedQuery] = Field(description="3-6 retrieval queries covering the question")
    rationale: str = Field(description="one paragraph: why these targets and queries")

    @field_validator("queries", mode="before")
    @classmethod
    def _upgrade_v1_queries(cls, v):
        # V1 stored plans (and the V1 fake adapter) carry plain strings
        if isinstance(v, list):
            return [{"query": q} if isinstance(q, str) else q for q in v]
        return v


class Stance(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    UNKNOWN = "unknown"


class StanceResult(BaseModel):
    stance: Stance
    rationale: str = Field(description="one sentence: why this evidence takes this stance")


class DraftReport(BaseModel):
    """Synthesis from collected evidence only. Citation markers are [chunk:<uuid>];
    the investigation engine verifies every marker resolves."""

    executive_summary: str
    key_findings: list[str]
    risks: list[str]
    follow_up_questions: list[str]
    narrative: str = Field(description="findings prose with [chunk:<uuid>] citation markers")


class ExecutionRecord(BaseModel):
    """One agent call, persisted for replay (Bible §13: execution history)."""

    operation: str
    model: str
    prompt: str
    response_text: str
    started_at: datetime
    duration_ms: int


class CollectedEvidence(BaseModel):
    """Evidence at the AI boundary: the chunk reference is mandatory (ADR-0005)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    excerpt: str
    stance: Stance
    rationale: str
    query: str
    scores: dict
    strategy: str
