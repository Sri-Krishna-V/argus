import { createFileRoute, redirect } from "@tanstack/react-router"

// Legacy URL — the app moved under /app when the landing page took `/`.
export const Route = createFileRoute("/search")({
  beforeLoad: () => {
    throw redirect({ to: "/app/search" })
  },
})
