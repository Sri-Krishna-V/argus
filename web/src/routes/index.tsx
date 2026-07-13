import { createFileRoute, Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Investigation } from "@/lib/types"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { NewInvestigationDialog } from "@/components/new-investigation-dialog"
import { StatusDot } from "@/components/status-dot"
import { SignalRidge } from "@/components/signal-ridge"

export const Route = createFileRoute("/")({
  component: InvestigationsPage,
})

function InvestigationsPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.get<Investigation[]>("/api/investigations"),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="relative h-44 overflow-hidden rounded-lg border border-border bg-card">
        <SignalRidge className="absolute inset-0 h-full w-full" />
        <div className="absolute right-4 top-4">
          <NewInvestigationDialog />
        </div>
        <div className="absolute bottom-4 left-5 flex flex-col gap-1">
          <span className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
            Investigations
          </span>
          <h1 className="text-4xl font-light tracking-tight text-white">Signal out of noise</h1>
          {data && (
            <span className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
              {data.length} tracked
            </span>
          )}
        </div>
      </div>

      {isPending && <Skeleton className="h-40 w-full" />}
      {error && <p className="text-destructive">{error.message}</p>}
      {data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                Question
              </TableHead>
              <TableHead className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                Status
              </TableHead>
              <TableHead className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                Confidence
              </TableHead>
              <TableHead className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                Created
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((inv) => (
              <TableRow key={inv.id} className="border-border">
                <TableCell>
                  <Link
                    to="/investigations/$investigationId"
                    params={{ investigationId: inv.id }}
                    className="text-white hover:text-primary"
                  >
                    {inv.question}
                  </Link>
                  {inv.new_evidence_available && (
                    <span className="ml-2 font-mono text-xs text-muted-foreground">· stale</span>
                  )}
                </TableCell>
                <TableCell>
                  <StatusDot status={inv.status} />
                </TableCell>
                <TableCell>
                  {inv.confidence !== null ? (
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted-foreground/10">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${Math.round(inv.confidence * 100)}%` }}
                      />
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {new Date(inv.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
