import { Link, Outlet } from "@tanstack/react-router"
import { toggleTheme } from "@/lib/theme"

const NAV = [
  { to: "/", label: "Investigations" },
  { to: "/search", label: "Search" },
  { to: "/pipeline", label: "Pipeline" },
]

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-56 shrink-0 border-r border-border p-4">
        <div className="mb-6 text-lg font-bold tracking-wide text-primary">ARGUS</div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground [&.active]:bg-accent [&.active]:text-foreground"
              activeOptions={{ exact: item.to === "/" }}
              activeProps={{ className: "active" }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-end border-b border-border px-6 py-3">
          <button
            onClick={toggleTheme}
            className="rounded-md border border-border px-3 py-1 text-sm text-muted-foreground hover:text-foreground"
          >
            Toggle theme
          </button>
        </header>
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
