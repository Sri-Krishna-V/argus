import { useEffect, useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { SearchResult } from "@/lib/types"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export const Route = createFileRoute("/search")({
  component: SearchPage,
})

const EYEBROW = "font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase"
const DEBOUNCE_MS = 300

// ponytail: setTimeout debounce instead of a library — one effect is the
// whole feature at this scale.
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}

function topScore(scores: Record<string, number>): number | null {
  const values = Object.values(scores)
  return values.length > 0 ? Math.max(...values) : null
}

function SearchPage() {
  const [query, setQuery] = useState("")
  const [docType, setDocType] = useState("all")
  const debouncedQuery = useDebounced(query, DEBOUNCE_MS)

  const { data, error } = useQuery({
    queryKey: ["search", debouncedQuery, docType],
    queryFn: () =>
      api.get<SearchResult[]>(
        `/api/search?${new URLSearchParams({
          q: debouncedQuery,
          ...(docType !== "all" ? { doc_type: docType } : {}),
          k: "20",
        })}`,
      ),
    enabled: debouncedQuery.trim().length > 0,
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <span className={EYEBROW}>Search</span>
        <h1 className="mt-1 text-3xl font-light tracking-tight text-white">Query the corpus</h1>
      </div>

      <div className="flex gap-3">
        <Input
          placeholder="Search documents…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-md"
        />
        <Select value={docType} onValueChange={(value) => setDocType(value ?? "all")}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            <SelectItem value="filing">Filing</SelectItem>
            <SelectItem value="news">News</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {debouncedQuery.trim().length === 0 && (
        <div className="flex justify-center py-16">
          <span className={EYEBROW}>Type to search the corpus</span>
        </div>
      )}

      {error && <p className="text-destructive">{error.message}</p>}

      {data && data.length === 0 && (
        <div className="flex justify-center py-16">
          <span className={EYEBROW}>No results.</span>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {data?.map((r) => {
          const score = topScore(r.scores)
          return (
            <Card key={r.chunk_id} className="border border-border bg-white/[0.03]">
              <CardContent className="flex flex-col gap-1.5 pt-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-white">{r.title ?? "Untitled"}</span>
                  {score !== null && (
                    <span className="font-mono text-xs text-muted-foreground">{score.toFixed(3)}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
                  <span>{r.doc_type}</span>
                  <span>·</span>
                  <span>{r.source}</span>
                </div>
                <p className="line-clamp-2 text-sm text-muted-foreground">{r.text}</p>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
