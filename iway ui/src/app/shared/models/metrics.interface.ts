export interface TimeSeriesPoint {
  day: string;
  rag_confidence: number;
  response_time: number;
  requests: number;
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
