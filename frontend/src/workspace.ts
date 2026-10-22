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
export function timeLabel(date: string): string {
  const value = new Date(date);
  return value.toLocaleDateString([], { month: "short", day: "numeric" });
}
export function activityLabel(kind: string, detail: string): string {
  if (kind === "tool") {
    const labels: Record<string, string> = {
      search_documents: "Searched your documents",
      write_artifact: "Saved a document",
      read_artifact: "Checked the saved document",
      complete_task: "Finished the task",
      request_input: "Asked for your input",
    };
    return `${labels[detail.split(":")[0]] ?? "Used a tool"}${detail.endsWith("error") ? " · needs attention" : ""}`;
  }
  const labels: Record<string, string> = {
    queued: "Task received",
    resumed: "Resumed with your reply",
    user_input: "Received your reply",
    completed: "Document ready",
    cancelled: "Stopped by you",
    retry: "Retrying a temporary error",
    failed: "Run stopped",
    needs_input: "Waiting for your reply",
    limit_reached: "Run limit reached",
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
