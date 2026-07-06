import * as React from "react"
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
