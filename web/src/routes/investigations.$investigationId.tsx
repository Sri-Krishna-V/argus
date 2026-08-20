import { createFileRoute, redirect } from "@tanstack/react-router"

// Legacy URL — shared demo links must keep working after the app moved under /app.
export const Route = createFileRoute("/investigations/$investigationId")({
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/app/investigations/$investigationId", params })
  },
})
