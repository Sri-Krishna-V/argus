import { Link, Outlet, useRouterState } from "@tanstack/react-router"

const NAV = [
  { to: "/", label: "Investigations" },
  { to: "/search", label: "Search" },
  { to: "/pipeline", label: "Pipeline" },
]

function StarGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 0 L14.2 9.8 L24 12 L14.2 14.2 L12 24 L9.8 14.2 L0 12 L9.8 9.8 Z" />
    </svg>
  )
}

export function AppShell() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const current = NAV.find((item) =>
    item.to === "/" ? pathname === "/" : pathname.startsWith(item.to),
  )

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border p-4">
        <div className="mb-8 flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <StarGlyph className="size-3.5 text-primary" />
            <span className="text-lg font-light tracking-tight text-white">Argus</span>
          </div>
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
              activeOptions={{ exact: item.to === "/" }}
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
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
