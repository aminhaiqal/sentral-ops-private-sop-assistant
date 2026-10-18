export type BoundaryWarning = {
  category: string;
  message: string;
};

export type SourceSnippet = {
  document_id: string;
  title: string;
  chunk_id: string;
  score: number;
  excerpt: string;
  citation: string;
};

export type AgentStep = {
  name: string;
  status: string;
  detail: string;
};

export type AskResponse = {
  answer: string;
  sources: SourceSnippet[];
  warnings: BoundaryWarning[];
  agent_steps: AgentStep[];
};

export type DemoQuestion = {
  question: string;
  boundary_expected: boolean;
};

export type HealthResponse = {
  status: string;
  app_name: string;
  qdrant_collection: string;
  openai_configured: boolean;
};

export type IngestResponse = {
  documents: number;
  chunks: number;
  collection: string;
};

export type UploadedDocument = {
  id: string;
  filename: string;
  title: string;
  size_bytes: number;
  uploaded_at: string;
  status: "saved" | "indexed";
  chunks: number;
  pages: number | null;
  indexing_error: string | null;
};

export type DocumentLibrary = {
  documents: UploadedDocument[];
  storage_configured: boolean;
  demo_documents: number;
};

export type ConversationTurn = { role: "user" | "assistant"; content: string };
export type ChatMessage = ConversationTurn & {
  id: string;
  response?: AskResponse;
  pending?: boolean;
  error?: string;
};
export type Chat = { id: string; title: string; updatedAt: number; messages: ChatMessage[] };
