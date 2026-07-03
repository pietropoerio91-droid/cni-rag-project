export interface Citation {
  title: string;
  source: string;
  relevance_score: number;
  excerpt: string;
}

export interface QueryResponse {
  response: string;
  citations: Citation[];
  category: string;
  trace_id: string;
}

export interface QueryRequest {
  question: string;
  top_k?: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  documents_indexed: number;
  llm_connected: boolean;
}

export interface IngestResponse {
  status: string;
  documents_crawled: number;
  chunks_indexed: number;
  message: string;
}

export interface IngestStatus {
  running: boolean;
  phase: string;
  progress_pct: number;
  documents_found: number;
  documents_total: number;
  chunks_indexed: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  category?: string;
  timestamp: Date;
  error?: boolean;
}

export interface StreamEvent {
  type: string;
  data: string;
}

export interface QdrantStatsResponse {
  collection: string;
  mode: string;
  points_count: number;
  vectors_count: number;
}

export interface QdrantDocument {
  id: string;
  score: number;
  title?: string;
  source?: string;
  category?: string;
  content?: string;
  url?: string;
  [key: string]: unknown;
}

export interface QdrantDocumentsResponse {
  documents: QdrantDocument[];
  offset?: number;
  total?: number | null;
  search?: string;
}

export interface QdrantAnalyticsResponse {
  total_documents: number;
  avg_content_length: number;
  median_content_length: number;
  categories: Record<string, number>;
  content_length_buckets: Record<string, number>;
  top_sources: { name: string; count: number }[];
}

export interface CoverageSection {
  category: string;
  chunks: number;
  avg_content_length: number;
  poor_coverage: boolean;
}

export interface QdrantCoverageResponse {
  sections: CoverageSection[];
}
