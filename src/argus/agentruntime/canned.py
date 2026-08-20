"""Deterministic stand-in for the LLM (ADR-0014): the same signature and return type
as adapter.run_structured, with no network, no cost and no nondeterminism. Selected
with ARGUS_LLM_PROVIDER=demo so a public read-only demo can execute the real
investigation machinery — plan → DAG → retrieval → dedup → stance → fusion →
citation gate → computed confidence — without an API key.

Only the prose is canned. Citation markers are parsed back out of the prompt and
never invented, so the citation gate passes against real evidence, and every
ExecutionRecord is stamped model=MODEL so canned text can never be mistaken for
model analysis.

ponytail: keyword tables and hash buckets, not a local model — the point is to
exercise the pipeline deterministically, not to imitate reasoning.
"""

import hashlib
import re
import time
from datetime import UTC, datetime

from pydantic import BaseModel

from argus.agentruntime.schemas import DraftReport, ExecutionRecord, Stance

MODEL = "canned-demo"
DISCLOSURE = (
    "Assembled deterministically from the cited passages in demo mode — "
    "no language model was called."
)
SNIPPET_CHARS = 220

# question token → watchlist ticker. Tickers, not names: evidence.resolve_companies
# matches tickers exactly, while an ilike on "%Apple%" can land on the wrong issuer.
_TICKERS = {
    "apple": "AAPL", "aapl": "AAPL", "iphone": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT", "azure": "MSFT",
    "nvidia": "NVDA", "nvda": "NVDA",
    "alphabet": "GOOGL", "google": "GOOGL", "googl": "GOOGL",
    "amazon": "AMZN", "amzn": "AMZN", "aws": "AMZN",
    "meta": "META", "facebook": "META", "instagram": "META",
    "taiwan semiconductor": "TSM", "tsmc": "TSM", "tsm": "TSM",
    "broadcom": "AVGO", "avgo": "AVGO",
}

# trigger tokens → (investigation_type, retrieval query for that theme)
_THEMES = [
    (("risk", "exposure", "supply chain", "concentration", "disruption"),
     "risk_assessment", "risk factors and mitigation disclosure"),
    (("revenue", "growth", "earnings", "quarter", "results", "margin", "guidance"),
     "earnings_analysis", "revenue growth and margin commentary"),
    (("regulat", "antitrust", "export control", "litigation", "compliance", "tariff"),
     "risk_assessment", "regulatory and legal proceedings"),
    (("competit", "market share", "rival", "peer"),
     "competitive_analysis", "competitive positioning and market share"),
    (("data center", "cloud", "chip", "semiconductor", "capital expenditure", "capex"),
     "company_research", "infrastructure and capital investment commentary"),
]

# padding for questions that match no theme, so every plan reaches 3 queries
_FALLBACKS = [
    ("management discussion and analysis outlook", "management's forward-looking commentary"),
    ("risk factors and mitigation disclosure", "the risks disclosed around this question"),
    ("recent results and guidance", "the most recently reported figures"),
]

_STOPWORDS = frozenset({
    "a", "an", "and", "any", "about", "are", "as", "at", "be", "been", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "if", "in", "is", "it",
    "its", "last", "many", "most", "of", "on", "or", "recent", "should", "that", "the",
    "their", "these", "this", "those", "to", "was", "were", "what", "when", "where", "which",
    "who", "whom", "whose", "why", "will", "with", "would",
})


def _mentions(haystack: str, token: str, *, prefix: bool = False) -> bool:
    """Whole-word match: "meta" must not fire on "metadata" — that would plan a
    Meta-only retrieval filter for a question about metadata. `prefix=True` for theme
    stems, where "regulat" is meant to catch "regulatory" and "regulation"."""
    if " " in token:
        return token in haystack
    tail = "" if prefix else r"\b"
    return re.search(rf"\b{re.escape(token)}{tail}", haystack) is not None


