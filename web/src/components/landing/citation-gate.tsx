const MICRO = "font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"

/* Synthetic claims, labelled as such below. The point is the rule, not the sentences:
   the third one is the plausible, forward-looking, entirely unsourced claim that a
   language model produces most readily — and it is exactly what the gate drops. */
const CLAIMS = [
  { text: "Revenue concentration in Greater China increased year over year.", ref: "chunk:7f2a41c8" },
  { text: "Capital expenditure guidance was raised for the second half.", ref: "chunk:1c94b6de" },
  { text: "Management expects margins to recover next quarter.", ref: null },
  { text: "Supply-chain risk is concentrated in two named suppliers.", ref: "chunk:b8e0f3a7" },
]

export function CitationGate() {
  return (
    <section id="gate" className="border-t border-border bg-white/[0.015]">
      <div className="mx-auto grid w-full max-w-6xl gap-14 px-5 py-20 sm:px-8 sm:py-28 lg:grid-cols-[minmax(0,26rem)_1fr] lg:gap-20">
        <div>
          <h2 className="text-3xl leading-[1.1] font-light tracking-[-0.025em] text-white sm:text-4xl">
            A claim without a source never reaches the report
          </h2>
          <p className="mt-6 leading-relaxed text-muted-foreground">
            At question time, Postgres full-text search and pgvector each return candidates and
            reciprocal rank fusion merges them. Near-duplicates collapse, sources are ranked,
            and a stance classifier marks what supports the question and what contradicts it.
          </p>
          <p className="mt-4 leading-relaxed text-muted-foreground">
            Then the gate: every claim the drafter writes must carry a chunk reference that
            resolves. The ones that do not are rejected before the report exists — not flagged,
            not footnoted, rejected.
          </p>
          <p className={`mt-8 ${MICRO}`}>illustration · synthetic claims</p>
        </div>

        <ul className="flex flex-col">
          {CLAIMS.map((claim) => (
            <li
              key={claim.text}
              className="flex flex-col gap-3 border-t border-border py-6 first:border-t-0 first:pt-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-8"
            >
              <p
                className={`max-w-[46ch] leading-relaxed ${
                  claim.ref ? "text-foreground/90" : "text-muted-foreground line-through decoration-destructive/70"
                }`}
              >
                {claim.text}
              </p>
              <div className="flex shrink-0 items-center gap-3 font-mono text-[11px] tracking-[0.1em]">
                {claim.ref ? (
                  <>
                    <span className="text-muted-foreground">{claim.ref}</span>
                    <span className="text-primary">cited</span>
                  </>
                ) : (
                  <>
                    <span className="text-muted-foreground/80">no source</span>
                    <span className="text-destructive">rejected</span>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
