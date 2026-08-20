import { Outlet, createRootRoute } from "@tanstack/react-router"

// The landing page (routes/index.tsx) renders outside the app shell, so the root
// route stays bare: `app.tsx` owns the AppShell + AuthGate chrome for /app/*.
export const Route = createRootRoute({
  component: Outlet,
})
