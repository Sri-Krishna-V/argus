"""Report drafter: stance-classified evidence → DraftReport. Receives evidence IDs
and excerpts, never free text; every claim must cite a listed [chunk:<uuid>] marker.
Marker verification and confidence are the investigation engine's job (Phase 7)."""

from argus.agentruntime import adapter
from argus.agentruntime.schemas import CollectedEvidence, DraftReport, ExecutionRecord

INSTRUCTION = """You draft a research report STRICTLY from the evidence provided.
Rules:
- Use only the evidence excerpts below. Never use outside knowledge.
- Every claim in the narrative must carry the citation marker of the evidence
  supporting it, copied exactly as listed, e.g. [chunk:9f8e...]. Never invent markers.
- Call out contradictions between evidence explicitly in risks.
- follow_up_questions: what the evidence could not answer."""


def draft(
    question: str, evidence: list[CollectedEvidence]
) -> tuple[DraftReport, ExecutionRecord]:
    if not evidence:
        raise ValueError("cannot draft a report without evidence (ADR-0005)")
    lines = [
        f"[chunk:{e.chunk_id}] stance={e.stance.value}\n{e.excerpt}" for e in evidence
    ]
    message = f"Question: {question}\n\nEvidence:\n\n" + "\n\n".join(lines)
    return adapter.run_structured("draft_report", INSTRUCTION, message, DraftReport)
