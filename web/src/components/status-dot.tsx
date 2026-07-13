const EMBER_STATUSES = new Set(["running", "pending", "refreshing"])
const STEEL_STATUSES = new Set(["complete", "completed", "success"])
const CLAY_STATUSES = new Set(["failed", "dead", "error"])

function dotClasses(status: string): string {
  const s = status.toLowerCase()
  if (EMBER_STATUSES.has(s)) return "bg-primary animate-pulse"
  if (CLAY_STATUSES.has(s)) return "bg-destructive"
  if (STEEL_STATUSES.has(s)) return "bg-muted-foreground"
  return "bg-muted-foreground" // fallback: steel
}

export function StatusDot({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`size-1.5 shrink-0 rounded-full ${dotClasses(status)}`} />
      <span className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
        {status}
      </span>
    </span>
  )
}
