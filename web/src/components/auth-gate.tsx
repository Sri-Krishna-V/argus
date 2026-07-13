import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { setApiKey } from "@/lib/api"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { StarGlyph } from "@/components/star-glyph"

const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [locked, setLocked] = useState(false)
  const [value, setValue] = useState("")
  const queryClient = useQueryClient()

  useEffect(() => {
    const onUnauthorized = () => setLocked(true)
    window.addEventListener("argus:unauthorized", onUnauthorized)
    return () => window.removeEventListener("argus:unauthorized", onUnauthorized)
  }, [])

  if (!locked) return <>{children}</>

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex w-80 flex-col gap-5 rounded-lg border border-border bg-white/[0.03] p-8">
        <div className="flex flex-col items-center gap-2">
          <div className="flex items-center gap-2">
            <StarGlyph className="size-4 text-primary" />
            <span className="text-xl font-light tracking-tight text-white">Argus</span>
          </div>
          <span className={EYEBROW}>API key required</span>
        </div>
        <Input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Argus API key"
          autoFocus
        />
        <Button
          onClick={() => {
            setApiKey(value)
            setLocked(false)
            queryClient.invalidateQueries()
          }}
          disabled={!value}
        >
          Save
        </Button>
      </div>
    </div>
  )
}
