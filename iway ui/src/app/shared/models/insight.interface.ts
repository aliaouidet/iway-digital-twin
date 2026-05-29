export interface InsightSuggestion {
  category: string;
  count: number;
  trend: 'up' | 'down' | 'stable';
  trend_pct: number;
  priority: 'critical' | 'high' | 'medium' | 'low';
  suggestion: string;
  sample_queries?: string[];
}

export interface FallbackCategory {
  name: string;
  count: number;
}

export interface ConfidenceBucket {
  range: string;
  count: number;
}

export interface InsightsData {
  knowledge_gaps: number;
  rag_coverage_rate: number;
  docs_suggested: number;
  failed_clusters: number;
  ai_summary?: string;
  suggestions: InsightSuggestion[];
  fallback_categories: FallbackCategory[];
  confidence_distribution: ConfidenceBucket[];
  // Extra stats
  total_queries?: number;
  total_fallback?: number;
  total_escalated?: number;
  avg_confidence?: number;
}
