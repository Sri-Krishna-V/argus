import { useEffect, useRef } from "react"

// ponytail: hand-rolled canvas noise instead of a shader/WebGL lib — three sine
// octaves at irrational frequency/speed ratios read as organic at this scale;
// upgrade to a real noise function (simplex/value) only if the sine lattice
// becomes visually periodic at larger canvas sizes.

const STEEL: readonly [number, number, number] = [141, 160, 186]
const EMBER: readonly [number, number, number] = [244, 194, 154]
const CYCLE_SECONDS = 40 // full visual drift cycle

function noise(x: number, t: number): number {
  const k1 = 0.006
  const k2 = k1 * Math.SQRT2
  const k3 = k1 * Math.sqrt(5)
  const omega = (2 * Math.PI) / CYCLE_SECONDS
  const raw =
    0.55 * Math.sin(k1 * x + t * omega) +
    0.3 * Math.sin(k2 * x + t * omega * Math.SQRT2) +
    0.15 * Math.sin(k3 * x + t * omega * 1.3)
  return (raw + 1) / 2 // normalize [-1,1] -> [0,1]
}

function draw(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  t: number,
  amplitude: number,
) {
  ctx.clearRect(0, 0, width, height)
  if (width <= 0 || height <= 0) return

  const baseline = height * 0.62
  const step = 3

  // Pass 1: locate the global crest — the ember hotspot follows it.
  let crestX = 0
  let crestN = -Infinity
  for (let x = 0; x <= width; x += step) {
    const n = noise(x, t)
    if (n > crestN) {
      crestN = n
      crestX = x
    }
  }
  const sigma = width * 0.18

  // Pass 2: draw the ridge strokes.
  for (let x = 0; x <= width; x += step) {
    const n = Math.pow(noise(x, t), 2.2)
    const up = n * height * amplitude
    const down = n * height * 0.35 * amplitude

    const gaussian = Math.exp(-((x - crestX) ** 2) / (2 * sigma * sigma))
    const blend = Math.min(1, gaussian * n)
    const r = STEEL[0] + (EMBER[0] - STEEL[0]) * blend
    const g = STEEL[1] + (EMBER[1] - STEEL[1]) * blend
    const b = STEEL[2] + (EMBER[2] - STEEL[2]) * blend
    const alpha = 0.08 + n * 0.55

    ctx.strokeStyle = `rgba(${r.toFixed(0)}, ${g.toFixed(0)}, ${b.toFixed(0)}, ${alpha.toFixed(3)})`
    ctx.beginPath()
    ctx.moveTo(x + 0.5, baseline - up)
    ctx.lineTo(x + 0.5, baseline + down)
    ctx.stroke()
  }
}

export function SignalRidge({
  className,
  amplitude = 1,
}: {
  className?: string
  amplitude?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    let width = 0
    let height = 0
    let rafId = 0

    function resize() {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas!.getBoundingClientRect()
      width = rect.width
      height = rect.height
      canvas!.width = Math.max(1, Math.round(width * dpr))
      canvas!.height = Math.max(1, Math.round(height * dpr))
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (reduceMotion) draw(ctx!, width, height, 0, amplitude)
    }

    function frame(now: number) {
      draw(ctx!, width, height, now / 1000, amplitude)
      if (!reduceMotion) rafId = requestAnimationFrame(frame)
    }

    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    resize()
    if (!reduceMotion) rafId = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(rafId)
      observer.disconnect()
    }
  }, [amplitude])

  return <canvas ref={canvasRef} className={className ?? "h-full w-full"} />
}
