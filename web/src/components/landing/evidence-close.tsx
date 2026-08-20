import { Link } from "@tanstack/react-router"
import { ArrowRightIcon, ArrowUpRightIcon } from "lucide-react"
import { ConfidenceMeter } from "@/components/confidence-meter"
import { Skeleton } from "@/components/ui/skeleton"
import { shortDate, useShowcase, type Showcase } from "@/lib/landing"
import type { Investigation } from "@/lib/types"

const MICRO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"

const SOURCE_LABEL: Record<string, string> = {
  sec_edgar: "SEC EDGAR",
  rss: "News",
  company_profiles: "Company profile",
}

/** Read off the live deployment on 2026-08-20 and kept verbatim, for the case where the
 *  API cannot be reached. Real filing text either way — never a written-for-the-page
 *  quote, and never presented as live. */
const SNAPSHOT_EVIDENCE: Showcase & { snapshot: string } = {
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

/** Chunk excerpts arrive truncated at a fixed length, which lands mid-word. Cut back to
 *  the last finished sentence, or failing that the last whole word. */
function tidy(excerpt: string): string {
  const text = excerpt.trim().replace(/\s+/g, " ")
  const lastStop = Math.max(text.lastIndexOf(". "), text.lastIndexOf(".\u201d"))
  if (lastStop > text.length * 0.5) return text.slice(0, lastStop + 1)
  const lastSpace = text.lastIndexOf(" ")
  return lastSpace > 0 ? `${text.slice(0, lastSpace)}\u2026` : text
}

export function EvidenceClose() {
  const { showcase, pending } = useShowcase()
  const shown = showcase ?? SNAPSHOT_EVIDENCE
  const isSnapshot = !showcase
  const { investigation, citation } = shown

  return (
    <section id="evidence" className="border-t border-border">
      <div className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
        <h2 className="max-w-[36rem] text-3xl leading-[1.1] font-light tracking-[-0.025em] text-white sm:text-4xl">
          What comes out the other end
        </h2>
        <p className="mt-5 max-w-[44rem] leading-relaxed text-muted-foreground">
          An investigation resolves into evidence, and every piece of it keeps the passage it
          came from. Below is a real question this deployment has answered, one of the
          passages its report cites, and the confidence the system computed for it.
        </p>

        {pending ? (
          <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,1fr)_25rem]">
            <div className="flex flex-col gap-4">
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <div className="mt-14 grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_25rem] lg:gap-16">
            <div className="min-w-0">
              <span className={MICRO}>Research question</span>
              <p className="mt-3 text-2xl leading-snug font-light tracking-[-0.015em] text-white">
                {investigation.question}
              </p>

              <blockquote className="mt-10 border-l border-border pl-5">
                <p className="max-w-[68ch] leading-[1.7] text-foreground/90">
                  {tidy(citation.excerpt)}
                </p>
              </blockquote>

              <div className="mt-5 flex flex-col gap-1.5 pl-5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground">
                <span>
                  chunk:{citation.chunk_id.slice(0, 8)}
                  <span className="text-muted-foreground/50">{citation.chunk_id.slice(8)}</span>
                </span>
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-white/70">{SOURCE_LABEL[citation.source] ?? citation.source}</span>
                  <span>{shortDate(citation.published_at)}</span>
                  {citation.url && (
                    <a
                      href={citation.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      {citation.title ?? "source filing"}
                      <ArrowUpRightIcon className="size-3" />
                    </a>
                  )}
                </span>
              </div>

              <p className="mt-8 max-w-[60ch] text-sm leading-relaxed text-muted-foreground">
                That passage is the filing&rsquo;s own text, resolved through the citation. The
                report prose around it is scripted in this deployment
                {shown.model ? ` (model=${shown.model})` : ""} — the pipeline, the retrieval and
                the score are not.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-3">
                <Link
                  to="/app/investigations/$investigationId"
                  params={{ investigationId: investigation.id }}
                  className="group inline-flex items-center gap-2 border-b border-primary/40 pb-1 text-primary transition-colors hover:border-primary"
                >
                  Open this investigation
                  <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
                {isSnapshot && (
                  <span className={MICRO}>snapshot · {SNAPSHOT_EVIDENCE.snapshot}</span>
                )}
              </div>
            </div>

            <div className="lg:sticky lg:top-16">
              <span className={MICRO}>Computed confidence</span>
              <div className="mt-4">
                <ConfidenceMeter inv={investigation} />
              </div>
              <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
                Five weighted inputs, evaluated in code. No model is asked how sure it is.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
