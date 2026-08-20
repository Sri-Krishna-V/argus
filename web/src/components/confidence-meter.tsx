import type { Investigation } from "@/lib/types"
import { SignalRidge } from "@/components/signal-ridge"

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
    <div className="flex flex-col gap-4">
      <div className="relative h-16 overflow-hidden rounded-md">
        <SignalRidge className="absolute inset-0 h-full w-full" amplitude={inv.confidence ?? 0} />
        <div className="absolute inset-0 flex items-center justify-end pr-4">
          <span className="text-2xl font-light text-white">
            {inv.confidence !== null ? `${Math.round(inv.confidence * 100)}%` : "—"}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-xs">
        {Object.entries(components).map(([key, component]) => (
          <div key={key} className="flex justify-between gap-3">
            <span className="text-muted-foreground">{LABELS[key] ?? key}</span>
            <span className="tabular-nums text-white">
              {Math.round(component.value * 100)}%
              <span className="text-muted-foreground"> ×{component.weight}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
