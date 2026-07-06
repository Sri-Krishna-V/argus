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
