import { Link } from "@tanstack/react-router"
import { ArrowRightIcon, ArrowUpRightIcon } from "lucide-react"
import { SignalRidge } from "@/components/signal-ridge"
import { Skeleton } from "@/components/ui/skeleton"
import { SNAPSHOT_EVIDENCE, shortDate, useShowcase } from "@/lib/landing"
import type { Investigation } from "@/lib/types"

const MICRO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"

const SOURCE_LABEL: Record<string, string> = {
  sec_edgar: "SEC EDGAR",
  rss: "News",
  company_profiles: "Company profile",
}

const COMPONENT_LABEL: Record<string, string> = {
  source_diversity: "Source diversity",
  document_count: "Document count",
  source_quality: "Source quality",
  recency: "Recency",
  stance_agreement: "Stance agreement",
}

/** Chunk excerpts arrive truncated at a fixed length, which lands mid-word. Cut back to
 *  the last finished sentence, or failing that the last whole word. */
function tidy(excerpt: string): string {
  const text = excerpt.trim().replace(/\s+/g, " ")
  const lastStop = Math.max(text.lastIndexOf(". "), text.lastIndexOf(".”"))
  if (lastStop > text.length * 0.5) return text.slice(0, lastStop + 1)
  const lastSpace = text.lastIndexOf(" ")
  return lastSpace > 0 ? `${text.slice(0, lastSpace)}…` : text
}

function ConfidenceBlock({ inv }: { inv: Investigation }) {
  const components = Object.entries(inv.confidence_breakdown?.components ?? {})
  const pct = inv.confidence !== null ? Math.round(inv.confidence * 100) : null

  return (
    <div>
      <span className={MICRO}>Computed confidence</span>
      <div className="mt-5 flex items-end gap-5">
        <span className="text-6xl leading-none font-light tracking-[-0.03em] tabular-nums text-white">
          {pct ?? "—"}
          <span className="text-2xl text-muted-foreground">%</span>
        </span>
        <div className="relative h-16 min-w-0 flex-1 overflow-hidden rounded-sm">
          <SignalRidge className="absolute inset-0 h-full w-full" amplitude={inv.confidence ?? 0} />
        </div>
      </div>
      <dl className="mt-7 flex flex-col gap-2.5 border-t border-border pt-5 font-mono text-[11px] tracking-[0.08em]">
        {components.map(([key, component]) => (
          <div key={key} className="flex items-baseline justify-between gap-4">
            <dt className="text-muted-foreground">{COMPONENT_LABEL[key] ?? key}</dt>
            <dd className="shrink-0 tabular-nums text-white">
              {Math.round(component.value * 100)}%
              <span className="text-muted-foreground"> ×{component.weight}</span>
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
        Five weighted inputs, evaluated in code. No model is asked how sure it is.
      </p>
    </div>
  )
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
          <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,1fr)_26rem]">
            <div className="flex flex-col gap-5">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
            <Skeleton className="h-48 w-full" />
          </div>
        ) : (
          <div className="mt-14 grid items-start gap-14 lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-20">
            <div className="min-w-0">
              <p className="leading-relaxed text-muted-foreground">
                Asked of the corpus: <span className="text-white">{investigation.question}</span>
              </p>

              <blockquote className="mt-8 border-l border-primary/50 pl-6">
                <p className="max-w-[44rem] text-2xl leading-[1.35] font-light tracking-[-0.02em] text-white sm:text-[1.75rem]">
                  {tidy(citation.excerpt)}
                </p>
              </blockquote>

              <div className="mt-6 flex flex-col gap-2 pl-6 font-mono text-[11px] tracking-[0.1em] text-muted-foreground">
                <span className="[overflow-wrap:anywhere]">
                  chunk:{citation.chunk_id.slice(0, 8)}
                  <span className="text-muted-foreground/80">{citation.chunk_id.slice(8)}</span>
                </span>
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-white/70">cited as evidence</span>
                  <span>{SOURCE_LABEL[citation.source] ?? citation.source}</span>
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
                  <span className={MICRO}>
                    snapshot · {shortDate(`${SNAPSHOT_EVIDENCE.snapshot}T00:00:00Z`)}
                  </span>
                )}
              </div>
            </div>

            <div className="lg:sticky lg:top-20">
              <ConfidenceBlock inv={investigation} />
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
