# ADR-0013: React SPA dashboard

## Status

Accepted

## Context

Phase 7 chose Jinja2 + htmx for the dashboard specifically to avoid a build
pipeline (see the Phase 7 plan). That held while the UI was a thin,
read-mostly wrapper over the JSON API. Reaching an enterprise-standard bar —
sortable/filterable tables, real-time-feeling updates, charts, a componentized
design system — outgrows what server-rendered partials can deliver without
turning into an ad-hoc JS framework of our own.

## Decision

Replace the Jinja2/htmx dashboard with a React SPA (`web/`): React 19 +
TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Router + Query,
Recharts. It is built at Docker build time (`vite build` → `web/dist`) and
served as static files by the existing FastAPI app — Node is a build-stage
dependency only, never present in the running container or its runtime image
layer.

`src/argus/ui/` (templates, htmx views, vendored htmx.js) is deleted outright;
there is no fallback server-rendered UI.

The dashboard commits to a single dark visual system ("Radiant" — a
dense-vertical-stroke signal-ridge motif over an ember/steel palette, detailed
in the dashboard-spa plan's Revision 2) rather than a light/dark toggle; this
is a design decision, not a technical constraint of the SPA architecture.

## Consequences

- Node is now a build-time requirement (`make web`, or the Dockerfile's
  `web-build` stage). Contributors touching only the Python backend don't
  need it — the API and CLI plans are unaffected.
- The dashboard is a pure API consumer: any data it needs must exist as a
  JSON endpoint. Three additive endpoints were introduced for this
  (`report.citations`, `investigation.hypotheses`/`links`,
  `GET/POST /api/jobs`) — no existing endpoint's shape changed.
- The citation URL scheme guard (only `http(s)` becomes a link) moved from
  the Jinja view into the API response, since the frontend has no unit-test
  framework in v1 to verify client-side sanitization — the guard is verified
  by pytest instead, at the source of truth.
- `argus.ui` is removed from the import-linter layers contract
  (`pyproject.toml`) — the layer no longer exists.
