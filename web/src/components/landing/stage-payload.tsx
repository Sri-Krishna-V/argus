/* The payload as it descends: seven representations of the same document, drawn in the
   Radiant grammar — steel hairlines on the void, ember for whatever the stage just
   produced. Deliberately not seven copies of one diagram: the shape changes because the
   artifact changes. */

const LINES = [86, 64, 78, 52, 71, 45, 68] // text hairline widths, fixed so renders are stable

function Plate({ x = 8, y = 14, w = 104, h = 104 }: { x?: number; y?: number; w?: number; h?: number }) {
  return (
    <rect
      x={x}
      y={y}
      width={w}
      height={h}
      rx="2"
      className="fill-white/[0.02] stroke-border"
      strokeWidth="1"
    />
  )
}

function TextLines({ x = 18, y = 28, gap = 12, only = LINES.length }: { x?: number; y?: number; gap?: number; only?: number }) {
  return (
    <g className="stroke-muted-foreground/50" strokeWidth="1.5" strokeLinecap="round">
      {LINES.slice(0, only).map((w, i) => (
        <line key={i} x1={x} y1={y + i * gap} x2={x + w * 0.9} y2={y + i * gap} />
      ))}
    </g>
  )
}

const svgProps = {
  viewBox: "0 0 240 132",
  className: "h-auto w-full overflow-visible",
  "aria-hidden": true as const,
}

function Parse() {
  return (
    <svg {...svgProps}>
      <Plate />
      <TextLines />
      <g className="stroke-primary" strokeWidth="1.5" strokeLinecap="round">
        <line x1="130" y1="52" x2="212" y2="52" />
        <line x1="130" y1="60" x2="188" y2="60" />
      </g>
      <text x="130" y="42" className="fill-muted-foreground font-mono text-[7px] uppercase tracking-[0.18em]">
        sha256
      </text>
      <text x="130" y="80" className="fill-muted-foreground/70 font-mono text-[7px] uppercase tracking-[0.18em]">
        raw store
      </text>
      <line x1="112" y1="66" x2="130" y2="66" className="stroke-border" strokeWidth="1" />
    </svg>
  )
}

