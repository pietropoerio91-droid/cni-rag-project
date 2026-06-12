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
