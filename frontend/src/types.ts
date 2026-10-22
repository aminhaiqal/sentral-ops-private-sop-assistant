export type SourceSnippet = {
  document_id: string;
  title: string;
  chunk_id: string;
  score: number;
  excerpt: string;
  citation: string;
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
export type DocumentLibrary = { documents: UploadedDocument[]; storage_configured: boolean };
export type TaskStatus =
  "queued" | "running" | "needs_input" | "completed" | "failed" | "cancelled" | "limit_reached";
export type TaskSummary = {
  id: string;
  goal: string;
  completion_criteria: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  summary: string;
  exception: string;
  turns: number;
  tokens: number;
  max_turns: number;
  max_tokens: number;
};
export type Artifact = { id: string; title: string; content: string; sha256: string };
export type Task = TaskSummary & {
  context: string;
  artifacts: Artifact[];
  sources: SourceSnippet[];
  events: { kind: string; detail: string; at: string }[];
};
