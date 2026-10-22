import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, FileText, History, Loader2, Plus, X } from "lucide-react";
import type { ApiClient } from "./api";
import type { DocumentLibrary, Task, TaskSummary, UploadedDocument } from "./types";
import DocumentPanel from "./components/DocumentPanel";
import TaskResult from "./components/TaskResult";
import { saveBlob, STATUS, timeLabel } from "./workspace";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong. Please try again.";

export default function App({ api, accountMenu }: { api: ApiClient; accountMenu: ReactNode }) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [goal, setGoal] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [library, setLibrary] = useState<DocumentLibrary | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [busyDocument, setBusyDocument] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    let fetching = false;
    async function refresh() {
      if (fetching || document.hidden) return;
      fetching = true;
      const results = await Promise.allSettled([
        api.getTasks(),
        ...(selected ? [api.getTask(selected)] : []),
      ]);
      if (!alive) return;
      if (results[0].status === "fulfilled") setTasks(results[0].value as TaskSummary[]);
      if (results[1]?.status === "fulfilled") {
        const updated = results[1].value as Task;
        setTask((current) =>
          current?.id === updated.id && current.updated_at > updated.updated_at ? current : updated,
        );
      }
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") setError(message(failure.reason));
      setLoading(false);
      fetching = false;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    const visible = () => {
      if (!document.hidden) void refresh();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [api, selected]);

  useEffect(() => {
    if (!documentsOpen) return;
    let alive = true;
    void api.getDocuments().then(
      (value) => {
        if (alive) setLibrary(value);
      },
      (err) => {
        if (alive) setDocumentError(message(err));
      },
    );
    return () => {
      alive = false;
    };
  }, [api, documentsOpen]);

  function accept(next: Task) {
    setTask(next);
    setSelected(next.id);
    setTasks((current) =>
      [next, ...current.filter((item) => item.id !== next.id)].sort((a, b) =>
        b.created_at.localeCompare(a.created_at),
      ),
    );
  }

  async function action(work: () => Promise<Task>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      accept(await work());
      setGoal("");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    const text = goal.trim();
    if (text.length < (task ? 1 : 3)) return;
    void action(() =>
      task?.status === "needs_input" ? api.resumeTask(task.id, text) : api.startTask(text),
    );
  }

  function updateDocument(document: UploadedDocument) {
    setLibrary(
      (current) =>
        current && {
          ...current,
          documents: [document, ...current.documents.filter((item) => item.id !== document.id)],
        },
    );
  }

  async function uploadFiles(files: File[]) {
    if (uploading || !files.length) return;
    setDocumentError(null);
    const errors: string[] = [];
    for (const file of files) {
      if (!/\.(pdf|md)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
        errors.push(`${file.name}: choose a PDF or Markdown file up to 10 MB.`);
        continue;
      }
      setUploading(file.name);
      try {
        updateDocument(await api.uploadDocument(file));
      } catch (err) {
        errors.push(`${file.name}: ${message(err)}`);
      }
    }
    setUploading(null);
    if (errors.length) setDocumentError(errors.join(" "));
  }

  async function documentAction(id: string, work: () => Promise<void>) {
    if (busyDocument) return;
    setBusyDocument(id);
    setDocumentError(null);
    try {
      await work();
    } catch (err) {
      setDocumentError(message(err));
    } finally {
      setBusyDocument(null);
    }
  }

  function newTask() {
    setSelected(null);
    setTask(null);
    setGoal("");
    setError("");
    setHistoryOpen(false);
  }

  return (
    <div className="workspace">
      <header className="app-header">
        <a
          className="brand"
          href="/"
          onClick={(event) => {
            event.preventDefault();
            newTask();
          }}
        >
          axelyn<span>.</span>
        </a>
        <nav aria-label="Workspace">
          <button onClick={() => setDocumentsOpen(true)}>
            <FileText size={16} />
            Documents
          </button>
          <button aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}>
            <History size={16} />
            History
          </button>
          {accountMenu}
        </nav>
      </header>
      {historyOpen && (
        <aside className="history" aria-label="Task history">
          <div className="section-heading">
            <h2>History</h2>
            <button
              className="icon-button"
              aria-label="Close history"
              onClick={() => setHistoryOpen(false)}
            >
              <X size={18} />
            </button>
          </div>
          {loading ? (
            <p>Loading tasks…</p>
          ) : !tasks.length ? (
            <p>Your tasks will appear here.</p>
          ) : (
            <ul>
              {tasks.map((item) => (
                <li key={item.id}>
                  <button
                    aria-current={selected === item.id ? "true" : undefined}
                    onClick={() => {
                      setTask(null);
                      setSelected(item.id);
                      setGoal("");
                      setError("");
                      setHistoryOpen(false);
                    }}
                  >
                    <span>{item.goal}</span>
                    <small>
                      {STATUS[item.status]} · {timeLabel(item.created_at)}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      )}
      <main className={`task-workspace ${selected ? "has-task" : ""}`}>
        <div className="workspace-heading">
          <div>
            <h1>{selected ? "Your task" : "What needs doing?"}</h1>
            {!selected && <p>Create a document from your sources.</p>}
          </div>
          {selected && (
            <button onClick={newTask}>
              <Plus size={16} />
              New task
            </button>
          )}
        </div>
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            <button className="icon-button" aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {task && <p className="task-goal">{task.goal}</p>}
        {selected && !task && (
          <p role="status">
            <Loader2 className="spin" size={18} /> Loading task…
          </p>
        )}
        {task && (
          <TaskResult
            task={task}
            busy={busy}
            onCancel={() => void action(() => api.cancelTask(task.id))}
            onRetry={() =>
              void action(() => api.resumeTask(task.id, "Retry using the available context."))
            }
          />
        )}
        {(!selected || task?.status === "needs_input") && (
          <form
            className="task-form"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label className="sr-only" htmlFor="task-goal">
              {task ? "Reply to the task" : "Describe your task"}
            </label>
            <textarea
              id="task-goal"
              ref={composer}
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder={
                task
                  ? "Add the information needed to continue…"
                  : "Describe what you need from your documents…"
              }
              maxLength={task ? 8000 : 4000}
              rows={5}
              disabled={busy}
            />
            <div className="composer-actions">
              <button type="button" onClick={() => setDocumentsOpen(true)}>
                <Plus size={16} />
                Add documents
              </button>
              <button
                className="primary"
                type="submit"
                disabled={busy || goal.trim().length < (task ? 1 : 3)}
              >
                {busy ? <Loader2 size={16} className="spin" /> : <ArrowUp size={16} />}
                {task ? "Continue task" : "Create document"}
              </button>
            </div>
          </form>
        )}
        {!selected && (
          <p className="workspace-note">
            Work continues in the background. Find it again in History.
          </p>
        )}
      </main>
      <DocumentPanel
        open={documentsOpen}
        library={library}
        uploading={uploading}
        busyId={busyDocument}
        error={documentError}
        onClose={() => setDocumentsOpen(false)}
        onPickFiles={() => fileInput.current?.click()}
        onUpload={(files) => void uploadFiles(files)}
        onRetry={(id) =>
          void documentAction(id, async () => updateDocument(await api.indexDocument(id)))
        }
        onDelete={(id) =>
          void documentAction(id, async () => {
            await api.deleteDocument(id);
            setLibrary(
              (current) =>
                current && {
                  ...current,
                  documents: current.documents.filter((doc) => doc.id !== id),
                },
            );
          })
        }
        onDownload={(id, filename) =>
          void documentAction(id, async () => saveBlob(await api.downloadDocument(id), filename))
        }
      />
      <input
        ref={fileInput}
        type="file"
        accept=".pdf,.md"
        multiple
        hidden
        onChange={(event) => {
          void uploadFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
    </div>
  );
}
