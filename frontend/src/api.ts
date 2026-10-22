import type {
  DocumentLibrary,
  UploadedDocument,
  Bot,
  BotInput,
  Task,
  TaskSummary,
  Memory,
  Routine,
  RoutineInput,
} from "./types";
import type {
  StudioBot,
  StudioCatalog,
  StudioConfig,
  StudioRun,
  StudioRunSummary,
} from "./studio/types";

import type { Connection, ConnectionsCatalog, DriveFile, DriveDocument } from "./connections/types";

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
        credentials: options?.credentials ?? "omit",
        headers,
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : response.status === 422
              ? "Please check the fields and try again."
              : `Request failed with ${response.status}`,
        );
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
    connections: (): Promise<ConnectionsCatalog> => request("/api/connections"),
    connectGoogleDrive: (): Promise<{ url: string; flow_id: string; expires_in: number }> =>
      request("/api/connections/google-drive/connect", { method: "POST", credentials: "include" }),
    googleDriveAuthStatus: (id: string): Promise<{ status: string; error: string | null }> =>
      request(`/api/connections/google-drive/attempts/${encodeURIComponent(id)}`),
    completeGoogleDriveAuth: (id: string): Promise<Connection> =>
      request(`/api/connections/google-drive/attempts/${encodeURIComponent(id)}/complete`, {
        method: "POST",
      }),
    cancelGoogleDriveAuth: (id: string): Promise<void> =>
      request(`/api/connections/google-drive/attempts/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      }),
    disconnectConnection: (
      id: string,
    ): Promise<{ disconnected: boolean; provider_removed: boolean; message: string }> =>
      request(`/api/connections/${encodeURIComponent(id)}`, { method: "DELETE" }),
    driveFiles: (id: string, query = ""): Promise<DriveFile[]> =>
      request(
        `/api/connections/${encodeURIComponent(id)}/files?query=${encodeURIComponent(query)}`,
      ),
    driveDocument: (id: string, fileId: string): Promise<DriveDocument> =>
      request(`/api/connections/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}`),
    studioCatalog: (): Promise<StudioCatalog> => request("/api/studio/catalog"),
    studioBots: (): Promise<StudioBot[]> => request("/api/studio/bots"),
    studioBot: (id: string): Promise<StudioBot> =>
      request(`/api/studio/bots/${encodeURIComponent(id)}`),
    saveStudioBot: (configuration: StudioConfig, id?: string): Promise<StudioBot> =>
      request(id ? `/api/studio/bots/${encodeURIComponent(id)}` : "/api/studio/bots", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(configuration),
      }),
    deleteStudioBot: (id: string): Promise<void> =>
      request(`/api/studio/bots/${encodeURIComponent(id)}`, { method: "DELETE" }),
    startStudioRun: (id: string, idempotency_key: string): Promise<StudioRun> =>
      request(`/api/studio/bots/${encodeURIComponent(id)}/runs`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key }),
      }),
    studioRuns: (botId?: string): Promise<StudioRunSummary[]> =>
      request(`/api/studio/runs${botId ? `?bot_id=${encodeURIComponent(botId)}` : ""}`),
    studioRun: (id: string): Promise<StudioRun> =>
      request(`/api/studio/runs/${encodeURIComponent(id)}`),
    cancelStudioRun: (id: string): Promise<StudioRun> =>
      request(`/api/studio/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
    retryStudioRun: (id: string): Promise<StudioRun> =>
      request(`/api/studio/runs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
    getBots: (): Promise<Bot[]> => request("/api/bots"),
    starterBots: (): Promise<Bot[]> => request("/api/bots/starter", { method: "POST" }),
    saveBot: (data: BotInput, id?: string): Promise<Bot> =>
      request(id ? `/api/bots/${encodeURIComponent(id)}` : "/api/bots", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      }),
    getTasks: (): Promise<TaskSummary[]> => request("/api/tasks"),
    getTask: (id: string): Promise<Task> => request(`/api/tasks/${encodeURIComponent(id)}`),
    startTask: (bot_id: string, goal: string): Promise<Task> =>
      request("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          bot_id,
          goal,
          completion_criteria:
            "Save a useful Markdown document that fulfills the request, cites the available sources and has been read back for verification.",
        }),
      }),
    cancelTask: (id: string): Promise<Task> =>
      request(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
    resumeTask: (id: string, message: string): Promise<Task> =>
      request(`/api/tasks/${encodeURIComponent(id)}/resume`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    getMemories: (bot: string): Promise<Memory[]> =>
      request(`/api/bots/${encodeURIComponent(bot)}/memories`),
    saveMemory: (bot: string, key: string, value: string): Promise<Memory> =>
      request(`/api/bots/${encodeURIComponent(bot)}/preferences/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    forgetMemory: (bot: string, id: string): Promise<void> =>
      request(`/api/bots/${encodeURIComponent(bot)}/memories/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    getRoutines: (): Promise<Routine[]> => request("/api/routines"),
    saveRoutine: (data: RoutineInput, id?: string): Promise<Routine> =>
      request(id ? `/api/routines/${encodeURIComponent(id)}` : "/api/routines", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      }),
    deleteRoutine: (id: string): Promise<void> =>
      request(`/api/routines/${encodeURIComponent(id)}`, { method: "DELETE" }),
    runRoutine: (id: string): Promise<Task> =>
      request(`/api/routines/${encodeURIComponent(id)}/run`, { method: "POST" }),
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
