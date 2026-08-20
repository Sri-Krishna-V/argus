import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

// ponytail: one shared react-query key, so every call site reads the same cached
// /health response instead of a context provider carrying a single boolean.
export function useDemoMode(): { demo: boolean; writesLocked: boolean } {
  const { data, isPending } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<{ status: string; demo?: boolean }>("/health"),
    staleTime: Infinity,
  })
  // unknown counts as locked: a write clicked before /health answers would 401 and
  // throw the visitor onto the API-key prompt, which is what the flag exists to avoid
  return { demo: data?.demo === true, writesLocked: isPending || data?.demo === true }
}

export const READ_ONLY_HINT = "Read-only demo — writes require an API key"
