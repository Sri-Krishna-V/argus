import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { InvestigationTask } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StatusDot } from "@/components/status-dot"

const GLASS_CARD = "border border-border bg-white/[0.03]"
const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"

const ACTIVE_STATUSES = new Set(["pending", "running"])

// ponytail: recursive depth-per-task instead of a graph library — this is a
// tree of ~dozens of nodes rendered as columns, not a real graph layout
// problem. `visiting` guards a cycle (shouldn't happen; DAG) from infinite
// recursion — falls back to depth 0 for the offending node.
function computeDepths(tasks: InvestigationTask[]): Map<string, number> {
  const byId = new Map(tasks.map((t) => [t.id, t]))
  const depths = new Map<string, number>()

  function depthOf(id: string, visiting: Set<string>): number {
    if (depths.has(id)) return depths.get(id)!
    if (visiting.has(id)) return 0
    const task = byId.get(id)
    const deps = task?.depends_on.filter((dep) => byId.has(dep)) ?? []
    if (deps.length === 0) {
      depths.set(id, 0)
      return 0
    }
    visiting.add(id)
    const depth = 1 + Math.max(...deps.map((dep) => depthOf(dep, visiting)))
    visiting.delete(id)
    depths.set(id, depth)
    return depth
  }

  for (const t of tasks) depthOf(t.id, new Set())
  return depths
}

export function TaskDag({ investigationId }: { investigationId: string }) {
  const { data, error } = useQuery({
    queryKey: ["tasks", investigationId],
    queryFn: () =>
      api.get<{ tasks: InvestigationTask[] }>(`/api/investigations/${investigationId}/tasks`),
    retry: false,
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? []
      return tasks.some((t) => ACTIVE_STATUSES.has(t.status)) ? 5_000 : false
    },
  })

  if (error || !data || data.tasks.length === 0) return null

  const depths = computeDepths(data.tasks)
  const columns = new Map<number, InvestigationTask[]>()
  for (const t of data.tasks) {
    const d = depths.get(t.id)!
    if (!columns.has(d)) columns.set(d, [])
    columns.get(d)!.push(t)
  }
  const sortedDepths = [...columns.keys()].sort((a, b) => a - b)

  return (
    <Card className={GLASS_CARD}>
      <CardHeader>
        <CardTitle className={EYEBROW}>Task graph</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-stretch gap-4 overflow-x-auto pb-2">
          {sortedDepths.map((depth, i) => (
            <div key={depth} className="flex items-stretch gap-4">
              {i > 0 && <div className="w-px shrink-0 bg-border" />}
              <div className="flex w-56 shrink-0 flex-col gap-2">
                {columns.get(depth)!.map((t) => (
                  <div key={t.id} className="rounded-md border border-border bg-white/[0.03] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className={EYEBROW}>{t.task_type}</span>
                      <StatusDot status={t.status} />
                    </div>
                    <p className="mt-1.5 line-clamp-3 text-sm">{t.objective}</p>
                    {t.specialist && (
                      <p className="mt-1 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                        {t.specialist}
                      </p>
                    )}
                    {t.error && <p className="mt-1 text-xs text-destructive">{t.error}</p>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
