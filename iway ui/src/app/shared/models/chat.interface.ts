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