function Metadata() {
  const fields = ["title", "publisher", "filed", "doc type"]
  return (
    <svg {...svgProps}>
      <Plate />
      <TextLines only={4} />
      {fields.map((field, i) => {
        const y = 30 + i * 22
        return (
          <g key={field}>
            <path d={`M112 66 C 126 66, 126 ${y}, 140 ${y}`} className="stroke-border" strokeWidth="1" fill="none" />
            <line x1="140" y1={y} x2="150" y2={y} className="stroke-primary" strokeWidth="1.5" strokeLinecap="round" />
            <text x="156" y={y + 3} className="fill-muted-foreground font-mono text-[7.5px] uppercase tracking-[0.14em]">
              {field}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function Entities() {
  const spans = [
    { y: 40, x: 18, w: 46 },
    { y: 64, x: 30, w: 38 },
    { y: 88, x: 18, w: 54 },
  ]
  return (
    <svg {...svgProps}>
      <Plate />
      <TextLines gap={12} />
      {spans.map((s, i) => (
        <g key={i}>
          <line x1={s.x} y1={s.y + 4} x2={s.x + s.w} y2={s.y + 4} className="stroke-primary" strokeWidth="2" strokeLinecap="round" />
          <path
            d={`M${s.x + s.w} ${s.y + 4} C ${s.x + s.w + 24} ${s.y + 4}, 140 ${44 + i * 24}, 158 ${44 + i * 24}`}
            className="stroke-border"
            strokeWidth="1"
            fill="none"
          />
          <circle cx="164" cy={44 + i * 24} r="3.5" className="fill-primary/20 stroke-primary" strokeWidth="1" />
          <line x1="172" y1={44 + i * 24} x2="212" y2={44 + i * 24} className="stroke-muted-foreground/40" strokeWidth="1.5" strokeLinecap="round" />
        </g>
      ))}
    </svg>
  )
}

function Chunks() {
  const bands = [0, 1, 2, 3, 4]
  return (
    <svg {...svgProps}>
      {bands.map((i) => (
        <g key={i}>
          <rect
            x={8 + i * 6}
            y={12 + i * 22}
            width="126"
            height="16"
            rx="1.5"
            className={i === 2 ? "fill-primary/[0.08] stroke-primary/70" : "fill-white/[0.02] stroke-border"}
            strokeWidth="1"
          />
          <line
            x1={16 + i * 6}
            y1={20 + i * 22}
            x2={16 + i * 6 + (i === 2 ? 78 : 94)}
            y2={20 + i * 22}
            className={i === 2 ? "stroke-primary/80" : "stroke-muted-foreground/40"}
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <text
            x="176"
            y={24 + i * 22}
            className="fill-muted-foreground/70 font-mono text-[7.5px] tracking-[0.1em]"
          >
            {String(i + 1).padStart(2, "0")}
          </text>
        </g>
      ))}
    </svg>
  )
}

function Vectors() {
  // the signal-ridge grammar, at chunk scale: one stroke per dimension band
  const strokes = Array.from({ length: 58 }, (_, i) => {
    const t = i / 57
    const crest = Math.exp(-Math.pow((t - 0.46) * 3.1, 2))
    const wobble =
      0.34 + 0.3 * Math.abs(Math.sin(i * 0.9)) + 0.24 * Math.abs(Math.sin(i * 0.37 + 1.1))
    return { t, h: (0.24 + 0.76 * wobble) * (0.55 + 0.45 * crest), crest }
  })
  return (
    <svg {...svgProps}>
      <g strokeWidth="1.6" strokeLinecap="round">
        {strokes.map((s, i) => {
          const x = 10 + s.t * 220
          const h = s.h * 88
          return (
            <line
              key={i}
              x1={x}
              y1={74 - h * 0.72}
              x2={x}
              y2={74 + h * 0.28}
              className={s.crest > 0.55 ? "stroke-primary" : "stroke-muted-foreground/45"}
              opacity={0.35 + s.h * 0.65}
            />
          )
        })}
      </g>
      <text x="10" y="122" className="fill-muted-foreground font-mono text-[7.5px] uppercase tracking-[0.18em]">
        384 dimensions · hnsw
      </text>
    </svg>
  )
}

function Graph() {
  const nodes = [
    { x: 40, y: 34 }, { x: 108, y: 20 }, { x: 176, y: 44 },
    { x: 62, y: 92 }, { x: 132, y: 78 }, { x: 202, y: 100 },
  ]
  const edges: [number, number][] = [[0, 1], [1, 2], [0, 3], [1, 4], [3, 4], [4, 5], [2, 5]]
  return (
    <svg {...svgProps}>
      <g className="stroke-border" strokeWidth="1">
        {edges.map(([a, b], i) => {
          const mx = (nodes[a].x + nodes[b].x) / 2
          const my = (nodes[a].y + nodes[b].y) / 2
          return (
            <g key={i}>
              <line x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y} />
              {/* every edge carries its provenance tick */}
              <line x1={mx} y1={my - 3} x2={mx} y2={my + 3} className="stroke-primary/80" strokeWidth="1.5" />
            </g>
          )
        })}
      </g>
      {nodes.map((n, i) => (
        <circle
          key={i}
          cx={n.x}
          cy={n.y}
          r={i === 1 ? 6 : 4.5}
          className={i === 1 ? "fill-primary/25 stroke-primary" : "fill-background stroke-muted-foreground/60"}
          strokeWidth="1.25"
        />
      ))}
      <text x="10" y="126" className="fill-muted-foreground font-mono text-[7.5px] uppercase tracking-[0.18em]">
        every edge names its source
      </text>
    </svg>
  )
}

function Validate() {
  return (
    <svg {...svgProps}>
      <Plate x={8} y={14} w={150} h={104} />
      <TextLines x={20} y={30} only={6} />
      <g className="stroke-primary" strokeWidth="2" strokeLinecap="round" fill="none">
        <path d="M176 62 l 10 10 l 20 -22" />
      </g>
      <text x="176" y="92" className="fill-muted-foreground font-mono text-[7.5px] uppercase tracking-[0.16em]">
        citable
      </text>
      <line x1="158" y1="66" x2="170" y2="66" className="stroke-border" strokeWidth="1" />
    </svg>
  )
}

const PAYLOADS = {
  parse: Parse,
  extract_metadata: Metadata,
  extract_entities: Entities,
  chunk: Chunks,
  embed: Vectors,
  build_graph: Graph,
  validate: Validate,
} as const

export type PayloadKind = keyof typeof PAYLOADS

export function StagePayload({ kind }: { kind: PayloadKind }) {
  const Shape = PAYLOADS[kind]
  return <Shape />
}
