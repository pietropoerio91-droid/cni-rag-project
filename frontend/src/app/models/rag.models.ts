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

// Le metriche IR sono state rimosse: sulle query degli utenti la rilevanza non
// e' definibile senza fonti attese note. Restano le grandezze osservabili.
export interface RetrievalTelemetry {
  n_scored_docs: number;
  score_mean: number;
  score_median: number;
  score_p10: number;
  score_p90: number;
  top_score_mean: number | null;
  note: string;
}

export interface QueryMetricsResponse {
  total_queries: number;
  system_cls_acc: number | null;
  human_cls_acc: number | null;
  human_cls_acc_n: number;
  avg_cls_acc: number | null;
  test_total: number;
  retrieval_telemetry: RetrievalTelemetry | null;
  note: string;
}

// ---------------------------------------------------------------------------
// Valutazione sul golden dataset
// ---------------------------------------------------------------------------
// Queste interfacce sostituiscono BenchmarkMetrics/QueryMetricsResponse per la
// parte qualitativa: quelle esponevano metriche calcolate sulle query degli
// utenti, che non hanno fonti attese note e quindi non ammettono metriche di
// Information Retrieval. Le metriche vere vengono dai run sul golden dataset.

export interface MetricCI {
  name: string;
  n: number;
  mean: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_method?: string;
  sd?: number;
  median?: number;
}

export interface StageMetrics {
  point: Record<string, number>;
  ci: Record<string, MetricCI>;
}

export interface PairedComparison {
  metric: string;
  mean_difference: number;
  difference_ci?: [number, number];
  effect_size: { delta: number; magnitude: string };
  significance: { test: string; p_value: number; significant_05?: boolean };
  [key: string]: unknown;
}

export interface EvaluationLatest {
  run_id: string;
  run_date: string;
  file: string;
  dataset: string;
  dataset_version: string;
  total_questions: number;
  config_snapshot: Record<string, unknown>;
  retrieval_stages: { retrieved?: StageMetrics; context?: StageMetrics };
  reranker_effect: Record<string, PairedComparison>;
  generation: Record<string, unknown>;
  fallback_rate: number;
  fallback_rate_ci: [number, number] | null;
  avg_latency_s: number;
  latency_ci: [number, number] | null;
  judge_enabled: boolean;
  judge_validated: boolean;
  judge_model: string;
  judge_warning: string | null;
}

export interface EvaluationRunSummary {
  run_id: string;
  run_date: string;
  dataset_version: string;
  total_questions: number;
  judge_validated: boolean;
  judge_model: string;
  hit_at_5_context: number | null;
  mrr_context: number | null;
}

export interface HumanAnnotation {
  faithfulness: number | null;
  answer_relevance: number | null;
  correctness: number | null;
  error_stage: string | null;
  note: string | null;
  annotated_at?: string;
}

export interface AnnotationItem {
  question_id: string;
  question: string;
  category: string;
  response: string;
  reference_answer: string;
  expected_sources: string[];
  must_contain: string[];
  must_contain_pass: boolean | null;
  fallback_triggered: boolean;
  context_sources: string[];
  rank_pre_rerank: number | null;
  rank_post_rerank: number | null;
  latency_s: number;
  annotazione: HumanAnnotation | null;
  suggerimento_stadio: string;
  judgment?: Record<string, { score: number; reason: string }>;
}

export interface AnnotationQueue {
  run_id: string;
  run_date: string;
  blind: boolean;
  metriche: string[];
  stadi_errore: Record<string, string>;
  totale: number;
  annotate: number;
  mancanti: number;
  items: AnnotationItem[];
}

export interface MetricAgreement {
  disponibile: boolean;
  n: number;
  nota?: string;
  media_umano?: number;
  media_giudice?: number;
  bias_giudice?: number;
  direzione_bias?: string;
  mae?: number;
  accordo_esatto?: number;
  accordo_entro_1?: number;
  kappa_quadratico?: number | null;
  interpretazione_kappa?: string;
  krippendorff_alpha?: number | null;
  interpretazione_alpha?: string;
  pearson_r?: number | null;
  matrice_confusione?: number[][];
  scala?: number[];
}

export interface AgreementReport {
  run_id: string;
  judge_model: string;
  giudice_uguale_al_generatore: boolean;
  n_domande_annotate: number;
  n_domande_con_giudizio: number;
  n_domande_confrontabili: number;
  totale_domande_run: number;
  metriche: Record<string, MetricAgreement>;
  kappa_medio: number | null;
  interpretazione_complessiva?: string;
  giudice_utilizzabile: boolean | null;
  conclusione: string;
  tassonomia_errori: {
    conteggi: Record<string, number>;
    etichette: Record<string, string>;
    totale_codificati: number;
  };
}
