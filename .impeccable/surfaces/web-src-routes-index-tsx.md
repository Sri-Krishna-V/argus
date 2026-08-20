---
version: 1
slug: "web-src-routes-index-tsx"
primary_target: "web/src/routes/index.tsx"
related_targets: ["web/src/components/landing/descent.tsx","web/src/components/landing/evidence-close.tsx","web/src/components/landing/citation-gate.tsx","web/src/components/landing/stage-payload.tsx","web/src/lib/landing.ts"]
---

Scope: the public landing page at `/`. Visitor mode: Persuade.

Audience: a technical evaluator arriving cold at argusops.vercel.app — engineer, architect
or hiring manager, minutes not hours, sceptical because every AI research tool looks alike
from outside. The page is Argus-as-product; Sri Krishna V is credited in the footer, never
the pitch. No hiring language, no availability claim.

Action: open a live investigation (`/app`). Secondary and only contact channel: the public
GitHub repo. No email, no form.

Proof: live figures from `/api/metrics/corpus` and `/api/metrics/pipeline`; a real cited
passage from a completed investigation with its filing title, date, chunk id and sec.gov
link; the computed confidence breakdown with its five weights. The citation-gate section is
a labelled illustration with synthetic claims — the only invented content on the page.

Direction: Provenance Descent (concept seed d5008547). The scroll is the pipeline: one real
filing enters at the top and lands seven stages later as a quotable passage. A persistent
stage rail tracks the descent (sticky column on desktop, sticky bar under the header on
mobile). Memorable moment: the closing passage — real filing text, resolvable citation,
computed score — after seven stages of watching provenance survive.

Constraints: Radiant world inherited unchanged (ADR-0013, dark only). SPA is a pure API
consumer. CSP allows no external assets, so all imagery is drawn in-page as SVG/canvas.
Stage runs come from a rolling 24h window and legitimately read zero on an idle deployment;
stage identity is static truth, throughput is the live layer.

Open: the snapshot fallback figures are baked constants and need refreshing whenever the
corpus materially changes. Passage selection is heuristic (filing boilerplate rejected, then
management voice and substance rewarded) — it picks from the three newest scored
investigations and will need revisiting if the corpus grows a different shape.
