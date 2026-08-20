import { useEffect, useRef, useState } from "react"
import { useQueries, useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Citation, Investigation, PipelineMetrics, Report } from "@/lib/types"

export interface CorpusMetrics {
  documents: number
  chunks: number
  entity_mentions: number
  graph_edges: number
  investigations_complete: number
  latest_document_at: string | null
}

/** Last figures read off the live deployment. Rendered only when the API cannot be
 *  reached, and always labelled with the date it was taken — a stale number presented
 *  as live is the one thing this page cannot afford. */
export const SNAPSHOT: { taken: string; corpus: CorpusMetrics } = {
  taken: "2026-08-20",
  corpus: {
    documents: 122,
    chunks: 1378,
    entity_mentions: 1163,
    graph_edges: 153,
    investigations_complete: 7,
    latest_document_at: "2026-08-20T03:37:47.213626Z",
  },
}

export function useCorpus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metrics", "corpus"],
    queryFn: () => api.get<CorpusMetrics>("/api/metrics/corpus"),
    staleTime: 60_000,
    retry: 1,
  })
  return { corpus: data ?? SNAPSHOT.corpus, live: Boolean(data), pending: isPending, failed: isError }
}

export interface StageRun {
  runs: number
  ms: number | null
}

/** `stages_24h` is a rolling 24-hour window: on an idle deployment it is empty, and the
 *  rail has to read correctly at zero. Stage identity and order are static truth; only
 *  the throughput figures are live. */
export function usePipelineFacts(): {
  runs: Record<string, StageRun>
  dead: number
  live: boolean
} {
  const { data } = useQuery({
    queryKey: ["metrics", "pipeline"],
    queryFn: () => api.get<PipelineMetrics>("/api/metrics/pipeline"),
    staleTime: 60_000,
    retry: 1,
  })
  const runs: Record<string, StageRun> = {}
  for (const row of data?.stages_24h ?? []) {
    const prev = runs[row.stage] ?? { runs: 0, ms: null }
    runs[row.stage] = {
      runs: prev.runs + row.runs,
      ms: row.status === "success" ? row.avg_duration_ms : prev.ms,
    }
  }
  return { runs, dead: data?.queue_depth?.dead ?? 0, live: Boolean(data) }
}

/** Filings are mostly boilerplate: disclosure-controls language, incorporation by
 *  reference, audit-standard recitals, exhibit indexes. A passage quoted on the landing
 *  page has to actually say something, so reject the known furniture outright and then
 *  reward management voice, business substance and figures. */
const FURNITURE =
  /^item \d|^\s*[•\u2022]|controls and procedures|incorporated (herein )?by reference|you should read|see note \d|table of contents|standards of the pcaob|we expense legal fees|exhibit \d|grace periods|qualified in its entirety|index to/i

const SUBSTANCE =
  /investment|revenue|margin|demand|growth|cost|customer|competit|antitrust|supply|capacity|datacenter|infrastructure|regulat/i

const STOPWORDS = new Set([
  "what", "which", "does", "did", "do", "is", "are", "was", "were", "the", "a", "an", "of",
  "in", "on", "for", "to", "and", "or", "its", "their", "his", "her", "most", "recent",
  "identify", "describe", "about", "how", "why", "any", "has", "have", "been", "that",
])

function terms(question: string): string[] {
  return [
    ...new Set(
      question
        .toLowerCase()
        .replace(/[^a-z\s]/g, " ")
        .split(/\s+/)
        .filter((w) => w.length > 3 && !STOPWORDS.has(w))
        .map((w) => w.replace(/(ies|s)$/, "")),
    ),
  ]
}

/** A passage shown under a question has to bear on that question — a real excerpt about
 *  VR headsets under "quarterly financial results" is the one thing a sceptic checks. */
function passageScore(c: Citation, question: string): number {
  // filings arrive with non-breaking spaces in them, so "Note\u00a08" only matches the
  // boilerplate patterns once the whitespace is normalised
  const text = c.excerpt.trim().replace(/\s+/g, " ")
  if (FURNITURE.test(text)) return 0

  const body = text.toLowerCase()
  const title = (c.title ?? "").toLowerCase()
  let score = 1
  // the passage should at least come from the filing the question is about
  for (const term of terms(question)) {
    if (body.includes(term)) score += 3
    else if (title.includes(term)) score += 4
  }
  if (/^(we|our)\b/i.test(text) || /\b(we|our)\b/i.test(text.slice(0, 70))) score += 2
  if (SUBSTANCE.test(text)) score += 2
  if (/\$|%|billion|million/i.test(text)) score += 2
  if (/\d/.test(text)) score += 1
  if (c.url) score += 1
  return score
}

