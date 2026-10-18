import type { AskResponse, ConversationTurn, DemoQuestion, DocumentLibrary, HealthResponse,
  IngestResponse, UploadedDocument } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options?.headers ?? {})
    },
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed with ${response.status}`);
  }

  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function getDemoQuestions(): Promise<DemoQuestion[]> {
  return request<DemoQuestion[]>("/api/demo-questions");
}

export function ingestDocuments(): Promise<IngestResponse> {
  return request<IngestResponse>("/api/ingest", { method: "POST" });
}

export function askQuestion(question: string, history: ConversationTurn[] = []): Promise<AskResponse> {
  return request<AskResponse>("/api/ask", {
    method: "POST",
    body: JSON.stringify({ question, top_k: 5, history })
  });
}

export function getDocuments(): Promise<DocumentLibrary> {
  return request<DocumentLibrary>("/api/documents");
}
export function uploadDocument(file: File): Promise<UploadedDocument> {
  const body = new FormData(); body.append("file", file);
  return request<UploadedDocument>("/api/documents", { method: "POST", body });
}
export function indexDocument(id: string): Promise<UploadedDocument> {
  return request<UploadedDocument>(`/api/documents/${id}/index`, { method: "POST" });
}
export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: "DELETE" });
}
export function documentDownloadUrl(id: string): string { return `${API_URL}/api/documents/${id}/download`; }
