export interface Investigation {
  id: string
  question: string
  status: string
  confidence: number | null
  confidence_breakdown: { score?: number; components?: Record<string, number>; evidence_count?: number }
  version: number
  created_at: string
  last_refreshed_at: string | null
  new_evidence_available: boolean
}

export interface Hypothesis {
  id: string
  statement: string
  created_at: string
}

export interface InvestigationLinkRef {
  link_type: string
  investigation_id: string
  question: string
}

export interface InvestigationDetail extends Investigation {
  hypotheses: Hypothesis[]
  links: InvestigationLinkRef[]
}

export interface Citation {
  index: number
  chunk_id: string
  document_id: string
  title: string | null
  url: string | null
  source: string
  published_at: string | null
  excerpt: string
}

export interface Report {
  id: string
  version: number
  executive_summary: string
  key_findings: string[]
  risks: string[]
  follow_up_questions: string[]
  narrative: string
  model: string
  created_at: string
  citations: Citation[]
}

export interface Evidence {
  chunk_id: string
  document_id: string
  stance: "supporting" | "contradicting" | "unknown"
  rationale: string
  query: string
  excerpt: string
  strategy: string
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  text: string
  title: string | null
  url: string | null
  source: string
  doc_type: string
  published_at: string | null
  scores: Record<string, number>
  strategy: string
}

export interface Job {
  id: number
  job_type: string
  document_id: string | null
  attempts: number
  max_attempts: number
  last_error: string | null
  created_at: string
}

export interface PipelineMetrics {
  queue_depth: Record<string, number>
  stages_24h: { stage: string; status: string; runs: number; avg_duration_ms: number }[]
  oldest_pending_seconds: number | null
  retries_24h: number
  document_count: number
}
