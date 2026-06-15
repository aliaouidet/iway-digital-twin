export interface TimeSeriesPoint {
  day: string;
  date?: string;
  rag_confidence: number;
  response_time: number;
  requests: number;
  total_traces: number;
  total_tokens?: number;
}

export interface MetricsComparison {
  total_requests: number;
  rag_success_rate: number;
  escalation_rate: number;
  avg_confidence: number;
  avg_response_time_ms: number;
  window_days: number;
}

export interface DashboardMetrics {
  total_requests: number;
  rag_resolved: number;
  ai_fallback: number;
  human_escalated: number;
  errors: number;
  avg_confidence: number;
  avg_response_time_ms: number;
  rag_success_rate: number;
  fallback_rate: number;
  escalation_rate: number;
  error_rate: number;
  open_tickets: number;
  time_series: TimeSeriesPoint[];
  comparison?: MetricsComparison | null;
}

export interface FeedbackStats {
  total: number;
  positive: number;
  negative: number;
  csat_score: number;
}

export interface RealtimeMetricUpdate {
  total_requests: number;
  rag_resolved: number;
  ai_fallback: number;
  human_escalated: number;
  errors: number;
  open_tickets: number;
  timestamp: string;
}
