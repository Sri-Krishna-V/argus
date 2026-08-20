import { StagePayload, type PayloadKind } from "@/components/landing/stage-payload"
import {
  fmt,
  shortDate,
  useActiveIndex,
  useCountUp,
  useCorpus,
  usePipelineFacts,
  SNAPSHOT,
  type CorpusMetrics,
} from "@/lib/landing"

const MICRO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"

interface Facts {
  corpus: CorpusMetrics
  dead: number
}

interface Figure {
  value: number
  unit: string
  /** corpus figures fall back to a dated snapshot; pipeline and static ones do not */
  source: "corpus" | "pipeline" | "static"
}

interface Stage {
  kind: PayloadKind
  title: string
  body: string
  event: string
  /** The artifact only this stage produces. Stages that derive no new count of their own
   *  carry none — five stages sharing two numbers is padding, not evidence. */
  figure?: (f: Facts) => Figure
  /** wide stages break the reading rhythm — the visual takes the full measure */
  wide?: boolean
}

const STAGES: Stage[] = [
  {
    kind: "parse",
    title: "Raw bytes become a row that can never change",
    body: "A filing is stored by the hash of its own content, then registered as a document. A database trigger rejects any update to it — only status and version advance. Everything downstream is re-derivable from the bytes on disk.",
    event: "document.parsed",
    figure: ({ corpus }) => ({ value: corpus.documents, unit: "documents ingested", source: "corpus" }),
  },
  {
    kind: "extract_metadata",
    title: "Metadata is lifted from the source, not guessed",
    body: "Title, publisher, filing date and document type come out of the document itself. A field the source does not carry stays empty rather than becoming a plausible invention.",
    event: "document.metadata_extracted",
  },
  {
    kind: "extract_entities",
    title: "Mentions resolve to canonical companies",
    body: "“Meta”, “Meta Platforms, Inc.” and a bare CIK are one company or the graph is worthless. Each mention keeps its offset in the source text, so a resolution can always be audited back to the sentence that produced it.",
    event: "document.entities_extracted",
    figure: ({ corpus }) => ({
      value: corpus.entity_mentions,
      unit: "resolved mentions",
      source: "corpus",
    }),
  },
  {
    kind: "chunk",
    title: "The document is cut into citable passages",
    body: "Roughly 250 words each. This is the unit every citation in every report points at — the reason a claim can be checked in one click instead of being traced through a whole filing.",
    event: "document.chunked",
    figure: ({ corpus }) => ({ value: corpus.chunks, unit: "citable chunks", source: "corpus" }),
  },
  {
    kind: "embed",
    title: "Each passage becomes a vector, in the same database",
    body: "384 dimensions, indexed with HNSW inside the one Postgres instance that already holds the rows, the full-text index, the graph, the event log and the job queue. There is no separate vector store to keep in sync.",
    event: "document.embedded",
    figure: () => ({ value: 384, unit: "dimensions per chunk", source: "static" }),
    wide: true,
  },
  {
    kind: "build_graph",
    title: "Edges carry their provenance or they are not written",
    body: "Companies, documents and relationships become nodes and edges. Every edge names the document it was derived from, which is what makes the graph auditable rather than merely queryable.",
    event: "document.graph_built",
    figure: ({ corpus }) => ({ value: corpus.graph_edges, unit: "graph edges", source: "corpus" }),
    wide: true,
  },
  {
    kind: "validate",
    title: "Retrievable and citable, or the job goes back on the queue",
    body: "The last stage checks the derived artifacts actually exist. Stages are idempotent on document, stage and pipeline version, so a retry is always safe and a failure is never silent — it lands in the dead-letter queue where you can see it.",
    event: "document.enriched",
    figure: ({ dead }) => ({ value: dead, unit: "jobs dead-lettered", source: "pipeline" }),
  },
]

export const STAGE_COUNT = STAGES.length

function StageFigure({
  figure,
  run,
  corpusLive,
}: {
  figure: Figure
  run: boolean
  corpusLive: boolean
}) {
  const shown = useCountUp(figure.value, run)
  const stale = figure.source === "corpus" && !corpusLive
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="text-3xl font-light tracking-[-0.02em] tabular-nums text-white">
        {fmt.format(shown)}
      </span>
      <span className={MICRO}>{figure.unit}</span>
      {stale && (
        <span className={`${MICRO} text-muted-foreground/80`}>
          snapshot · {shortDate(`${SNAPSHOT.taken}T00:00:00Z`)}
        </span>
      )}
    </div>
  )
}

