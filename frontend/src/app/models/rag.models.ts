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
  trace_id?: string;
  feedbackGiven?: boolean;
  feedbackCorrect?: boolean;
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
  total_chunks: number;
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

export interface BenchmarkMetrics {
  mrr: number;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  precision_at_1: number;
  precision_at_3: number;
  classification_accuracy: number;
}

export interface BenchmarkResultItem {
  config_name: string;
  metrics: BenchmarkMetrics;
  avg_latency_ms: number;
  total_queries: number;
  config: Record<string, unknown>;
}

export interface BenchmarkRun {
  timestamp: string;
  run_date: string;
  file: string;
  total_queries: number;
  configs: number;
  best_config: string;
  best_mrr: number;
}

export interface BenchmarkFullRun {
  run_date: string;
  timestamp: string;
  best_config: string;
  best_mrr: number;
  results: BenchmarkResultItem[];
}

export interface BenchmarkResponse {
  available: boolean;
  message?: string;
  runs: BenchmarkRun[];
  latest: BenchmarkFullRun | null;
  best_overall: BenchmarkFullRun | null;
}

export interface QueryLogEntry {
  question: string;
  category: string;
  doc_count: number;
  top_score: number;
  citation_scores?: number[];
  latency_ms: number;
  response_length: number;
  timestamp: string;
}

export interface QueryStatsResponse {
  total_queries: number;
  avg_docs_retrieved: number;
  avg_top_score: number;
  avg_latency_ms: number;
  category_distribution: Record<string, number>;
  recent: QueryLogEntry[];
}

export interface QueryMetricsResponse {
  total_queries: number;
  mrr: number;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  precision_at_1: number;
  precision_at_3: number;
  precision_at_5: number;
  system_cls_acc: number | null;
  human_cls_acc: number | null;
  avg_cls_acc: number | null;
  test_total: number;
}
