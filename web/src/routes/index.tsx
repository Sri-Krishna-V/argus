import type { ReactNode } from "react"
import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon, ArrowUpRightIcon } from "lucide-react"
import { SignalRidge } from "@/components/signal-ridge"
import { StarGlyph } from "@/components/star-glyph"
import { CitationGate } from "@/components/landing/citation-gate"
import { Descent, STAGE_COUNT } from "@/components/landing/descent"
import { EvidenceClose } from "@/components/landing/evidence-close"
import { SNAPSHOT_EVIDENCE, shortDate, useShowcase } from "@/lib/landing"
import { useDemoMode } from "@/lib/demo"

export const Route = createFileRoute("/")({
  component: Landing,
})

const GITHUB = "https://github.com/Sri-Krishna-V/argus"
const MICRO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"

function PrimaryAction({ children }: { children: ReactNode }) {
  return (
    <Link
      to="/app"
      className="group inline-flex items-center gap-2.5 rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-[0_10px_30px_-12px_rgba(232,165,127,0.55)] transition-colors hover:bg-primary/90"
    >
      {children}
      <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}

function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-5 py-3.5 sm:px-8">
        <a href="#top" className="flex items-center gap-2 text-white">
          <StarGlyph className="size-3.5 text-primary" />
          <span className="text-base font-light tracking-tight">Argus</span>
        </a>
        <nav className="flex items-center gap-6">
          <a
            href={GITHUB}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase transition-colors hover:text-white"
          >
            GitHub
            <ArrowUpRightIcon className="size-3" />
          </a>
          <Link
            to="/app"
            className="font-mono text-[11px] tracking-[0.14em] text-white uppercase transition-colors hover:text-primary"
          >
            Open the demo
          </Link>
        </nav>
      </div>
    </header>
  )
}

function FilingPlate() {
  const { showcase } = useShowcase()
  const citation = showcase?.citation ?? SNAPSHOT_EVIDENCE.citation

  return (
    <figure className="w-full max-w-[27rem] rounded-md border border-border bg-card/70 p-4 backdrop-blur-sm">
      <figcaption className="flex items-center justify-between gap-4">
        <span className={MICRO}>{citation.source === "sec_edgar" ? "SEC EDGAR" : citation.source}</span>
        <span className={`${MICRO} tabular-nums`}>filed {shortDate(citation.published_at)}</span>
      </figcaption>
      <p className="mt-3 font-mono text-[12px] leading-relaxed text-white/90">{citation.title}</p>
      {/* the filing's own words, faded out rather than faked with placeholder strokes */}
      <p className="mt-4 max-h-[5.5rem] overflow-hidden text-[13px] leading-[1.55] text-muted-foreground [mask-image:linear-gradient(to_bottom,black_40%,transparent_100%)]">
        {citation.excerpt.trim()}
      </p>
    </figure>
  )
}

function RailStub() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5" aria-hidden>
        <span className="size-2.5 rounded-full bg-primary" />
        {Array.from({ length: STAGE_COUNT - 1 }, (_, i) => (
          <span key={i} className="size-2.5 rounded-full border border-border" />
        ))}
      </div>
      <span className={`${MICRO} tabular-nums`}>
        01 / {String(STAGE_COUNT).padStart(2, "0")} parse
      </span>
    </div>
  )
}

function Hero() {
  const { demo } = useDemoMode()
  return (
    <section id="top" className="relative overflow-hidden border-b border-border">
      <SignalRidge className="absolute inset-0 h-full w-full" />
      <div className="absolute inset-0 bg-gradient-to-r from-background/85 via-background/30 to-transparent" />
      <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-12 px-5 pt-16 pb-20 sm:px-8 sm:pt-24 sm:pb-28">
        <FilingPlate />
        <div>
          <h1 className="max-w-[52rem] text-[clamp(2.25rem,6.2vw,4.5rem)] leading-[1.03] font-light tracking-[-0.035em] text-white">
            Every sentence resolves to a document chunk, or the run fails.
          </h1>
          <p className="mt-8 max-w-[44rem] text-lg leading-relaxed text-muted-foreground">
            Argus turns SEC filings and news into immutable documents — then into chunks,
            vectors, resolved entities and a graph where every edge names its source — and
            answers research questions with cited, confidence-scored investigations.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-4">
            <PrimaryAction>Open a live investigation</PrimaryAction>
            <a
              href={GITHUB}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 border-b border-border pb-1 text-sm text-white transition-colors hover:border-primary hover:text-primary"
            >
              Read the source
              <ArrowUpRightIcon className="size-3.5" />
            </a>
          </div>
          {demo && (
            <p className={`mt-8 ${MICRO}`}>
              Read-only demo · everything is readable without a key, every write needs one
            </p>
          )}
        </div>
        <div className="pt-4">
          <RailStub />
        </div>
      </div>
    </section>
  )
}

