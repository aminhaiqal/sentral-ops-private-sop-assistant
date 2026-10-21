import type { AskResponse, ConversationTurn, DocumentLibrary, UploadedDocument } from "./types";

const API_URL = import.meta.env?.VITE_API_URL ?? "";

export function createApiClient(getToken: () => Promise<string | null>, baseUrl = API_URL) {
  const pending = new Set<AbortController>();
  async function raw(path: string, options?: RequestInit): Promise<Response> {
    const token = await getToken();
    if (!token) throw new Error("Your session has ended. Sign in again.");
    const controller = new AbortController();
    pending.add(controller);
    try {
      const headers = new Headers(options?.headers);
      if (!(options?.body instanceof FormData)) headers.set("Content-Type", "application/json");
      headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch(`${baseUrl}${path}`, {
        ...options,
        credentials: "omit",
        headers,
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? `Request failed with ${response.status}`);
      }
      return response;
    } finally {
      pending.delete(controller);
    }
  }
  async function request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await raw(path, options);
    return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
  }
  return {
    askQuestion(question: string, history: ConversationTurn[] = []): Promise<AskResponse> {
      return request("/api/ask", {
        method: "POST",
        body: JSON.stringify({ question, top_k: 5, history }),
      });
    },
    getDocuments(): Promise<DocumentLibrary> {
      return request("/api/documents");
    },
    uploadDocument(file: File): Promise<UploadedDocument> {
      const body = new FormData();
      body.append("file", file);
      return request("/api/documents", { method: "POST", body });
    },
    indexDocument(id: string): Promise<UploadedDocument> {
      return request(`/api/documents/${id}/index`, { method: "POST" });
    },
    deleteDocument(id: string): Promise<void> {
      return request(`/api/documents/${id}`, { method: "DELETE" });
    },
    async downloadDocument(id: string): Promise<Blob> {
      return (await raw(`/api/documents/${id}/download`)).blob();
    },
    abortRequests() {
      for (const controller of pending) controller.abort();
      pending.clear();
    },
  };
}
export type ApiClient = ReturnType<typeof createApiClient>;
