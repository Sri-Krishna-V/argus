# Dashboard SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Jinja2 + htmx dashboard with an enterprise-grade React SPA served as a static build from the existing FastAPI app — one container in production, no Node at runtime.

**Architecture:** `web/` is a standalone Vite + React + TypeScript project consuming the existing JSON API (`/api/*`) plus three small additive endpoints. `vite build` emits `web/dist`; FastAPI mounts it as static files with an SPA fallback so client-side routes (e.g. `/investigations/abc`) still resolve to `index.html` on a hard refresh. The old `src/argus/ui/` package (Jinja2 templates, htmx views, vendored htmx.js) is deleted once the SPA covers the same four surfaces.

**Tech Stack:** React 19, TypeScript, Vite 7, Tailwind CSS v4, shadcn/ui, TanStack Router (file-based), TanStack Query v5, Recharts, sonner (toasts). Backend additions stay FastAPI + SQLAlchemy, sync `def` (ADR-0004).

## Global Constraints

- No Node in the production image — Node is a build-stage tool only (multi-stage Dockerfile).
- All API endpoints stay sync `def` and respect the existing opt-in `ARGUS_API_KEY` auth (`argus.main` middleware checks `request.url.path.startswith("/api/")`; the SPA shell itself must stay reachable without a key, same as today's `/` and `/health`).
- Pagination bounds on new list endpoints follow the existing convention: `Query(50, ge=1, le=200)` / `Query(0, ge=0)`.
- The XSS guard on citation URLs (only `http(s)` becomes a link) moves from the deleted Jinja view into the API response (`GET /api/investigations/{id}/report`) — verified by pytest, not a frontend test framework.
- No frontend unit-test framework in v1. The frontend gate is `tsc --noEmit` + `vite build`. The API contract is covered by pytest.
- Layer contract (`pyproject.toml` `[tool.importlinter]`): `argus.ui` is removed from the layers list once the package is deleted; no other layer changes.

---

## Revision 2 — 2026-07-12: Radiant visual direction + V2 task DAG

**Status at revision time:** Tasks 1–3 merged to main; Tasks 4–8 committed on
`worktree-frontend-revamp` (c8d5f74…98e701e). `main` (V2 Phase 1 task DAG) merged into the
branch 2026-07-12, which adds `GET /api/investigations/{id}/tasks`.

**Plan changes:**

1. **ADR renumber** — Task 14 writes **ADR-0013** (0010–0012 were taken by V2 Phase 0).
2. **Dark-only UI** — the visual identity commits to dark. Task 8b deletes `lib/theme.ts`
   and the header toggle; `<html class="dark">` is hard-coded in `index.html`.
3. **New Task 8b (Radiant visual system) and Task 8c (task DAG panel)**, specified below.
   Tasks 9–11 must build on 8b's tokens and components — the code samples in their original
   specs are behavioral references, not styling references.

### Visual direction — "Radiant"

The reference is a near-black field crossed by two ridges of dense 1px vertical strokes —
cool steel-blue light with one warm ember hotspot — and a minimal white geometric wordmark.
For Argus this texture is literal, not decorative: dense vertical strokes = document chunks,
the ridge rising out of them = signal extracted from noise, the ember crest = confidence.

**Palette (exact values, wired into the existing shadcn CSS variables in `index.css`):**

| token | value | role |
|---|---|---|
| `--background` | `#06080D` | void — page background, blue-cast near-black |
| `--card` / `--popover` | `#0C1017` | raised surface; panels additionally get `bg-white/[0.03]` glass tint |
| `--border` / `--input` | `rgba(148,163,184,0.14)` | hairline steel |
| `--foreground` | `#EEF2F8` | primary text |
| `--muted-foreground` | `#8DA0BA` | steel — secondary text, cool ridge color |
| `--primary` | `#E8A57F` | ember — the only warm thing on screen; active states, confidence, links |
| ember glow (chart/canvas only) | `#F4C29A` | ridge crest hotspot |
| `--destructive` | `#C97B6E` | muted clay |

Ember is spent sparingly: nav active state, confidence, primary buttons, citation markers,
the ridge hotspot. Everything else is steel-on-void.

**Type:** Geist Variable (installed) stays the body face. Add `@fontsource-variable/geist-mono`
as the utility face: ALL eyebrows, nav items, status labels, table headers, and data values are
mono, uppercase, `text-[11px]`, `tracking-[0.14em]`, steel. Display headings are Geist at
weight 300, large, `tracking-tight` — the Radiant wordmark look. No third face.

**Signature element:** `SignalRidge` — one canvas component drawing dense vertical 1px strokes
whose heights follow layered sine ridges; strokes colored by a steel gradient with an ember
hotspot around the crest. Slow horizontal drift (respects `prefers-reduced-motion`: renders one
static frame). Two uses only: (a) full-bleed hero band behind the investigations list header,
(b) `amplitude` prop driven by confidence as a thin band on the detail page (replacing the
plain progress bar inside `ConfidenceMeter`). Nothing else animates.

**Chrome:** sidebar keeps its structure but goes void-black with hairline right border; ARGUS
wordmark in white Geist 300 with a small 4-point-star SVG glyph (the image's asterisk mark) in
ember; nav items mono-uppercase steel, active = white text + ember star bullet. Status chips
become mono text with a small colored dot (ember = running/pending, steel = complete, clay =
failed/dead) instead of filled badges. Cards are glass: `bg-white/[0.03]`, hairline border,
`rounded-lg`, no shadows.

### Task 8b: Radiant visual system

**Files:**
- Modify: `web/src/index.css` (tokens above), `web/index.html` (`class="dark"` on `<html>`)
- Modify: `web/src/components/app-shell.tsx` (chrome above; delete toggle)
- Create: `web/src/components/signal-ridge.tsx` (canvas; `height`, `amplitude?`, `className?` props)
- Create: `web/src/components/status-dot.tsx` (status → dot + mono label mapping, reused everywhere)
- Modify: `web/src/routes/index.tsx`, `web/src/routes/investigations.$investigationId.tsx`,
  `web/src/components/{confidence-meter,new-investigation-dialog,report-narrative}.tsx` — restyle to tokens
- Delete: `web/src/lib/theme.ts`
- Add dep: `@fontsource-variable/geist-mono`

Verify: `npx tsc --noEmit && npm run build`; dev-server visual check.

### Task 8c: Task DAG panel (V2)

**Files:**
- Create: `web/src/components/task-dag.tsx`
- Modify: `web/src/routes/investigations.$investigationId.tsx`, `web/src/lib/types.ts`

Consumes `GET /api/investigations/{id}/tasks` →
`{tasks: [{id, task_type, objective, specialist, depends_on: string[], status, outputs, error, created_at}]}`.
Render as a topologically-layered column flow (no graph lib — group tasks by dependency depth,
one column per depth, hairline connectors between dependent cards). Each card: mono task_type
eyebrow, objective text, specialist, `StatusDot`. Poll with `refetchInterval: 5_000` while any
task is pending/running. Hide the panel entirely when `tasks` is empty (V1 investigations).
Failed tasks show `error` in clay. A 404 from the endpoint must not break the page.

---

### Task 1: Report endpoint returns numbered, guarded citations

**Files:**
- Modify: `src/argus/api/routes.py`
- Test: `tests/test_api_features.py`

**Interfaces:**
- Consumes: `argus.investigations.engine.MARKER_RE` (existing), `argus.research.citations.resolve(session, chunk_ids) -> list[Citation]` (existing; `Citation` has `chunk_id, document_id, title, url, source, published_at, excerpt`).
- Produces: `GET /api/investigations/{id}/report` response gains a `"citations"` key: `list[{"index": int, "chunk_id": UUID, "document_id": UUID, "title": str|None, "url": str|None, "source": str, "published_at": datetime|None, "excerpt": str}]`, ordered by first appearance in the narrative, 1-indexed. `url` is `None` unless it starts with `http://` or `https://`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_features.py`, right after the existing `_investigation_citing` helper (which already builds a minimal investigation + report citing one chunk — reused as-is):

```python
def test_report_citation_javascript_url_is_nulled(client):
    inv_id = _investigation_citing("javascript:alert(1)")
    r = client.get(f"/api/investigations/{inv_id}/report")
    assert r.status_code == 200
    citations = r.json()["citations"]
    assert citations[0]["url"] is None
    assert citations[0]["index"] == 1


def test_report_citation_http_url_is_kept(client):
    inv_id = _investigation_citing("https://example.com/good-source")
    r = client.get(f"/api/investigations/{inv_id}/report")
    assert r.status_code == 200
    citations = r.json()["citations"]
    assert citations[0]["url"] == "https://example.com/good-source"


def test_report_with_no_citations_returns_empty_list(client, monkeypatch):
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    created = client.post(
        "/api/investigations", json={"question": "no-op question with no matches xyz"}
    ).json()
    r = client.get(f"/api/investigations/{created['id']}/report")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json()["citations"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_features.py -k citation -v`
Expected: FAIL — `KeyError: 'citations'`

- [ ] **Step 3: Add the citations helper and wire it into `get_report`**

In `src/argus/api/routes.py`, add to the imports:

```python
from argus.investigations.models import (
    Evidence,
    Investigation,
    InvestigationLink,
    Report,
)
```

becomes:

```python
from argus.investigations.models import (
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationLink,
    Report,
)
from argus.research.citations import resolve
```

Add a helper function right before the `get_report` route (after the `# --- investigations ---` section's other helpers):

```python
def _report_citations(session: Session, narrative: str) -> list[dict]:
    """Numbered, first-appearance-order citations for [chunk:<uuid>] markers.
    Only http(s) URLs are kept — a stored javascript: URI must never become a link."""
    order: list[uuid.UUID] = []
    for m in engine.MARKER_RE.finditer(narrative):
        cid = uuid.UUID(m.group(1))
        if cid not in order:
            order.append(cid)
    if not order:
        return []
    by_id = {c.chunk_id: c for c in resolve(session, order)}
    return [
        {
            "index": i,
            "chunk_id": by_id[cid].chunk_id,
            "document_id": by_id[cid].document_id,
            "title": by_id[cid].title,
            "url": by_id[cid].url
            if by_id[cid].url and by_id[cid].url.startswith(("http://", "https://"))
            else None,
            "source": by_id[cid].source,
            "published_at": by_id[cid].published_at,
            "excerpt": by_id[cid].excerpt,
        }
        for i, cid in enumerate(order, 1)
    ]
```

Replace the `get_report` body's return statement:

```python
    return {
        c: getattr(report, c)
        for c in (
            "id", "version", "executive_summary", "key_findings", "risks",
            "follow_up_questions", "narrative", "model", "created_at",
        )
    }
```

with:

```python
    return {
        c: getattr(report, c)
        for c in (
            "id", "version", "executive_summary", "key_findings", "risks",
            "follow_up_questions", "narrative", "model", "created_at",
        )
    } | {"citations": _report_citations(session, report.narrative)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_features.py -k citation -v`
Expected: PASS (all 3)

- [ ] **Step 5: Run the full test file to check for regressions**

Run: `uv run pytest tests/test_api_features.py -v`
Expected: all pass (old Jinja-view citation tests at the bottom of the file still pass unchanged — they're deleted later in Task 12 alongside the `ui` package)

- [ ] **Step 6: Commit**

```bash
git add src/argus/api/routes.py tests/test_api_features.py
git commit -m "api: report endpoint returns numbered, URL-guarded citations"
```

---

### Task 2: Investigation detail includes hypotheses and links

**Files:**
- Modify: `src/argus/api/routes.py`
- Test: `tests/test_api_features.py`

**Interfaces:**
- Consumes: `argus.investigations.models.Hypothesis`, `InvestigationLink` (existing), `argus.investigations.engine.create` (existing).
- Produces: `GET /api/investigations/{id}` response gains `"hypotheses": list[{"id": UUID, "statement": str, "created_at": datetime}]` and `"links": list[{"link_type": str, "investigation_id": UUID, "question": str}]`. `GET /api/investigations` (list) is unchanged — no per-row extra queries.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_features.py`:

```python
def test_investigation_detail_includes_hypotheses_and_links(client):
    from argus.investigations import engine

    with session_scope() as session:
        inv = engine.create(session, "does X affect Y?", "yes, because Z")
        other = Investigation(question="a related question")
        session.add(other)
        session.flush()
        session.add(InvestigationLink(
            src_investigation_id=inv.id, dst_investigation_id=other.id,
            link_type="relates_to",
        ))
        inv_id = inv.id

    r = client.get(f"/api/investigations/{inv_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["hypotheses"][0]["statement"] == "yes, because Z"
    assert body["links"][0]["link_type"] == "relates_to"
    assert body["links"][0]["question"] == "a related question"


def test_investigation_detail_with_no_hypotheses_or_links_returns_empty_lists(client):
    with session_scope() as session:
        inv = Investigation(question="standalone question")
        session.add(inv)
        session.flush()
        inv_id = inv.id

    body = client.get(f"/api/investigations/{inv_id}").json()
    assert body["hypotheses"] == []
    assert body["links"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_features.py -k "hypotheses_and_links or empty_lists" -v`
Expected: FAIL — `KeyError: 'hypotheses'`

- [ ] **Step 3: Extend `get_investigation`**

Replace:

```python
@router.get("/api/investigations/{investigation_id}")
def get_investigation(
    investigation_id: uuid.UUID, session: Session = Depends(get_db)
) -> dict:
    return _investigation_json(session, _get_or_404(session, investigation_id))
```

with:

```python
@router.get("/api/investigations/{investigation_id}")
def get_investigation(
    investigation_id: uuid.UUID, session: Session = Depends(get_db)
) -> dict:
    inv = _get_or_404(session, investigation_id)
    hypotheses = session.scalars(
        select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)
    ).all()
    links = session.execute(
        select(InvestigationLink, Investigation)
        .join(Investigation, Investigation.id == InvestigationLink.dst_investigation_id)
        .where(InvestigationLink.src_investigation_id == investigation_id)
    ).all()
    return _investigation_json(session, inv) | {
        "hypotheses": [
            {"id": h.id, "statement": h.statement, "created_at": h.created_at}
            for h in hypotheses
        ],
        "links": [
            {"link_type": link.link_type, "investigation_id": dst.id, "question": dst.question}
            for link, dst in links
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_features.py -k "hypotheses_and_links or empty_lists" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/argus/api/routes.py tests/test_api_features.py
git commit -m "api: investigation detail includes hypotheses and links"
```

---

### Task 3: Dead-letter job list, retry endpoint, document count in pipeline metrics

**Files:**
- Modify: `src/argus/api/routes.py`
- Test: `tests/test_api_features.py`

**Interfaces:**
- Produces:
  - `GET /api/jobs?status=<status>&limit=&offset=` → `list[{"id": int, "job_type": str, "document_id": UUID|None, "attempts": int, "max_attempts": int, "last_error": str|None, "created_at": datetime}]`
  - `POST /api/jobs/{job_id}/retry` → `{"retried": true}` on success; 404 if the job doesn't exist or isn't `dead`.
  - `GET /api/metrics/pipeline` gains `"document_count": int`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_features.py`. First add `Job` to the top-level imports (currently only imported inside route handlers in other files, not this test file):

```python
from argus.core.models import Job
```

Then add the tests (near the pagination section, after `test_evidence_limit_and_offset`):

```python
def _dead_job(**overrides) -> int:
    with session_scope() as session:
        job = Job(job_type="parse", status="dead", attempts=3, last_error="boom", **overrides)
        session.add(job)
        session.flush()
        return job.id


def test_list_jobs_filters_by_status(client):
    dead_id = _dead_job()
    jobs = client.get("/api/jobs", params={"status": "dead"}).json()
    assert any(j["id"] == dead_id and j["last_error"] == "boom" for j in jobs)


def test_list_jobs_unknown_status_is_422(client):
    assert client.get("/api/jobs", params={"status": "bogus"}).status_code == 422


def test_retry_job_resets_dead_job_to_pending(client):
    job_id = _dead_job()
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert r.json() == {"retried": True}
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "pending"
        assert job.attempts == 0


def test_retry_job_unknown_id_is_404(client):
    assert client.post("/api/jobs/999999999/retry").status_code == 404


def test_retry_job_not_dead_is_404(client):
    with session_scope() as session:
        job = Job(job_type="parse", status="pending")
        session.add(job)
        session.flush()
        job_id = job.id
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 404


def test_pipeline_metrics_includes_document_count(client, seeded_companies):
    body = client.get("/api/metrics/pipeline").json()
    assert body["document_count"] >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_features.py -k "jobs or document_count" -v`
Expected: FAIL — `404` for `/api/jobs` (route doesn't exist), `KeyError: 'document_count'`

- [ ] **Step 3: Implement the endpoints**

Add a new section to `src/argus/api/routes.py`, right before `# --- observability ---`:

```python
# --- jobs ---


_JOB_STATUSES = ("pending", "running", "completed", "failed", "dead")


@router.get("/api/jobs")
def list_jobs(
    status: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> list[dict]:
    if status not in _JOB_STATUSES:
        raise HTTPException(422, f"status must be one of {_JOB_STATUSES}")
    rows = session.scalars(
        select(Job)
        .where(Job.status == status)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": j.id, "job_type": j.job_type, "document_id": j.document_id,
            "attempts": j.attempts, "max_attempts": j.max_attempts,
            "last_error": j.last_error, "created_at": j.created_at,
        }
        for j in rows
    ]


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, session: Session = Depends(get_db)) -> dict:
    job = session.get(Job, job_id)
    if job is None or job.status != "dead":
        raise HTTPException(404, "no dead job with that id")
    job.status = "pending"
    job.attempts = 0
    job.run_after = datetime.now(UTC)
    return {"retried": True}
```

Update `pipeline_metrics` to add the document count. Replace:

```python
    return {
        "queue_depth": queue,
        "stages_24h": stages,
        "oldest_pending_seconds": oldest_pending_seconds,
        "retries_24h": retries_24h,
    }
```

with:

```python
    return {
        "queue_depth": queue,
        "stages_24h": stages,
        "oldest_pending_seconds": oldest_pending_seconds,
        "retries_24h": retries_24h,
        "document_count": session.scalar(select(func.count()).select_from(Document)),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_features.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/argus/api/routes.py tests/test_api_features.py
git commit -m "api: dead-letter job list + retry endpoint, document count in pipeline metrics"
```

---

### Task 4: Scaffold the Vite + React + TypeScript + Tailwind v4 project

**Files:**
- Create: `web/` (Vite scaffold — package.json, tsconfig*.json, index.html, src/main.tsx, src/App.tsx, vite.config.ts)
- Modify: `.gitignore` (add `web/node_modules`, `web/dist`)

**Interfaces:**
- Produces: `web/dist/index.html` + hashed assets after `npm run build` — the artifact Task 12 serves from FastAPI.

- [ ] **Step 1: Scaffold with Vite**

Run from the repo root:

```bash
npm create vite@latest web -- --template react-ts
cd web
npm install
```

- [ ] **Step 2: Add Tailwind v4**

```bash
npm install tailwindcss @tailwindcss/vite
```

Replace the contents of `web/src/index.css` with:

```css
@import "tailwindcss";
```

Replace `web/vite.config.ts` with:

```typescript
import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
})
```

- [ ] **Step 3: Add the `@/*` path alias to TypeScript config**

Vite's `react-ts` template splits config into `tsconfig.json` (references only) and `tsconfig.app.json` (the one that actually applies to `src/`). Open `web/tsconfig.app.json` and add `baseUrl`/`paths` inside `compilerOptions`:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

(Merge into the existing `compilerOptions` object — don't replace the whole file. If a future Vite version names this file differently, apply the same two keys to whichever `tsconfig*.json` has `"include": ["src"]`.)

- [ ] **Step 4: Replace the placeholder page**

Replace `web/src/App.tsx` with a minimal placeholder (later tasks replace this with the router):

```tsx
export default function App() {
  return <div className="p-8 text-2xl font-semibold">Argus</div>
}
```

- [ ] **Step 5: Ignore build artifacts**

Add to `.gitignore` (repo root):

```
web/node_modules
web/dist
```

- [ ] **Step 6: Verify the build**

Run: `cd web && npm run build`
Expected: exits 0, creates `web/dist/index.html`

Run: `test -f web/dist/index.html && echo OK`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add web .gitignore
git commit -m "web: scaffold Vite + React + TypeScript + Tailwind v4"
```

---

### Task 5: TanStack Router + Query, API client, app shell

**Files:**
- Create: `web/src/lib/api.ts`, `web/src/lib/types.ts`, `web/src/lib/theme.ts`
- Create: `web/src/components/app-shell.tsx`
- Create: `web/src/routes/__root.tsx`, `web/src/routes/index.tsx`
- Modify: `web/vite.config.ts`, `web/src/main.tsx`
- Delete: `web/src/App.tsx`, `web/src/App.css` (if scaffolded)

**Interfaces:**
- Produces: `api.get<T>(path)`, `api.post<T>(path, body?)`, `ApiError`, `getApiKey()/setApiKey()` from `lib/api.ts` — consumed by every later page task. `toggleTheme()`/`initTheme()` from `lib/theme.ts`. Route tree registered under `/` (investigations list placeholder) and `__root` (shell + outlet).

- [ ] **Step 1: Install dependencies**

```bash
cd web
npm install @tanstack/react-router @tanstack/react-query
npm install -D @tanstack/router-plugin
```

- [ ] **Step 2: Enable file-based routing in Vite config**

Replace `web/vite.config.ts`:

```typescript
import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
})
```

- [ ] **Step 3: Write the API client**

Create `web/src/lib/api.ts`:

```typescript
const API_KEY_STORAGE = "argus_api_key"

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE)
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE, key)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getApiKey()
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  if (key) headers.set("X-API-Key", key)

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new Event("argus:unauthorized"))
    throw new ApiError(401, "invalid or missing API key")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
}
```

- [ ] **Step 4: Write shared API types**

Create `web/src/lib/types.ts`:

```typescript
export interface Investigation {
  id: string
  question: string
  status: string
  confidence: number | null
  confidence_breakdown: { score?: number; components?: Record<string, number>; evidence_count?: number }
  version: number
  created_at: string
  last_refreshed_at: string | null
  new_evidence_available: boolean
}

export interface Hypothesis {
  id: string
  statement: string
  created_at: string
}

export interface InvestigationLinkRef {
  link_type: string
  investigation_id: string
  question: string
}

export interface InvestigationDetail extends Investigation {
  hypotheses: Hypothesis[]
  links: InvestigationLinkRef[]
}

export interface Citation {
  index: number
  chunk_id: string
  document_id: string
  title: string | null
  url: string | null
  source: string
  published_at: string | null
  excerpt: string
}

export interface Report {
  id: string
  version: number
  executive_summary: string
  key_findings: string[]
  risks: string[]
  follow_up_questions: string[]
  narrative: string
  model: string
  created_at: string
  citations: Citation[]
}

export interface Evidence {
  chunk_id: string
  document_id: string
  stance: "supporting" | "contradicting" | "unknown"
  rationale: string
  query: string
  excerpt: string
  strategy: string
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  text: string
  title: string | null
  url: string | null
  source: string
  doc_type: string
  published_at: string | null
  scores: Record<string, number>
  strategy: string
}

export interface Job {
  id: number
  job_type: string
  document_id: string | null
  attempts: number
  max_attempts: number
  last_error: string | null
  created_at: string
}

export interface PipelineMetrics {
  queue_depth: Record<string, number>
  stages_24h: { stage: string; status: string; runs: number; avg_duration_ms: number }[]
  oldest_pending_seconds: number | null
  retries_24h: number
  document_count: number
}
```

- [ ] **Step 5: Write the theme helper**

Create `web/src/lib/theme.ts`:

```typescript
const THEME_STORAGE = "argus_theme"

export function initTheme(): void {
  const stored = localStorage.getItem(THEME_STORAGE)
  const dark = stored ? stored === "dark" : true // dark by default
  document.documentElement.classList.toggle("dark", dark)
}

export function toggleTheme(): void {
  const dark = !document.documentElement.classList.contains("dark")
  document.documentElement.classList.toggle("dark", dark)
  localStorage.setItem(THEME_STORAGE, dark ? "dark" : "light")
}
```

- [ ] **Step 6: Write the app shell**

Create `web/src/components/app-shell.tsx`:

```tsx
import { Link, Outlet } from "@tanstack/react-router"
import { toggleTheme } from "@/lib/theme"

const NAV = [
  { to: "/", label: "Investigations" },
  { to: "/search", label: "Search" },
  { to: "/pipeline", label: "Pipeline" },
]

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-56 shrink-0 border-r border-border p-4">
        <div className="mb-6 text-lg font-bold tracking-wide text-primary">ARGUS</div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground [&.active]:bg-accent [&.active]:text-foreground"
              activeOptions={{ exact: item.to === "/" }}
              activeProps={{ className: "active" }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-end border-b border-border px-6 py-3">
          <button
            onClick={toggleTheme}
            className="rounded-md border border-border px-3 py-1 text-sm text-muted-foreground hover:text-foreground"
          >
            Toggle theme
          </button>
        </header>
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Write the root route and a placeholder index route**

Create `web/src/routes/__root.tsx`:

```tsx
import { createRootRoute } from "@tanstack/react-router"
import { AppShell } from "@/components/app-shell"

export const Route = createRootRoute({
  component: AppShell,
})
```

Create `web/src/routes/index.tsx` (replaced with the real investigations list in Task 7):

```tsx
import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/")({
  component: () => <div>Investigations (coming in Task 7)</div>,
})
```

- [ ] **Step 8: Wire up the router and query client in main.tsx**

Delete `web/src/App.tsx` and `web/src/App.css` if present.

Replace `web/src/main.tsx`:

```tsx
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { routeTree } from "./routeTree.gen"
import { initTheme } from "@/lib/theme"
import "./index.css"

initTheme()

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const queryClient = new QueryClient()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
```

`routeTree.gen.ts` is generated by the `tanstackRouter` Vite plugin the first time the dev server or build runs — do not hand-write it.

- [ ] **Step 9: Verify**

Run: `cd web && npm run build`
Expected: exits 0; `src/routeTree.gen.ts` now exists (generated); `web/dist/index.html` produced

Run: `cd web && npm run dev` (manual check, then Ctrl-C)
Expected: dev server starts, visiting it in a browser shows the sidebar shell with "Investigations (coming in Task 7)"

- [ ] **Step 10: Commit**

```bash
git add web
git commit -m "web: TanStack Router + Query, API client, app shell with theme toggle"
```

---

### Task 6: shadcn/ui initialization and core components

**Files:**
- Create: `web/components.json` (generated by shadcn CLI)
- Create: `web/src/components/ui/*.tsx` (generated: button, table, badge, card, dialog, input, textarea, label, sonner, popover, skeleton, separator, select)
- Modify: `web/src/index.css` (shadcn adds theme tokens)

**Interfaces:**
- Produces: importable primitives `@/components/ui/{button,table,badge,card,dialog,input,textarea,label,sonner,popover,skeleton,separator,select}` used by every page task from here on.

- [ ] **Step 1: Initialize shadcn/ui**

```bash
cd web
npx shadcn@latest init
```

Accept the defaults it proposes (it will detect Vite + Tailwind v4 + the `@` alias from `tsconfig.app.json`/`vite.config.ts` already in place). This generates `components.json` and appends color tokens to `src/index.css`.

- [ ] **Step 2: Add the core components**

```bash
npx shadcn@latest add button table badge card dialog input textarea label sonner popover skeleton separator select
```

- [ ] **Step 3: Mount the toast host**

In `web/src/main.tsx`, add the `Toaster` from sonner so any page can call `toast(...)`:

```tsx
import { Toaster } from "@/components/ui/sonner"
```

and inside the render tree, alongside `RouterProvider`:

```tsx
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
    <Toaster />
  </QueryClientProvider>
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: no errors

Run: `cd web && npm run build`
Expected: exits 0

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "web: initialize shadcn/ui, add core components"
```

---

### Task 7: Investigations list page + create dialog

**Files:**
- Modify: `web/src/routes/index.tsx`
- Create: `web/src/components/new-investigation-dialog.tsx`

**Interfaces:**
- Consumes: `api.get<Investigation[]>("/api/investigations")`, `api.post<Investigation>("/api/investigations", {question, hypothesis})` from Task 5's `lib/api.ts`; `Investigation` type from `lib/types.ts`.
- Produces: `/` route renders the table; navigating to a row goes to `/investigations/$investigationId` (built in Task 8).

- [ ] **Step 1: Build the create-investigation dialog**

Create `web/src/components/new-investigation-dialog.tsx`:

```tsx
import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Investigation } from "@/lib/types"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"

export function NewInvestigationDialog() {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState("")
  const [hypothesis, setHypothesis] = useState("")
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: () =>
      api.post<Investigation>("/api/investigations", {
        question,
        hypothesis: hypothesis || undefined,
      }),
    onSuccess: (inv) => {
      queryClient.invalidateQueries({ queryKey: ["investigations"] })
      setOpen(false)
      setQuestion("")
      setHypothesis("")
      navigate({ to: "/investigations/$investigationId", params: { investigationId: inv.id } })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New investigation</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New investigation</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="question">Question</Label>
            <Textarea
              id="question"
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want to investigate?"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="hypothesis">Hypothesis (optional)</Label>
            <Input
              id="hypothesis"
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!question.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Running…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Build the investigations list route**

Replace `web/src/routes/index.tsx`:

```tsx
import { createFileRoute, Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Investigation } from "@/lib/types"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { NewInvestigationDialog } from "@/components/new-investigation-dialog"

export const Route = createFileRoute("/")({
  component: InvestigationsPage,
})

function InvestigationsPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.get<Investigation[]>("/api/investigations"),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Investigations</h1>
        <NewInvestigationDialog />
      </div>
      {isPending && <Skeleton className="h-40 w-full" />}
      {error && <p className="text-destructive">{error.message}</p>}
      {data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Question</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((inv) => (
              <TableRow key={inv.id}>
                <TableCell>
                  <Link
                    to="/investigations/$investigationId"
                    params={{ investigationId: inv.id }}
                    className="hover:underline"
                  >
                    {inv.question}
                  </Link>
                  {inv.new_evidence_available && (
                    <Badge variant="outline" className="ml-2">stale</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={inv.status === "complete" ? "default" : "secondary"}>
                    {inv.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {inv.confidence !== null ? (
                    <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${Math.round(inv.confidence * 100)}%` }}
                      />
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(inv.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no errors, build succeeds

Run: `cd web && npm run dev`, open the browser, click "New investigation", submit a question against a running `make up && make migrate && make api` backend.
Expected: dialog closes, browser navigates to `/investigations/<id>` (a 404-ish placeholder page until Task 8 exists — that's expected at this point in the plan)

- [ ] **Step 4: Commit**

```bash
git add web
git commit -m "web: investigations list page + create-investigation dialog"
```

---

### Task 8: Investigation detail page

**Files:**
- Create: `web/src/routes/investigations.$investigationId.tsx`
- Create: `web/src/components/report-narrative.tsx`
- Create: `web/src/components/confidence-meter.tsx`

**Interfaces:**
- Consumes: `api.get<InvestigationDetail>`, `api.get<Report>` (404 tolerant — no report yet), `api.get<Evidence[]>`, `api.post` for refresh/replay; types from `lib/types.ts`.

- [ ] **Step 1: Confidence meter component**

Create `web/src/components/confidence-meter.tsx`:

```tsx
import type { Investigation } from "@/lib/types"

const LABELS: Record<string, string> = {
  source_diversity: "Source diversity",
  document_count: "Document count",
  source_quality: "Source quality",
  recency: "Recency",
  stance_agreement: "Stance agreement",
}

export function ConfidenceMeter({ inv }: { inv: Investigation }) {
  const components = inv.confidence_breakdown?.components ?? {}
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-primary"
            style={{ width: `${Math.round((inv.confidence ?? 0) * 100)}%` }}
          />
        </div>
        <span className="text-sm font-medium">
          {inv.confidence !== null ? `${Math.round(inv.confidence * 100)}%` : "—"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground">
        {Object.entries(components).map(([key, value]) => (
          <div key={key} className="flex justify-between">
            <span>{LABELS[key] ?? key}</span>
            <span>{Math.round(value * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Narrative + citation renderer**

Create `web/src/components/report-narrative.tsx`:

```tsx
import type { Citation } from "@/lib/types"

const MARKER_RE = /\[chunk:([0-9a-f-]{36})\]/g

export function ReportNarrative({ narrative, citations }: { narrative: string; citations: Citation[] }) {
  const byChunk = new Map(citations.map((c) => [c.chunk_id, c]))
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  MARKER_RE.lastIndex = 0
  while ((match = MARKER_RE.exec(narrative))) {
    parts.push(narrative.slice(lastIndex, match.index))
    const citation = byChunk.get(match[1])
    parts.push(
      <sup key={match.index}>
        <a href={`#cite-${citation?.index ?? "?"}`} className="text-primary">
          [{citation?.index ?? "?"}]
        </a>
      </sup>,
    )
    lastIndex = match.index + match[0].length
  }
  parts.push(narrative.slice(lastIndex))

  return (
    <div className="flex flex-col gap-4">
      <p className="whitespace-pre-wrap leading-relaxed">{parts}</p>
      {citations.length > 0 && (
        <ol className="flex flex-col gap-1 text-sm text-muted-foreground">
          {citations.map((c) => (
            <li key={c.chunk_id} id={`cite-${c.index}`}>
              [{c.index}]{" "}
              {c.url ? (
                <a href={c.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  {c.title ?? c.url}
                </a>
              ) : (
                <span>{c.title ?? c.source}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
```

Note: `narrative` is rendered as a plain string inside `<p>` — React escapes text content automatically, so no HTML injection is possible regardless of what the LLM produced. The only markup we add ourselves is the citation superscripts.

- [ ] **Step 3: The detail route**

Create `web/src/routes/investigations.$investigationId.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { api, ApiError } from "@/lib/api"
import type { Evidence, InvestigationDetail, Report } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfidenceMeter } from "@/components/confidence-meter"
import { ReportNarrative } from "@/components/report-narrative"
import { Link } from "@tanstack/react-router"

export const Route = createFileRoute("/investigations/$investigationId")({
  component: InvestigationDetailPage,
})

const STANCE_LABELS = { supporting: "Supporting", contradicting: "Contradicting", unknown: "Unknown" } as const

function InvestigationDetailPage() {
  const { investigationId } = Route.useParams()
  const queryClient = useQueryClient()

  const invQuery = useQuery({
    queryKey: ["investigation", investigationId],
    queryFn: () => api.get<InvestigationDetail>(`/api/investigations/${investigationId}`),
  })

  const reportQuery = useQuery({
    queryKey: ["report", investigationId],
    queryFn: () => api.get<Report>(`/api/investigations/${investigationId}/report`),
    retry: false,
    enabled: invQuery.data?.status === "complete",
  })

  const evidenceQuery = useQuery({
    queryKey: ["evidence", investigationId],
    queryFn: () => api.get<Evidence[]>(`/api/investigations/${investigationId}/evidence`),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["investigation", investigationId] })
    queryClient.invalidateQueries({ queryKey: ["report", investigationId] })
    queryClient.invalidateQueries({ queryKey: ["evidence", investigationId] })
  }

  const refresh = useMutation({
    mutationFn: () => api.post(`/api/investigations/${investigationId}/refresh`),
    onSuccess: () => {
      toast.success("Investigation refreshed")
      invalidateAll()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const replay = useMutation({
    mutationFn: () => api.post(`/api/investigations/${investigationId}/replay`),
    onSuccess: (result: any) =>
      toast(result.match ? "Replay matches recorded evidence" : "Replay diverged from recorded evidence"),
    onError: (err: Error) => toast.error(err.message),
  })

  if (invQuery.isPending) return <Skeleton className="h-64 w-full" />
  if (invQuery.error) return <p className="text-destructive">{invQuery.error.message}</p>
  const inv = invQuery.data!

  const byStance = { supporting: [] as Evidence[], contradicting: [] as Evidence[], unknown: [] as Evidence[] }
  for (const e of evidenceQuery.data ?? []) byStance[e.stance].push(e)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{inv.question}</h1>
          <p className="text-sm text-muted-foreground">
            {inv.status} · v{inv.version}
            {inv.new_evidence_available && " · new evidence available"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => replay.mutate()} disabled={replay.isPending}>
            Replay
          </Button>
          <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Confidence</CardTitle></CardHeader>
        <CardContent><ConfidenceMeter inv={inv} /></CardContent>
      </Card>

      {inv.hypotheses.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Hypotheses</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-2">
            {inv.hypotheses.map((h) => (
              <p key={h.id} className="text-sm">{h.statement}</p>
            ))}
          </CardContent>
        </Card>
      )}

      {reportQuery.data && (
        <Card>
          <CardHeader><CardTitle>Report</CardTitle></CardHeader>
          <CardContent>
            <ReportNarrative narrative={reportQuery.data.narrative} citations={reportQuery.data.citations} />
          </CardContent>
        </Card>
      )}
      {reportQuery.error instanceof ApiError && reportQuery.error.status !== 404 && (
        <p className="text-destructive">{reportQuery.error.message}</p>
      )}

      <Card>
        <CardHeader><CardTitle>Evidence</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {(["supporting", "contradicting", "unknown"] as const).map((stance) => (
            <div key={stance} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{STANCE_LABELS[stance]} ({byStance[stance].length})</h3>
              {byStance[stance].map((e) => (
                <div key={e.chunk_id} className="rounded-md border border-border p-3 text-sm">
                  <p>{e.excerpt}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{e.rationale}</p>
                </div>
              ))}
            </div>
          ))}
        </CardContent>
      </Card>

      {inv.links.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Linked investigations</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-1">
            {inv.links.map((link) => (
              <Link
                key={link.investigation_id}
                to="/investigations/$investigationId"
                params={{ investigationId: link.investigation_id }}
                className="text-sm hover:underline"
              >
                {link.link_type}: {link.question}
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no errors

Run: `cd web && npm run dev`, create an investigation, wait for it to complete, open its detail page.
Expected: confidence meter renders, report narrative shows numbered citations linking to the citation list below, evidence appears in the correct stance column, refresh/replay buttons work and toast on completion.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "web: investigation detail page — report, confidence, evidence, links"
```

---

### Task 9: Search page

**Files:**
- Create: `web/src/routes/search.tsx`

**Interfaces:**
- Consumes: `api.get<SearchResult[]>("/api/search?q=...&doc_type=...&company_id=...")`, `api.get<{id,name,cik,tickers}[]>("/api/companies?q=...")`.

- [ ] **Step 1: Build the search route**

Create `web/src/routes/search.tsx`:

```tsx
import { useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { SearchResult } from "@/lib/types"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/search")({
  component: SearchPage,
})

function SearchPage() {
  const [query, setQuery] = useState("")
  const [docType, setDocType] = useState("")

  const { data, isFetching, error } = useQuery({
    queryKey: ["search", query, docType],
    queryFn: () =>
      api.get<SearchResult[]>(
        `/api/search?${new URLSearchParams({
          q: query,
          ...(docType ? { doc_type: docType } : {}),
          k: "20",
        })}`,
      ),
    enabled: query.trim().length > 0,
  })

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Search</h1>
      <div className="flex gap-3">
        <Input
          placeholder="Search documents…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-md"
        />
        <Input
          placeholder="doc type (optional)"
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          className="max-w-40"
        />
      </div>
      {isFetching && <Skeleton className="h-32 w-full" />}
      {error && <p className="text-destructive">{error.message}</p>}
      <div className="flex flex-col gap-3">
        {data?.map((r) => (
          <Card key={r.chunk_id}>
            <CardContent className="flex flex-col gap-1 pt-4">
              <div className="flex items-center gap-2">
                <span className="font-medium">{r.title ?? "Untitled"}</span>
                <Badge variant="outline">{r.doc_type}</Badge>
                <span className="text-xs text-muted-foreground">{r.source}</span>
              </div>
              <p className="text-sm text-muted-foreground">{r.text.slice(0, 240)}…</p>
            </CardContent>
          </Card>
        ))}
        {data && data.length === 0 && <p className="text-muted-foreground">No results.</p>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no errors

Run: `cd web && npm run dev`, type a query against real data.
Expected: results render as cards; empty query shows no results and no request is fired (`enabled` guard).

- [ ] **Step 3: Commit**

```bash
git add web
git commit -m "web: search page"
```

---

### Task 10: Pipeline page

**Files:**
- Create: `web/src/routes/pipeline.tsx`

**Interfaces:**
- Consumes: `api.get<PipelineMetrics>("/api/metrics/pipeline")`, `api.get<Job[]>("/api/jobs?status=dead")`, `api.post("/api/jobs/{id}/retry")`.
- New dependency: `recharts` (for the per-stage run chart).

- [ ] **Step 1: Install recharts**

```bash
cd web
npm install recharts
```

- [ ] **Step 2: Build the pipeline route**

Create `web/src/routes/pipeline.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { api } from "@/lib/api"
import type { Job, PipelineMetrics } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/pipeline")({
  component: PipelinePage,
})

function stageChartData(metrics: PipelineMetrics) {
  const byStage = new Map<string, { stage: string; success: number; failure: number }>()
  for (const s of metrics.stages_24h) {
    const row = byStage.get(s.stage) ?? { stage: s.stage, success: 0, failure: 0 }
    row[s.status === "success" ? "success" : "failure"] = s.runs
    byStage.set(s.stage, row)
  }
  return [...byStage.values()]
}

function PipelinePage() {
  const queryClient = useQueryClient()

  const metricsQuery = useQuery({
    queryKey: ["pipeline-metrics"],
    queryFn: () => api.get<PipelineMetrics>("/api/metrics/pipeline"),
    refetchInterval: 15_000,
  })

  const deadQuery = useQuery({
    queryKey: ["jobs", "dead"],
    queryFn: () => api.get<Job[]>("/api/jobs?status=dead"),
    refetchInterval: 15_000,
  })

  const retry = useMutation({
    mutationFn: (jobId: number) => api.post(`/api/jobs/${jobId}/retry`),
    onSuccess: () => {
      toast.success("Job requeued")
      queryClient.invalidateQueries({ queryKey: ["jobs", "dead"] })
      queryClient.invalidateQueries({ queryKey: ["pipeline-metrics"] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  if (metricsQuery.isPending) return <Skeleton className="h-64 w-full" />
  if (metricsQuery.error) return <p className="text-destructive">{metricsQuery.error.message}</p>
  const metrics = metricsQuery.data!

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Pipeline</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {Object.entries(metrics.queue_depth).map(([status, count]) => (
          <Card key={status}>
            <CardHeader className="pb-2"><CardTitle className="text-sm font-normal text-muted-foreground">{status}</CardTitle></CardHeader>
            <CardContent className="text-2xl font-semibold">{count}</CardContent>
          </Card>
        ))}
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-normal text-muted-foreground">documents</CardTitle></CardHeader>
          <CardContent className="text-2xl font-semibold">{metrics.document_count}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Runs by stage (24h)</CardTitle></CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stageChartData(metrics)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="stage" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="success" stackId="a" fill="var(--color-primary, #16a34a)" />
              <Bar dataKey="failure" stackId="a" fill="var(--destructive, #dc2626)" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Dead-letter jobs ({deadQuery.data?.length ?? 0})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>id</TableHead>
                <TableHead>type</TableHead>
                <TableHead>attempts</TableHead>
                <TableHead>error</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(deadQuery.data ?? []).map((job) => (
                <TableRow key={job.id}>
                  <TableCell>{job.id}</TableCell>
                  <TableCell>{job.job_type}</TableCell>
                  <TableCell>{job.attempts}/{job.max_attempts}</TableCell>
                  <TableCell className="max-w-96 truncate text-muted-foreground">{job.last_error}</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => retry.mutate(job.id)} disabled={retry.isPending}>
                      Retry
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no errors

Run: `cd web && npm run dev`, open `/pipeline`.
Expected: queue cards, stacked bar chart, dead-letter table render; clicking Retry on a dead job removes it from the table and toasts success.

- [ ] **Step 4: Commit**

```bash
git add web
git commit -m "web: pipeline page — queue cards, stage chart, dead-letter retry"
```

---

### Task 11: Auth gate (API-key entry on 401)

**Files:**
- Create: `web/src/components/auth-gate.tsx`
- Modify: `web/src/components/app-shell.tsx`

**Interfaces:**
- Consumes: `setApiKey` from `lib/api.ts`; listens for the `"argus:unauthorized"` window event dispatched by `request()` in Task 5.

- [ ] **Step 1: Build the gate**

Create `web/src/components/auth-gate.tsx`:

```tsx
import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { setApiKey } from "@/lib/api"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [locked, setLocked] = useState(false)
  const [value, setValue] = useState("")
  const queryClient = useQueryClient()

  useEffect(() => {
    const onUnauthorized = () => setLocked(true)
    window.addEventListener("argus:unauthorized", onUnauthorized)
    return () => window.removeEventListener("argus:unauthorized", onUnauthorized)
  }, [])

  if (!locked) return <>{children}</>

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex w-80 flex-col gap-4 rounded-lg border border-border p-6">
        <h1 className="text-lg font-semibold">API key required</h1>
        <Input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Argus API key"
        />
        <Button
          onClick={() => {
            setApiKey(value)
            setLocked(false)
            queryClient.invalidateQueries()
          }}
          disabled={!value}
        >
          Save
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wrap the app shell with it**

In `web/src/components/app-shell.tsx`, wrap the returned JSX with `<AuthGate>`:

```tsx
import { AuthGate } from "@/components/auth-gate"
```

and change the component body's `return (...)` to wrap the existing `<div className="flex min-h-screen ...">...</div>` inside `<AuthGate>...</AuthGate>`.

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no errors

Run against a backend started with `ARGUS_API_KEY=test123 uv run uvicorn argus.main:app`, open the SPA in dev mode (proxying to that backend).
Expected: any `/api/*` call 401s → the key-entry screen appears; entering `test123` and saving unlocks the app and refetches data successfully.

- [ ] **Step 4: Commit**

```bash
git add web
git commit -m "web: API-key entry screen on 401"
```

---

### Task 12: Serve the SPA from FastAPI, delete the old htmx UI

**Files:**
- Modify: `src/argus/main.py`
- Modify: `pyproject.toml` (`[tool.importlinter]` layers list)
- Delete: `src/argus/ui/` (entire package — `views.py`, `templates/`, `static/htmx.min.js`, `__init__.py`)
- Modify: `tests/test_api_features.py` (remove the three htmx-only tests superseded by Tasks 1 and this task)

**Interfaces:**
- Produces: `GET /` and any non-`/api`, non-`/health`, non-`/static`-prefixed path serve `web/dist/index.html`; hashed assets under `web/dist/assets/*` are served directly.

- [ ] **Step 1: Remove the three htmx-dependent tests**

In `tests/test_api_features.py`, delete these three tests (they exercise routes that no longer exist once `ui/views.py` is gone — Task 1 already added their JSON-API equivalents):

```python
def test_static_htmx_is_served(client):
    r = client.get("/static/htmx.min.js")
    assert r.status_code == 200
```

```python
def test_citation_javascript_url_is_not_rendered_as_a_link(client):
    inv_id = _investigation_citing("javascript:alert(1)")
    r = client.get(f"/investigations/{inv_id}")
    assert r.status_code == 200
    assert "javascript:" not in r.text


def test_citation_http_url_still_renders_as_a_link(client):
    inv_id = _investigation_citing("https://example.com/good-source")
    r = client.get(f"/investigations/{inv_id}")
    assert r.status_code == 200
    assert 'href="https://example.com/good-source"' in r.text
```

Keep `_investigation_citing` itself — Task 1's tests still use it.

- [ ] **Step 2: Delete the old UI package**

```bash
git rm -r src/argus/ui
```

- [ ] **Step 3: Update `main.py` to serve the SPA**

Replace `src/argus/main.py`'s imports and app construction:

```python
from argus.api.routes import router as api_router
from argus.core.config import get_settings
from argus.core.logging import configure_logging, request_id
from argus.ui.views import router as ui_router

configure_logging(get_settings().log_level)
app = FastAPI(title="Argus", description="Enterprise Research Operating System")
app.include_router(api_router)
app.include_router(ui_router)
app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "ui" / "static"), name="static"
)
```

with:

```python
from argus.api.routes import router as api_router
from argus.core.config import get_settings
from argus.core.logging import configure_logging, request_id

configure_logging(get_settings().log_level)
app = FastAPI(title="Argus", description="Enterprise Research Operating System")
app.include_router(api_router)

_WEB_DIST = Path(__file__).parent.parent.parent / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="spa-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(_WEB_DIST / "index.html")
```

Add `FileResponse` to the existing `from fastapi.responses import JSONResponse` import line:

```python
from fastapi.responses import FileResponse, JSONResponse
```

Note: `_WEB_DIST.is_dir()` guard means the app still starts (API-only) in environments where `web/dist` hasn't been built — e.g. plain `pytest` runs before Task 13's Docker build step produces it. The catch-all route is registered last, after `api_router`, so `/api/*` and `/health*` always match their own routes first.

- [ ] **Step 4: Update the import-linter layers**

In `pyproject.toml`, remove `"argus.ui"` from the layers list:

```toml
layers = [
    "argus.ui",
    "argus.api",
    ...
]
```

becomes:

```toml
layers = [
    "argus.api",
    "argus.evals",
    "argus.investigations",
    "argus.agentruntime",
    "argus.research",
    "argus.dataplatform",
    "argus.knowledge",
    "argus.observability",
    "argus.core",
]
```

- [ ] **Step 5: Add a smoke test for the fallback route**

The fallback route is registered once at import time against the real
`web/dist` path, so the test only needs to confirm the route responds —
it can't retarget `_WEB_DIST` without reimporting the module. Add to
`tests/test_api_features.py`:

```python
def test_root_is_served(client):
    r = client.get("/")
    assert r.status_code == 200


def test_unknown_path_falls_back_to_spa_shell(client):
    r = client.get("/investigations/does-not-exist-as-a-file")
    assert r.status_code == 200
```

- [ ] **Step 6: Build the SPA once so the smoke tests have something to serve**

```bash
cd web && npm run build && cd ..
```

- [ ] **Step 7: Run the full backend suite**

Run: `uv run pytest`
Expected: all pass (htmx tests gone, new SPA-serving smoke tests pass)

Run: `uv run ruff check src tests && uv run lint-imports`
Expected: no violations (import-linter no longer expects `argus.ui`)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "serve React SPA from FastAPI, delete the Jinja2/htmx dashboard"
```

---

### Task 13: Multi-stage Dockerfile and Makefile targets

**Files:**
- Modify: `Dockerfile`
- Modify: `Makefile`

**Interfaces:** none (build tooling only)

- [ ] **Step 1: Add a Node build stage to the Dockerfile**

Replace `Dockerfile`:

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# app user matches the typical host uid (1000) so the ./data bind mount stays writable
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# dependency layer: cached until pyproject.toml/uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# project layer
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY evals/ evals/
RUN uv sync --frozen --no-dev

RUN chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
```

with:

```dockerfile
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# app user matches the typical host uid (1000) so the ./data bind mount stays writable
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# dependency layer: cached until pyproject.toml/uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# project layer
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY evals/ evals/
RUN uv sync --frozen --no-dev
COPY --from=web-build /web/dist web/dist

RUN chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
```

- [ ] **Step 2: Add Makefile targets**

In `Makefile`, add after the `api:` target:

```makefile
web:           ## Install web dependencies and build the SPA into web/dist
	cd web && npm install && npm run build

web-dev:       ## Run the SPA dev server (proxies /api and /health to :8000)
	cd web && npm run dev
```

Update the `.PHONY` line at the top to include the new targets:

```makefile
.PHONY: up down migrate test lint worker api eval stack stack-down backup restore web web-dev
```

- [ ] **Step 3: Verify**

Run: `docker build -t argus-web-test .`
Expected: builds successfully through both stages (requires Docker; if Docker isn't available in this environment, verify the Dockerfile syntax with `docker build --check .` or skip with a note — do not silently claim success without running one of these)

Run: `make web`
Expected: `web/dist/index.html` exists afterward

- [ ] **Step 4: Commit**

```bash
git add Dockerfile Makefile
git commit -m "docker: multi-stage build for the React SPA, add make web / make web-dev"
```

---

### Task 14: ADR-0010 — React SPA dashboard

**Files:**
- Create: `docs/adr/0010-react-spa-dashboard.md`

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0010-react-spa-dashboard.md`:

```markdown
# ADR-0010: React SPA dashboard

## Status

Accepted

## Context

Phase 7 chose Jinja2 + htmx for the dashboard specifically to avoid a build
pipeline (see the Phase 7 plan). That held while the UI was a thin,
read-mostly wrapper over the JSON API. Reaching an enterprise-standard bar —
sortable/filterable tables, real-time-feeling updates, charts, a componentized
design system — outgrows what server-rendered partials can deliver without
turning into an ad-hoc JS framework of our own.

## Decision

Replace the Jinja2/htmx dashboard with a React SPA (`web/`): React 19 +
TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Router + Query,
Recharts. It is built at Docker build time (`vite build` → `web/dist`) and
served as static files by the existing FastAPI app — Node is a build-stage
dependency only, never present in the running container or its runtime image
layer.

`src/argus/ui/` (templates, htmx views, vendored htmx.js) is deleted outright;
there is no fallback server-rendered UI.

## Consequences

- Node is now a build-time requirement (`make web`, or the Dockerfile's
  `web-build` stage). Contributors touching only the Python backend don't
  need it — the API and CLI plans are unaffected.
- The dashboard is a pure API consumer: any data it needs must exist as a
  JSON endpoint. Three additive endpoints were introduced for this
  (`report.citations`, `investigation.hypotheses`/`links`,
  `GET/POST /api/jobs`) — no existing endpoint's shape changed.
- The citation URL scheme guard (only `http(s)` becomes a link) moved from
  the Jinja view into the API response, since the frontend has no unit-test
  framework in v1 to verify client-side sanitization — the guard is verified
  by pytest instead, at the source of truth.
- `argus.ui` is removed from the import-linter layers contract
  (`pyproject.toml`) — the layer no longer exists.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0010-react-spa-dashboard.md
git commit -m "docs: ADR-0010 — React SPA dashboard"
```

---

### Task 15: Full-suite check

**Files:** none (verification only)

- [ ] **Step 1: Backend**

Run: `uv run pytest`
Expected: all pass

Run: `uv run ruff check src tests && uv run lint-imports`
Expected: no violations

- [ ] **Step 2: Frontend**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no type errors, build succeeds

- [ ] **Step 3: Manual end-to-end check**

```bash
make up && make migrate
make web
uv run uvicorn argus.main:app --port 8000
```

Open `http://localhost:8000/` in a browser. Confirm: investigations list loads, creating one navigates to its detail page, search returns results for ingested content, pipeline page shows queue cards and the stage chart, dark mode is the default and the toggle works, a hard refresh on `/investigations/<id>` still resolves (SPA fallback) instead of 404ing.

- [ ] **Step 4: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: full-suite check fixes"
```
(skip if nothing changed)
