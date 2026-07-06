import { createFileRoute, Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Investigation } from "@/lib/types"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { NewInvestigationDialog } from "@/components/new-investigation-dialog"

export const Route = createFileRoute("/")({
  component: InvestigationsPage,
})

function InvestigationsPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.get<Investigation[]>("/api/investigations"),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Investigations</h1>
        <NewInvestigationDialog />
      </div>
      {isPending && <Skeleton className="h-40 w-full" />}
      {error && <p className="text-destructive">{error.message}</p>}
      {data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Question</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((inv) => {
              // ponytail: Task 8 hasn't added this route yet; widen to `string`
              // (see new-investigation-dialog.tsx) so typed-router doesn't reject it.
              const path: string = `/investigations/${inv.id}`
              return (
                <TableRow key={inv.id}>
                  <TableCell>
                    <Link to={path} className="hover:underline">
                      {inv.question}
                    </Link>
                    {inv.new_evidence_available && (
                      <Badge variant="outline" className="ml-2">stale</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={inv.status === "complete" ? "default" : "secondary"}>
                      {inv.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {inv.confidence !== null ? (
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-primary"
                          style={{ width: `${Math.round(inv.confidence * 100)}%` }}
                        />
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(inv.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
