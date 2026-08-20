import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { api, ApiError } from "@/lib/api"
import { READ_ONLY_HINT, useDemoMode } from "@/lib/demo"
import type { Evidence, InvestigationDetail, Report } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfidenceMeter } from "@/components/confidence-meter"
import { ReportNarrative } from "@/components/report-narrative"
import { StatusDot } from "@/components/status-dot"
import { TaskDag } from "@/components/task-dag"
import { ActivityTimeline } from "@/components/activity-timeline"
import { Link } from "@tanstack/react-router"

const GLASS_CARD = "border border-border bg-white/[0.03]"
const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"

export const Route = createFileRoute("/app/investigations/$investigationId")({
  component: InvestigationDetailPage,
})

const STANCE_LABELS = { supporting: "Supporting", contradicting: "Contradicting", unknown: "Unknown" } as const

function InvestigationDetailPage() {
  const { investigationId } = Route.useParams()
  const queryClient = useQueryClient()
  const { writesLocked: demo } = useDemoMode()

  const invQuery = useQuery({
    queryKey: ["investigation", investigationId],
    queryFn: () => api.get<InvestigationDetail>(`/api/investigations/${investigationId}`),
  })

  const reportQuery = useQuery({
    queryKey: ["report", investigationId],
    queryFn: () => api.get<Report>(`/api/investigations/${investigationId}/report`),
    retry: false,
    enabled: invQuery.data?.status === "complete",
  })

  const evidenceQuery = useQuery({
    queryKey: ["evidence", investigationId],
    queryFn: () => api.get<Evidence[]>(`/api/investigations/${investigationId}/evidence`),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["investigation", investigationId] })
    queryClient.invalidateQueries({ queryKey: ["report", investigationId] })
    queryClient.invalidateQueries({ queryKey: ["evidence", investigationId] })
    queryClient.invalidateQueries({ queryKey: ["events", investigationId] })
  }

  const refresh = useMutation({
    mutationFn: () => api.post(`/api/investigations/${investigationId}/refresh`),
    onSuccess: () => {
      toast.success("Investigation refreshed")
      invalidateAll()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const replay = useMutation({
    mutationFn: () => api.post(`/api/investigations/${investigationId}/replay`),
    onSuccess: (result: any) =>
      toast(result.match ? "Replay matches recorded evidence" : "Replay diverged from recorded evidence"),
    onError: (err: Error) => toast.error(err.message),
  })

  if (invQuery.isPending) return <Skeleton className="h-64 w-full" />
  if (invQuery.error) return <p className="text-destructive">{invQuery.error.message}</p>
  const inv = invQuery.data!

  const byStance = { supporting: [] as Evidence[], contradicting: [] as Evidence[], unknown: [] as Evidence[] }
  for (const e of evidenceQuery.data ?? []) byStance[e.stance].push(e)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-white">{inv.question}</h1>
          <p className="mt-1 flex items-center gap-2">
            <StatusDot status={inv.status} />
            <span className={EYEBROW}>
              v{inv.version}
              {inv.new_evidence_available && " · new evidence available"}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="text-muted-foreground"
            onClick={() => replay.mutate()}
            disabled={replay.isPending || demo}
            title={demo ? READ_ONLY_HINT : undefined}
          >
            Replay
          </Button>
          <Button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || demo}
            title={demo ? READ_ONLY_HINT : undefined}
          >
            {refresh.isPending ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <Card className={GLASS_CARD}>
        <CardHeader><CardTitle className={EYEBROW}>Confidence</CardTitle></CardHeader>
        <CardContent><ConfidenceMeter inv={inv} /></CardContent>
      </Card>

      {inv.hypotheses.length > 0 && (
        <Card className={GLASS_CARD}>
          <CardHeader><CardTitle className={EYEBROW}>Hypotheses</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-2">
            {inv.hypotheses.map((h) => (
              <p key={h.id} className="text-sm">{h.statement}</p>
            ))}
          </CardContent>
        </Card>
      )}

      <TaskDag investigationId={investigationId} />

      {reportQuery.data && (
        <Card className={GLASS_CARD}>
          <CardHeader><CardTitle className={EYEBROW}>Report</CardTitle></CardHeader>
          <CardContent>
            <ReportNarrative narrative={reportQuery.data.narrative} citations={reportQuery.data.citations} />
          </CardContent>
        </Card>
      )}
      {reportQuery.error instanceof ApiError && reportQuery.error.status !== 404 && (
        <p className="text-destructive">{reportQuery.error.message}</p>
      )}

      <Card className={GLASS_CARD}>
        <CardHeader><CardTitle className={EYEBROW}>Evidence</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {(["supporting", "contradicting", "unknown"] as const).map((stance) => (
            <div key={stance} className="flex flex-col gap-2">
              <h3 className={EYEBROW}>{STANCE_LABELS[stance]} ({byStance[stance].length})</h3>
              {byStance[stance].map((e) => (
                <div key={e.chunk_id} className="rounded-md border border-border p-3 text-sm">
                  <p>{e.excerpt}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{e.rationale}</p>
                </div>
              ))}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className={GLASS_CARD}>
        <CardHeader><CardTitle className={EYEBROW}>Activity</CardTitle></CardHeader>
        <CardContent>
          <ActivityTimeline investigationId={investigationId} status={inv.status} />
        </CardContent>
      </Card>

      {inv.links.length > 0 && (
        <Card className={GLASS_CARD}>
          <CardHeader><CardTitle className={EYEBROW}>Linked investigations</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-1">
            {inv.links.map((link) => (
              <Link
                key={link.investigation_id}
                to="/app/investigations/$investigationId"
                params={{ investigationId: link.investigation_id }}
                className="text-sm hover:text-primary hover:underline"
              >
                {link.link_type}: {link.question}
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
