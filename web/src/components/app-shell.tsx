import { Link, Outlet, useRouterState } from "@tanstack/react-router"
import { StarGlyph } from "@/components/star-glyph"
import { AuthGate } from "@/components/auth-gate"
import { useDemoMode } from "@/lib/demo"

const NAV = [
  { to: "/app", label: "Investigations" },
  { to: "/app/search", label: "Search" },
  { to: "/app/pipeline", label: "Pipeline" },
]

export function AppShell() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { demo } = useDemoMode()
  const current = NAV.find((item) =>
    item.to === "/app" ? pathname.replace(/\/$/, "") === "/app" : pathname.startsWith(item.to),
  )

  return (
    <AuthGate>
      <div className="flex min-h-screen bg-background text-foreground">
        <aside className="flex w-56 shrink-0 flex-col border-r border-border p-4">
          <div className="mb-8 flex flex-col gap-1">
            <Link to="/" className="flex items-center gap-2 text-white hover:text-primary">
              <StarGlyph className="size-3.5 text-primary" />
              <span className="text-lg font-light tracking-tight">Argus</span>
            </Link>
            <span className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
              Research OS
            </span>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="group flex items-center gap-2 rounded-md px-3 py-2 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase hover:text-white [&.active]:text-white"
                activeOptions={{ exact: item.to === "/app" }}
                activeProps={{ className: "active" }}
              >
                <StarGlyph className="size-2 shrink-0 text-primary opacity-0 group-[.active]:opacity-100" />
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <div className="flex-1">
          <header className="flex items-center border-b border-border px-6 py-3">
            <span className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
              {current?.label ?? ""}
            </span>
          </header>
          {demo && (
            <div className="border-b border-border bg-primary/[0.06] px-6 py-2">
              <span className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                Demo data · read-only — writes require an API key
              </span>
            </div>
          )}
          <main className="p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </AuthGate>
  )
}
