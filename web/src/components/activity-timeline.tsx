import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { InvestigationEvent } from "@/lib/types"
import { Skeleton } from "@/components/ui/skeleton"

const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"

// ponytail: reuses status-dot.tsx's semantic-class approach (destructive /
// muted-foreground) rather than inventing a new "green" token this design
// system doesn't have.
function markerClass(eventType: string): string {
  if (eventType.endsWith(".failed")) return "bg-destructive"
  if (eventType === "investigation.completed" || eventType === "investigation.refreshed") return "bg-muted-foreground"
  return "bg-muted-foreground/40"
}

function summarize(e: InvestigationEvent): string {
  const p = e.payload as Record<string, any>
  switch (e.event_type) {
    case "investigation.created":
      return String(p.question ?? "Investigation created")
    case "agent.plan": {
      const queries = p.plan?.queries
      return Array.isArray(queries) ? `Plan generated · ${queries.length} queries` : "Plan generated"
    }
    case "investigation.compiled": {
      const tasks = Array.isArray(p.tasks) ? p.tasks.length : 0
      return `DAG compiled · ${tasks} tasks`
    }
    case "evidence.collected": {
      const chunkCount = Array.isArray(p.chunk_ids) ? p.chunk_ids.length : 0
      return `${p.query ?? "Evidence query"} · ${chunkCount} chunks`
    }
    case "agent.draft":
      return p.record?.model ? `Report drafted · ${p.record.model}` : "Report drafted"
    case "investigation.completed":
    case "investigation.refreshed": {
      const conf = typeof p.confidence === "number" ? p.confidence.toFixed(2) : "—"
      return `Confidence ${conf} · v${p.version ?? "?"}`
    }
    case "investigation.failed":
      return String(p.error ?? "Investigation failed")
    case "task.failed":
      return String(p.error ?? "Task failed")
    default:
      return e.event_type
  }
}

export function ActivityTimeline({ investigationId, status }: { investigationId: string; status: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ["events", investigationId],
    queryFn: () => api.get<InvestigationEvent[]>(`/api/investigations/${investigationId}/events?limit=200`),
    refetchInterval: () => (status === "running" ? 5_000 : false),
  })

  if (isPending) return <Skeleton className="h-32 w-full" />
  if (error) return <p className="text-destructive">{(error as Error).message}</p>
  if (data!.length === 0) return <p className="text-sm text-muted-foreground">No activity yet</p>

  return (
    <div className="flex flex-col gap-3">
      {data!.map((e) => (
        <div key={e.id} className="flex gap-3">
          <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${markerClass(e.event_type)}`} />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm">{summarize(e)}</p>
              <span className={`shrink-0 ${EYEBROW}`}>{new Date(e.created_at).toLocaleString()}</span>
            </div>
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">payload</summary>
              <pre className="mt-1 max-h-64 overflow-auto rounded-md border border-border bg-white/[0.03] p-2 text-xs">
                {JSON.stringify(e.payload, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      ))}
    </div>
  )
}
