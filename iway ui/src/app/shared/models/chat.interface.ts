export type ProcessorType = 'RAG' | 'AI Model' | 'Failed – Human Pending';

export interface ChatMessage {
  id: string;
  role: 'user' | 'rag' | 'ai' | 'system';
  content: string;
  timestamp: string;
  processor?: ProcessorType;
  confidence?: number;
  sources?: string[];
}

export interface ConversationThread {
  id: string;
  userId: string;
  status: 'active' | 'resolved' | 'escalated';
  lastMessage: string;
  time: string;
  unread: number;
}

export interface QueueItem {
  id: string;
  user_name: string;
  user_role: string;
  user_matricule: string;
  status: string;
  created_at: string;
  reason: string | null;
  message_count: number;
  last_message: string;
  agent_matricule: string | null;
  last_ai_confidence: number | null;
}
