"""Agent I/O contracts. Pure pydantic — no ADK here; these are the types that cross
the adapter boundary, so the orchestration framework stays replaceable (Bible §10)."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    """Planner output: plan precedes retrieval, never search-first."""

    companies: list[str] = Field(description="company names central to the question")
    doc_types: list[str] = Field(description="document types to search: news, filing")
    queries: list[str] = Field(description="3-6 retrieval queries covering the question")
    rationale: str = Field(description="one paragraph: why these targets and queries")


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
