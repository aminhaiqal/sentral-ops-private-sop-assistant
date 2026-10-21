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

export type DocumentLibrary = {
  documents: UploadedDocument[];
  storage_configured: boolean;
  demo_documents: number;
};

export type BotInput = { name: string; role: string; instructions: string };
export type Bot = BotInput & { id: string; created_at: string; updated_at: string };
export type TaskStatus =
  "queued" | "running" | "needs_input" | "completed" | "failed" | "cancelled" | "limit_reached";
export type TaskSummary = {
  id: string;
  bot_id: string | null;
  routine_id: string | null;
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
  memory_ids: string[];
};
export type Memory = {
  id: string;
  bot_id: string;
  kind: "preference" | "outcome";
  key: string;
  value: string;
  source: "user" | "harness";
  source_task_id: string | null;
  created_at: string;
  updated_at: string;
};
export type RoutineInput = {
  bot_id: string;
  name: string;
  goal: string;
  completion_criteria: string;
  recurrence: "daily" | "weekdays" | "weekly";
  timezone: string;
  local_time: string;
  weekday: number;
  enabled: boolean;
};
export type Routine = RoutineInput & {
  id: string;
  next_run_at: string;
  last_task_id: string | null;
  created_at: string;
  updated_at: string;
};