def _keywords(question: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z][\w'-]+", question) if w.lower() not in _STOPWORDS]
    return " ".join(words[:8])


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Whitespace-collapsed prefix cut on a word boundary. Deliberately not
    sentence-splitting: filing text is full of "Item 1A." style false stops."""
    flat = " ".join(text.split()).lstrip("—-•·*| ")
    if len(flat) <= limit:
        return flat
    # rfind returns -1 on an unbroken run (a URL, a table row, an XBRL blob), and
    # flat[:-1] would hand back the whole excerpt
    cut = flat.rfind(" ", 0, limit)
    return flat[: cut if cut > 0 else limit] + "…"


def _proper_nouns(question: str) -> list[str]:
    """Company names to try when the question names no watchlist issuer: a planner
    echoes the names it reads and lets evidence.resolve_companies do the canonical
    lookup. Keeps arbitrary questions working instead of silently corpus-wide."""
    words = re.findall(r"\b[A-Z][a-zA-Z&.'-]{2,}\b", question)
    return list(dict.fromkeys(w for w in words if w.lower() not in _STOPWORDS))[:2]


# cover-page and form furniture a model would never headline as a finding
_FORM_GLYPHS = "☐☒☑✓"


def _prose_score(snippet: str) -> float:
    """How quotable a passage is. Filing text is part prose, part cover-page table
    ("— Nasdaq Stock Market LLC 3.450% Senior Notes due 2032 —") and part form
    furniture ("Emerging growth company ☐", "REPORT OF MANAGEMENT ON INTERNAL
    CONTROL"), and a model drafting a report would headline the sentence over either.
    Letters-per-character separates prose from tables; a checkbox glyph or a mostly
    upper-case run marks the furniture.

    ponytail: a selection heuristic, not a rewrite — it only reorders passages that
    were genuinely retrieved and cited. Better headline passages are really a
    retrieval-ranking problem, which the demo shows honestly."""
    if not snippet:
        return 0.0
    score = sum(c.isalpha() or c.isspace() for c in snippet) / len(snippet)
    letters = [c for c in snippet if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.5:
        score *= 0.3
    if any(g in snippet for g in _FORM_GLYPHS):
        score *= 0.2
    return score


def _plan[T: BaseModel](question: str, schema: type[T]) -> T:
    low = question.lower()
    companies = list(
        dict.fromkeys(t for key, t in _TICKERS.items() if _mentions(low, key))
    ) or _proper_nouns(question)
    themes = [
        (kind, query)
        for tokens, kind, query in _THEMES
        if any(_mentions(low, t, prefix=True) for t in tokens)
    ]
    keywords = _keywords(question) or question[:120]

    queries = [{
        "query": keywords,
        "objective": "the question's own terms, as a direct retrieval query",
        "priority": 3,
        "evidence_target": "passages that answer the question directly",
        "source_types": ["filing", "news"],
    }]
    for i, (_kind, theme_query) in enumerate(themes[:3]):
        queries.append({
            "query": theme_query,
            "objective": f"evidence on {theme_query}",
            "priority": 2 - i,
            "evidence_target": theme_query,
        })
    for fallback, objective in _FALLBACKS:
        if len({q["query"] for q in queries}) >= 3:  # ResearchPlan documents 3-6
            break
        queries.append({
            "query": fallback, "objective": objective,
            "priority": 0, "evidence_target": objective,
        })
    # compile_dag makes one task per query and each task owns its query's evidence
    # rows — duplicate query strings would give two tasks the same rows to rebuild
    unique = list({q["query"]: q for q in queries}.values())

    return schema(
        investigation_type=themes[0][0] if themes else "company_research",
        objective=f"Establish what the corpus supports about: {question.strip()}",
        companies=companies,
        doc_types=["filing", "news"],
        queries=unique[:5],
        rationale=(
            "Queries cover the question's own terms plus the themes it implies "
            f"({', '.join(q['query'] for q in unique[1:]) or 'none'}). Both filings and "
            "news are searched so source diversity and corroboration are possible."
        ),
    )


_STANCE_RATIONALE = {
    Stance.SUPPORTING: "Passage carries disclosure consistent with the question's premise.",
    Stance.CONTRADICTING: "Passage cuts against the question's premise.",
    Stance.UNKNOWN: "Passage is topically adjacent but does not settle the question.",
}


def _stance_for(excerpt: str) -> Stance:
    """Stable per excerpt text, so a replay of the same corpus classifies identically.
    Buckets are weighted to leave every stance represented in a normal evidence set:
    60% supporting, 20% unknown, 20% contradicting."""
    bucket = int(hashlib.sha256(excerpt.encode()).hexdigest()[:8], 16) % 10
    if bucket < 6:
        return Stance.SUPPORTING
    if bucket < 8:
        return Stance.UNKNOWN
    return Stance.CONTRADICTING


def _split_numbered(message: str) -> list[str]:
    """Excerpts out of evidence.collect_query's prompt, where they are joined by a
    blank line: "[1] …\n\n[2] …". A marker counts only when it continues the sequence
    AND opens a block, because filing text is full of line-leading bracketed footnote
    numbers and an over-count fails the whole stance batch.

    ponytail: still a heuristic — excerpt text containing exactly
    "\n\n[<next index>] " is indistinguishable from a real marker. The cost is one
    failed collect task on a demo, never a wrong answer."""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"(?m)^\[(\d+)\] ", message):
        if int(m.group(1)) != len(spans) + 1:
            continue
        # the first excerpt follows the "---" fence, every later one a blank line
        if spans and message[max(0, m.start() - 2) : m.start()] != "\n\n":
            continue
        if spans:
            spans[-1] = (spans[-1][0], m.start())
        spans.append((m.end(), len(message)))
    return [_trim_fence(message[start:end]) for start, end in spans]


def _trim_fence(text: str) -> str:
    return text.strip().rstrip("-").strip()


def _stances[T: BaseModel](message: str, schema: type[T]) -> T:
    excerpts = _split_numbered(message)
    return schema(
        results=[
            {"stance": (s := _stance_for(e)), "rationale": _STANCE_RATIONALE[s]}
            for e in excerpts
        ]
    )


def _cited(message: str) -> list[tuple[str, str, str]]:
    """(chunk_id, stance, excerpt) out of drafter.draft's prompt."""
    markers = list(re.finditer(r"\[chunk:([0-9a-f-]{36})\] stance=(\w+)\n", message))
    out = []
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(message)
        out.append((m.group(1), m.group(2), _trim_fence(message[m.end() : end])))
    return out


def _draft(question: str, message: str, schema: type[DraftReport]) -> DraftReport:
    cited = _cited(message)
    by_stance: dict[str, list[tuple[str, str]]] = {}
    for chunk_id, stance, excerpt in cited:
        by_stance.setdefault(stance, []).append((chunk_id, _snippet(excerpt)))
    # quote the most prose-like passages first; ties keep evidence order, so the
    # report stays reproducible for a given evidence set
    for bucket in by_stance.values():
        bucket.sort(key=lambda item: -_prose_score(item[1]))
    supporting = by_stance.get("supporting", [])
    contradicting = by_stance.get("contradicting", [])
    unknown = by_stance.get("unknown", [])

    def sentence(item: tuple[str, str]) -> str:
        chunk_id, snippet = item
        return f"{snippet.rstrip('.…')} [chunk:{chunk_id}]."

    lead = (
        f"Collected evidence for “{question.strip()}” spans {len(cited)} passages: "
        f"{len(supporting)} supporting, {len(contradicting)} contradicting, "
        f"{len(unknown)} neutral."
    )
    body = [sentence(i) for i in (supporting + contradicting + unknown)[:5]]
    return schema(
        executive_summary=f"{lead} {DISCLOSURE}",
        key_findings=[sentence(i) for i in supporting[:4]]
        or ["No supporting evidence was retrieved for this question."],
        risks=[sentence(i) for i in contradicting[:3]]
        or ["No contradicting evidence surfaced in the current corpus."],
        follow_up_questions=[
            f"What do the most recent filings add on {_keywords(question) or 'this question'}?",
            "Which independent sources corroborate the highest-ranked passages?",
            "Do the contradicting passages cover a different period or segment?",
        ],
        narrative=" ".join([lead, *body, DISCLOSURE]),
    )


def run_structured[T: BaseModel](
    operation: str, instruction: str, message: str, schema: type[T]
) -> tuple[T, ExecutionRecord]:
    """adapter.run_structured's contract, served from canned data. `operation` is the
    dispatch key (the three call sites in planner/evidence/drafter), and the response
    is built with the caller's own `schema` so StanceBatch never has to be imported
    from evidence.py — which imports adapter, and would close an import cycle."""
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    if operation == "plan":
        response = _plan(message, schema)
    elif operation == "classify_stance":
        response = _stances(message, schema)
    elif operation == "draft_report":
        question = message.partition("\n")[0].removeprefix("Question: ")
        response = _draft(question, message, schema)
    else:
        raise ValueError(f"canned runtime has no response for operation {operation!r}")

    return response, ExecutionRecord(
        operation=operation,
        model=MODEL,
        prompt=f"{instruction}\n\n{message}",
        response_text=response.model_dump_json(),
        started_at=started_at,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
