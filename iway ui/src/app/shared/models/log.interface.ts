export type LogOutcome = 'RAG_RESOLVED' | 'AI_FALLBACK' | 'HUMAN_ESCALATED' | 'ERROR';

export interface LogEntry {
  id: string;
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
