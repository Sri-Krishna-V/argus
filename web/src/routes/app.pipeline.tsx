import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { api } from "@/lib/api"
import { READ_ONLY_HINT, useDemoMode } from "@/lib/demo"
import type { Job, PipelineMetrics } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/app/pipeline")({
  component: PipelinePage,
})

const GLASS_CARD = "border border-border bg-white/[0.03]"
const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"
const STEEL = "#8DA0BA"
const CLAY = "#C97B6E"
const REFETCH_MS = 15_000

function stageChartData(metrics: PipelineMetrics) {
  const byStage = new Map<string, { stage: string; success: number; failure: number }>()
  for (const s of metrics.stages_24h) {
    const row = byStage.get(s.stage) ?? { stage: s.stage, success: 0, failure: 0 }
    row[s.status === "success" ? "success" : "failure"] = s.runs
    byStage.set(s.stage, row)
  }
  return [...byStage.values()]
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <Card className={GLASS_CARD}>
      <CardHeader className="pb-2">
        <CardTitle className={EYEBROW}>{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-3xl font-light text-white">{value}</CardContent>
    </Card>
  )
}

function PipelinePage() {
  const queryClient = useQueryClient()
  const { writesLocked: demo } = useDemoMode()

  const metricsQuery = useQuery({
    queryKey: ["pipeline-metrics"],
    queryFn: () => api.get<PipelineMetrics>("/api/metrics/pipeline"),
    refetchInterval: REFETCH_MS,
  })

  const deadQuery = useQuery({
    queryKey: ["jobs", "dead"],
    queryFn: () => api.get<Job[]>("/api/jobs?status=dead"),
    refetchInterval: REFETCH_MS,
  })

  const retry = useMutation({
    mutationFn: (jobId: number) => api.post(`/api/jobs/${jobId}/retry`),
    onSuccess: () => {
      toast.success("Job requeued")
      queryClient.invalidateQueries({ queryKey: ["jobs", "dead"] })
      queryClient.invalidateQueries({ queryKey: ["pipeline-metrics"] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  if (metricsQuery.isPending) return <Skeleton className="h-64 w-full" />
  if (metricsQuery.error) return <p className="text-destructive">{metricsQuery.error.message}</p>
  const metrics = metricsQuery.data!

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between">
        <div>
          <span className={EYEBROW}>Pipeline</span>
          <h1 className="mt-1 text-3xl font-light tracking-tight text-white">Ingestion &amp; queues</h1>
        </div>
        {metrics.oldest_pending_seconds !== null && (
          <span className={EYEBROW}>oldest pending: {Math.round(metrics.oldest_pending_seconds)}s</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {Object.entries(metrics.queue_depth).map(([status, count]) => (
          <StatTile key={status} label={status} value={count} />
        ))}
        <StatTile label="documents" value={metrics.document_count} />
        <StatTile label="retries (24h)" value={metrics.retries_24h} />
      </div>

      <Card className={GLASS_CARD}>
        <CardHeader>
          <CardTitle className={EYEBROW}>Runs by stage (24h)</CardTitle>
        </CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stageChartData(metrics)}>
              <CartesianGrid stroke="rgba(148,163,184,0.10)" vertical={false} />
              <XAxis
                dataKey="stage"
                tick={{ fill: "#8DA0BA", fontSize: 11, fontFamily: "var(--font-mono)" }}
                axisLine={{ stroke: "rgba(148,163,184,0.14)" }}
                tickLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: "#8DA0BA", fontSize: 11, fontFamily: "var(--font-mono)" }}
                axisLine={{ stroke: "rgba(148,163,184,0.14)" }}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "rgba(148,163,184,0.05)" }}
                contentStyle={{
                  background: "#0C1017",
                  border: "1px solid rgba(148,163,184,0.14)",
                  borderRadius: 8,
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                }}
                labelStyle={{ color: "#8DA0BA" }}
                itemStyle={{ color: "#EEF2F8" }}
              />
              <Bar dataKey="success" stackId="a" fill={STEEL} />
              <Bar dataKey="failure" stackId="a" fill={CLAY} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card className={GLASS_CARD}>
        <CardHeader>
          <CardTitle className={EYEBROW}>Dead-letter jobs ({deadQuery.data?.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className={EYEBROW}>Id</TableHead>
                <TableHead className={EYEBROW}>Type</TableHead>
                <TableHead className={EYEBROW}>Attempts</TableHead>
                <TableHead className={EYEBROW}>Error</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(deadQuery.data ?? []).map((job) => (
                <TableRow key={job.id} className="border-border">
                  <TableCell className="font-mono text-xs text-muted-foreground">{job.id}</TableCell>
                  <TableCell className="text-sm">{job.job_type}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {job.attempts}/{job.max_attempts}
                  </TableCell>
                  <TableCell className="max-w-96 truncate text-xs text-muted-foreground">
                    {job.last_error}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-muted-foreground"
                      onClick={() => retry.mutate(job.id)}
                      disabled={retry.isPending || demo}
                      title={demo ? READ_ONLY_HINT : undefined}
                    >
                      Retry
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
