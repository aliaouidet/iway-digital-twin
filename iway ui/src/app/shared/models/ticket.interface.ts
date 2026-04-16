export type ProcessingStatus = 'RAG_RESOLVED' | 'AI_HANDLED' | 'HUMAN_REQUIRED' | 'PENDING';

export interface RagContext {
  documentId: string;
  chunkText: string;
  similarityScore: number;
  sourceUrl?: string;
}

export interface SupportTicket {
  id: string;
  userId: string;
  query: string;
  status: ProcessingStatus;
  ragContext: RagContext[];
  aiResponse?: string;
  confidenceScore: number;
  createdAt: string;
  assignedTo?: string;
  ragSources: number;
}

export interface EscalationTicket {
  case_id: string;
  status: string;
  queue_position: number;
  estimated_wait: string;
  matricule: string;
  client_name: string;
  client_role: string;
  reason: string;
  chat_history: Array<{ role: string; content: string }>;
  created_at: string;
}

export interface ReclamationInput {
  matricule: string;
  objet: string;
  message: string;
  piece_jointe_base64?: string;
}

export interface Reclamation {
  id: string;
  date: string;
  objet: string;
  statut: string;
  message_preview?: string;
}
