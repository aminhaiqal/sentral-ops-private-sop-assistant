import type { TaskStatus } from "./types";

export const STATUS: Record<TaskStatus, string> = {
  queued: "Queued",
  running: "Working",
  needs_input: "Needs your input",
  completed: "Done",
  failed: "Couldn’t finish",
  cancelled: "Stopped",
  limit_reached: "Run limit reached",
};
export const WORKING = new Set<TaskStatus>(["queued", "running"]);
export const CRITERIA =
  "Save a useful Markdown document with source citations and check the saved file.";
export function timeLabel(date: string): string {
  const value = new Date(date);
  if (value.toDateString() === new Date().toDateString())
    return value.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return value.toLocaleDateString([], { month: "short", day: "numeric" });
}
export function dayLabel(date: string): string {
  const value = new Date(date);
  return value.toDateString() === new Date().toDateString()
    ? "Today"
    : value.toLocaleDateString([], { month: "long", day: "numeric" });
}
export function activityLabel(kind: string, detail: string): string {
  if (kind === "tool") {
    const tool = detail.split(":")[0];
    const labels: Record<string, string> = {
      search_sops: "Searched your knowledge",
      write_artifact: "Saved a document",
      read_artifact: "Read back the saved document",
      complete_task: "Finished the task",
      recall_memory: "Recalled saved memory",
      request_input: "Asked for your input",
    };
    return `${labels[tool] ?? "Used a tool"}${detail.endsWith("error") ? " · needs attention" : ""}`;
  }
  const labels: Record<string, string> = {
    queued: "Task received",
    memory_loaded: "Loaded bot instructions and memory",
    resumed: "Resumed with your reply",
    user_input: "Received your reply",
    completed: "Document ready",
    cancelled: "Stopped by you",
    retry: "Retrying a temporary error",
    failed: "Run stopped",
    needs_input: "Waiting for your reply",
    limit_reached: "Run budget reached",
  };
  return labels[kind] ?? "Updated the task";
}
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
