import type { AskResponse, DemoQuestion, HealthResponse, IngestResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    },
    ...options
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
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

export function askQuestion(question: string): Promise<AskResponse> {
  return request<AskResponse>("/api/ask", {
    method: "POST",
    body: JSON.stringify({ question, top_k: 5 })
  });
}
