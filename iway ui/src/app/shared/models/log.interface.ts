export type LogOutcome = 'RAG_RESOLVED' | 'GRAPH_RESOLVED' | 'STALL_RESOLVED' | 'AI_FALLBACK' | 'HUMAN_ESCALATED' | 'ERROR' | string;

export interface LogEntry {
  id: string;
  otel_trace_id?: string;
  timestamp: string;
  user_id: string;
  query: string;
  top_similarity: number;
  chunks_retrieved: number;
  gen_time_ms: number;
  tokens_used: number;
  outcome: LogOutcome;
  model: string;
  confidence: number;
}

export interface LogFilter {
  search?: string;
  outcome?: LogOutcome | '';
  user_id?: string;
  min_similarity?: number;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}

export interface PaginatedLogs {
  items: LogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
