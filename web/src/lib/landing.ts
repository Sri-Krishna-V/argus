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
    latest_document_at: "2026-08-20T00:00:00Z",
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
export function useStageRuns(): Record<string, StageRun> {
  const { data } = useQuery({
    queryKey: ["metrics", "pipeline"],
    queryFn: () => api.get<PipelineMetrics>("/api/metrics/pipeline"),
    staleTime: 60_000,
    retry: 1,
  })
  const out: Record<string, StageRun> = {}
  for (const row of data?.stages_24h ?? []) {
    const prev = out[row.stage] ?? { runs: 0, ms: null }
    out[row.stage] = {
      runs: prev.runs + row.runs,
      ms: row.status === "success" ? row.avg_duration_ms : prev.ms,
    }
  }
  return out
}

/** Filings are mostly boilerplate: disclosure-controls language, incorporation by
 *  reference, audit-standard recitals, exhibit indexes. A passage quoted on the landing
 *  page has to actually say something, so reject the known furniture outright and then
 *  reward management voice, business substance and figures. */
const FURNITURE =
  /^item \d|^\s*[•\u2022]|controls and procedures|incorporated (herein )?by reference|you should read|see note \d|table of contents|standards of the pcaob|we expense legal fees|exhibit \d|grace periods|qualified in its entirety|index to/i

const SUBSTANCE =
  /investment|revenue|margin|demand|growth|cost|customer|competit|antitrust|supply|capacity|datacenter|infrastructure|regulat/i

function passageScore(c: Citation): number {
  const text = c.excerpt.trim()
  if (FURNITURE.test(text)) return 0
  let score = 1
  if (/^(we|our)\b/i.test(text) || /\b(we|our)\b/i.test(text.slice(0, 70))) score += 3
  if (SUBSTANCE.test(text)) score += 3
  if (/\d/.test(text)) score += 1
  if (/\$|%|billion|million/i.test(text)) score += 2
  if (c.url) score += 1
  return score
}

function pickPassage(citations: Citation[]): { citation: Citation; score: number } | null {
  const ranked = citations
    .filter((c) => c.excerpt.trim().length > 120)
    .map((c) => ({ citation: c, score: passageScore(c) }))
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
      const picked = report ? pickPassage(report.citations ?? []) : null
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