function Rail({ active }: { active: number }) {
  return (
    <nav
      aria-label="Pipeline stages"
      className="sticky top-0 hidden h-screen shrink-0 flex-col justify-center pr-10 lg:flex"
    >
      <ol className="relative flex flex-col gap-6">
        <span aria-hidden className="absolute left-[5.5px] top-2 bottom-2 w-px bg-border" />
        <span
          aria-hidden
          className="absolute left-[5.5px] top-2 w-px bg-primary transition-[height] duration-500 ease-out"
          style={{ height: `calc((100% - 1rem) * ${active / (STAGES.length - 1)})` }}
        />
        {STAGES.map((stage, i) => {
          const done = i <= active
          return (
            <li key={stage.kind} className="relative flex items-center gap-3">
              <a
                href={`#stage-${i + 1}`}
                className="group flex items-center gap-3 outline-none"
                aria-current={i === active ? "step" : undefined}
              >
                <span
                  className={`size-3 shrink-0 rounded-full border transition-colors group-focus-visible:ring-2 group-focus-visible:ring-ring ${
                    i === active
                      ? "border-primary bg-primary"
                      : done
                        ? "border-primary/60 bg-primary/30"
                        : "border-border bg-background"
                  }`}
                />
                <span
                  className={`font-mono text-[10px] tracking-[0.14em] uppercase transition-colors ${
                    i === active ? "text-white" : "text-muted-foreground group-hover:text-white"
                  }`}
                >
                  {String(i + 1).padStart(2, "0")} {stage.kind.replace(/_/g, " ")}
                </span>
              </a>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function MobileRail({ active }: { active: number }) {
  const stage = STAGES[active]
  return (
    <div className="sticky top-[3.25rem] z-20 -mx-5 mb-10 border-b border-border bg-background/95 px-5 py-3 backdrop-blur-sm lg:hidden">
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-mono text-[11px] tracking-[0.14em] text-white uppercase">
          {stage.kind.replace(/_/g, " ")}
        </span>
        <span className={`${MICRO} tabular-nums`}>
          {String(active + 1).padStart(2, "0")} / {String(STAGES.length).padStart(2, "0")}
        </span>
      </div>
      <div className="mt-2 h-px w-full bg-border">
        <div
          className="h-px bg-primary transition-[width] duration-500 ease-out"
          style={{ width: `${((active + 1) / STAGES.length) * 100}%` }}
        />
      </div>
    </div>
  )
}

export function Descent() {
  const { active, register } = useActiveIndex(STAGES.length)
  const { corpus, live } = useCorpus()
  const { runs, dead } = usePipelineFacts()
  const facts: Facts = { corpus, dead }

  return (
    <div className="mx-auto flex w-full max-w-6xl gap-0 px-5 sm:px-8">
      <Rail active={active} />
      <div className="min-w-0 flex-1">
        <MobileRail active={active} />
        <ol>
          {STAGES.map((stage, i) => {
            const run = runs[stage.kind]
            const reached = i <= active
            return (
              <li
                key={stage.kind}
                id={`stage-${i + 1}`}
                ref={register(i)}
                className="border-t border-border py-16 first:border-t-0 first:pt-0 sm:py-24"
              >
                <div
                  className={
                    stage.wide
                      ? "flex flex-col gap-10"
                      : "flex flex-col gap-10 md:flex-row md:items-start md:justify-between"
                  }
                >
                  <div className={stage.wide ? "max-w-[46rem]" : "max-w-[34rem] flex-1"}>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[11px] tracking-[0.14em] text-primary tabular-nums">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className={MICRO}>{stage.kind.replace(/_/g, " ")}</span>
                    </div>
                    <h3 className="mt-4 text-2xl leading-[1.15] font-light tracking-[-0.02em] text-white sm:text-3xl">
                      {stage.title}
                    </h3>
                    <p className="mt-4 max-w-[42rem] leading-relaxed text-muted-foreground">
                      {stage.body}
                    </p>
                    <div className="mt-8 flex flex-col gap-2">
                      {stage.figure && (
                        <StageFigure figure={stage.figure(facts)} run={reached} corpusLive={live} />
                      )}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] tracking-[0.1em] text-muted-foreground/80">
                        <span>{stage.event}</span>
                        {run && run.ms !== null && (
                          <span className="tabular-nums">
                            {run.ms < 1000
                              ? `${Math.round(run.ms)} ms avg`
                              : `${(run.ms / 1000).toFixed(1)} s avg`}
                          </span>
                        )}
                        {run && run.runs > 0 && (
                          <span className="tabular-nums">{fmt.format(run.runs)} runs · 24h</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div
                    className={
                      stage.wide
                        ? "w-full max-w-[46rem] border-t border-border pt-10"
                        : "flex w-full shrink-0 justify-start md:w-[19rem] md:justify-end"
                    }
                  >
                    <StagePayload kind={stage.kind} />
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