function DescentIntro() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 pt-20 pb-4 sm:px-8 sm:pt-28">
      <h2 className="max-w-[40rem] text-3xl leading-[1.1] font-light tracking-[-0.025em] text-white sm:text-4xl">
        One filing, seven stages, nothing lost on the way down
      </h2>
      <p className="mt-6 max-w-[44rem] leading-relaxed text-muted-foreground">
        Ingestion is a deterministic pipeline, not a script that runs once and hopes. Each stage
        is idempotent on the document it processes, so a retry costs nothing and a failure is
        visible instead of silent. The figures below are read from the running deployment.
      </p>
    </div>
  )
}

const REAL = [
  "The corpus — SEC EDGAR and RSS connectors, fetching real filings and news",
  "The seven-stage pipeline, the job outbox, retries and the dead-letter queue",
  "Hybrid retrieval: Postgres full-text and pgvector fused with reciprocal rank fusion",
  "Near-duplicate collapse, source ranking and stance classification",
  "The task DAG, the citation gate and every confidence score on the site",
]

const NOT_REAL = [
  "The language model. This deployment runs a deterministic canned runtime behind the same adapter boundary a real model would sit behind",
  "Investigation plans, stance rationales and report prose — scripted, and every report carries model=canned-demo",
  "Nothing else. There are no invented companies, filings, passages or numbers anywhere on this page",
]

function Limits() {
  return (
    <section id="limits" className="border-t border-border">
      <div className="mx-auto grid w-full max-w-6xl gap-12 px-5 py-20 sm:px-8 sm:py-24 lg:grid-cols-2 lg:gap-20">
        <div>
          <h2 className="text-2xl font-light tracking-[-0.02em] text-white">What is real</h2>
          <ul className="mt-6 flex flex-col gap-4">
            {REAL.map((item) => (
              <li key={item} className="flex gap-3 leading-relaxed text-muted-foreground">
                <StarGlyph className="mt-1.5 size-2 shrink-0 text-primary" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-2xl font-light tracking-[-0.02em] text-white">What is not</h2>
          <ul className="mt-6 flex flex-col gap-4">
            {NOT_REAL.map((item) => (
              <li key={item} className="flex gap-3 leading-relaxed text-muted-foreground">
                <StarGlyph className="mt-1.5 size-2 shrink-0 text-muted-foreground/50" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer id="site-footer" className="border-t border-border">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 py-14 sm:px-8 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-white">
            <StarGlyph className="size-3.5 text-primary" />
            <span className="text-base font-light tracking-tight">Argus</span>
          </div>
          <p className="mt-4 max-w-[34rem] text-sm leading-relaxed text-muted-foreground">
            An enterprise research operating system: knowledge infrastructure that AI consumes,
            not an investment adviser. Built by Sri Krishna V.
          </p>
        </div>
        <nav className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <Link to="/app" className={`${MICRO} transition-colors hover:text-white`}>
            Investigations
          </Link>
          <Link to="/app/search" className={`${MICRO} transition-colors hover:text-white`}>
            Search
          </Link>
          <Link to="/app/pipeline" className={`${MICRO} transition-colors hover:text-white`}>
            Pipeline
          </Link>
          <a
            href={GITHUB}
            target="_blank"
            rel="noreferrer"
            className={`${MICRO} inline-flex items-center gap-1.5 transition-colors hover:text-white`}
          >
            GitHub
            <ArrowUpRightIcon className="size-3" />
          </a>
        </nav>
      </div>
    </footer>
  )
}

function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />
      <main>
        <Hero />
        <DescentIntro />
        <Descent />
        <CitationGate />
        <EvidenceClose />
        <Limits />
      </main>
      <Footer />
    </div>
  )
}
