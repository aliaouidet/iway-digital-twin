export interface RagConfig {
  chunking_strategy: string;
  top_k: number;
  similarity_threshold: number;
  enable_ai_fallback: boolean;
  auto_escalate_negative_sentiment: boolean;
}

export interface LlmConfig {
  primary_model: string;
  temperature: number;
  system_prompt: string;
}

export interface RetryConfig {
  max_retries: number;
  backoff_seconds: number;
}

export interface SystemConfig {
  rag: RagConfig;
  llm: LlmConfig;
  retry: RetryConfig;
}