function pickPassage(
  citations: Citation[],
  question: string,
): { citation: Citation; score: number } | null {
  const ranked = citations
    .filter((c) => c.excerpt.trim().length > 120)
    .map((c) => ({ citation: c, score: passageScore(c, question) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
  return ranked[0] ?? null
}

export interface Showcase {
  investigation: Investigation
  citation: Citation
  model: string
}

/** The closing passage quotes real evidence from a real filing. The newest
 *  investigations are often `created` or `failed` with a null confidence, and the list
 *  endpoint has no status filter — so take the finished, scored ones, read their reports,
 *  and show whichever has the passage most worth reading. */
export function useShowcase() {
  const investigations = useQuery({
    queryKey: ["investigations", "landing"],
    queryFn: () => api.get<Investigation[]>("/api/investigations?limit=100"),
    staleTime: 60_000,
    retry: 1,
  })

  const finished = (investigations.data ?? [])
    .filter((inv) => inv.status === "complete" && inv.confidence !== null)
    .slice(0, 3)

  const reports = useQueries({
    queries: finished.map((inv) => ({
      queryKey: ["report", inv.id],
      queryFn: () => api.get<Report>(`/api/investigations/${inv.id}/report`),
      staleTime: 60_000,
      retry: 1,
    })),
  })

  const best = finished
    .map((investigation, i) => {
      const report = reports[i]?.data
      const picked = report ? pickPassage(report.citations ?? [], investigation.question) : null
      return picked ? { investigation, citation: picked.citation, model: report!.model, score: picked.score } : null
    })
    .filter((x): x is Showcase & { score: number } => x !== null)
    .sort((a, b) => b.score - a.score)[0]

  const showcase: Showcase | null = best
    ? { investigation: best.investigation, citation: best.citation, model: best.model }
    : null

  return {
    showcase,
    pending: investigations.isPending || reports.some((r) => r.isPending),
  }
}

/** Read off the live deployment on 2026-08-20 and kept verbatim, for the case where the
 *  API cannot be reached. Real filing text either way — never a written-for-the-page
 *  quote, and never presented as live. */
export const SNAPSHOT_EVIDENCE: Showcase & { snapshot: string } = {
  snapshot: "2026-08-20",
  model: "canned-demo",
  investigation: {
    id: "6368a62b-2b39-4377-9f63-a843d35d7947",
    question: "Which chipmakers are exposed to AI demand swings?",
    status: "complete",
    confidence: 0.851,
    confidence_breakdown: {
      score: 0.851,
      components: {
        recency: { value: 1, weight: 0.15 },
        document_count: { value: 1, weight: 0.15 },
        source_quality: { value: 1, weight: 0.2 },
        source_diversity: { value: 0.6667, weight: 0.25 },
        stance_agreement: { value: 0.7391, weight: 0.25 },
      },
      evidence_count: 23,
    },
    version: 1,
    created_at: "2026-08-20T03:38:00.000Z",
    last_refreshed_at: null,
    new_evidence_available: false,
  } as Investigation,
  citation: {
    index: 2,
    chunk_id: "9eaeefdb-78cc-4553-81a0-0043b8af5940",
    document_id: "30435502-bab9-40bf-b1e4-e86efc36147b",
    title: "MICROSOFT CORP 10-Q 2026-04-29",
    url: "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft-20260331.htm",
    source: "sec_edgar",
    published_at: "2026-04-29T00:00:00Z",
    excerpt:
      "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins. We continue to identify and evaluate opportunities to expand our datacenter locations.",
  },
}

/** One observer, one active index — drives the rail and the counters together. */
export function useActiveIndex(count: number) {
  const refs = useRef<(HTMLElement | null)[]>([])
  const [active, setActive] = useState(0)

  useEffect(() => {
    const nodes = refs.current.filter(Boolean) as HTMLElement[]
    if (nodes.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const index = nodes.indexOf(entry.target as HTMLElement)
          if (index >= 0) setActive(index)
        }
      },
      // a band across the middle of the viewport: the stage you are reading is the
      // stage the rail points at, not the one scrolling past the top edge
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    )
    for (const node of nodes) observer.observe(node)
    return () => observer.disconnect()
  }, [count])

  return {
    active,
    register: (index: number) => (node: HTMLElement | null) => {
      refs.current[index] = node
    },
  }
}

const REDUCED = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** Counts once, on arrival, then holds. Exponential ease-out. */
export function useCountUp(target: number, run: boolean): number {
  const [value, setValue] = useState(() => (REDUCED() ? target : 0))
  const done = useRef(false)

  useEffect(() => {
    if (!run || done.current) return
    done.current = true
    if (REDUCED()) return setValue(target)

    const start = performance.now()
    const duration = 900
    let raf = 0
    const frame = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 4)
      setValue(Math.round(target * eased))
      if (t < 1) raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [run, target])

  // a target that arrives after the animation ran (live data replacing the snapshot)
  // lands without re-animating
  useEffect(() => {
    if (done.current && !REDUCED()) setValue(target)
  }, [target])

  return value
}

export const fmt = new Intl.NumberFormat("en-US")

export function shortDate(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}
