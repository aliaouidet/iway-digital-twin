export interface InsightSuggestion {
  category: string;
  count: number;
  trend: 'up' | 'down' | 'stable';
  trend_pct: number;
  priority: 'high' | 'medium' | 'low';
  suggestion: string;
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
  suggestions: InsightSuggestion[];
  fallback_categories: FallbackCategory[];
  confidence_distribution: ConfidenceBucket[];
}
