const API_KEY_STORAGE = "argus_api_key"

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE)
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE, key)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getApiKey()
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  if (key) headers.set("X-API-Key", key)

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new Event("argus:unauthorized"))
    throw new ApiError(401, "invalid or missing API key")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
}
