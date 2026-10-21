import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowUp,
  BookOpen,
  ChevronDown,
  CircleHelp,
  Info,
  Loader2,
  Plus,
  Search,
  X,
} from "lucide-react";
import type { ApiClient } from "./api";
import type {
  Bot,
  DocumentLibrary,
  Memory,
  Routine,
  Task,
  TaskSummary,
  UploadedDocument,
} from "./types";
import BotAvatar from "./components/BotAvatar";
import DocumentPanel from "./components/DocumentPanel";
import TaskConversation from "./components/TaskConversation";
import WorkspaceInspector, { type InspectorView } from "./components/WorkspaceInspector";
import { BotEditor, MemoryEditor, RoutineEditor } from "./components/WorkspaceEditors";
import { saveBlob, STATUS, timeLabel, WORKING } from "./workspace";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong. Please try again.";
type Editor =
  | { kind: "bot"; bot?: Bot }
  | { kind: "memory"; memory?: Memory }
  | { kind: "routine"; routine?: Routine };

export default function App({
  api,
  storageScope,
  accountMenu,
}: {
  api: ApiClient;
  storageScope: string;
  accountMenu: ReactNode;
}) {
  const [bots, setBots] = useState<Bot[]>([]);
  const [selected, setSelected] = useState<string | null>(() => {
    try {
      return localStorage.getItem(`axelyn:bot:${storageScope}`);
    } catch {
      return null;
    }
  });
  const [summaries, setSummaries] = useState<TaskSummary[]>([]);
  const [details, setDetails] = useState<Record<string, Task>>({});
  const detailCache = useRef(details);
  detailCache.current = details;
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [memories, setMemories] = useState<{ bot: string; values: Memory[] }>({
    bot: "",
    values: [],
  });
  const [memoryError, setMemoryError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [goal, setGoal] = useState("");
  const [replyId, setReplyId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [mobileChat, setMobileChat] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth >= 1180);
  const [view, setView] = useState<InspectorView>({ kind: "overview" });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [help, setHelp] = useState(false);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [library, setLibrary] = useState<DocumentLibrary | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [busyDocument, setBusyDocument] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const bot =
    bots.find((item) => item.id === selected) ??
    bots.find((item) => /chief/i.test(item.name)) ??
    bots[0];
  const botTasks = summaries
    .filter((task) => task.bot_id === bot?.id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const replyTask = botTasks.find((task) => task.id === replyId && task.status === "needs_input");

  const acceptTask = useCallback((task: Task) => {
    setDetails((current) =>
      current[task.id]?.updated_at > task.updated_at ? current : { ...current, [task.id]: task },
    );
    setSummaries((current) =>
      [task, ...current.filter((item) => item.id !== task.id)].sort((a, b) =>
        b.created_at.localeCompare(a.created_at),
      ),
    );
  }, []);

  useEffect(() => {
    let alive = true,
      polling = false;
    async function refresh(initial = false) {
      if (polling || (!initial && document.hidden)) return;
      polling = true;
      const results = await Promise.allSettled([
        api.getTasks(),
        api.getRoutines(),
        ...(initial ? [api.getBots()] : []),
      ]);
      if (!alive) return;
      const [tasksResult, routinesResult, botsResult] = results;
      if (tasksResult.status === "fulfilled") setSummaries(tasksResult.value as TaskSummary[]);
      if (routinesResult.status === "fulfilled") setRoutines(routinesResult.value as Routine[]);
      if (botsResult?.status === "fulfilled") {
        let profiles = botsResult.value as Bot[];
        if (!profiles.length) {
          try {
            profiles = await api.starterBots();
          } catch (err) {
            if (alive) setError(errorMessage(err));
          }
        }
        if (alive) setBots(profiles);
      }
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") setError(errorMessage(failure.reason));
      if (initial && alive) setLoaded(true);
      polling = false;
    }
    void refresh(true);
    void api
      .getDocuments()
      .then((value) => {
        if (alive) setLibrary(value);
      })
      .catch((err) => {
        if (alive) setLibraryError(errorMessage(err));
      });
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
  }, [api]);

  const taskRevision = botTasks.map((task) => `${task.id}:${task.updated_at}`).join();
  useEffect(() => {
    let alive = true;
    const stale = botTasks.filter(
      (task) =>
        !detailCache.current[task.id] ||
        detailCache.current[task.id].updated_at !== task.updated_at,
    );
    void Promise.allSettled(stale.map((task) => api.getTask(task.id))).then((results) => {
      if (!alive) return;
      setDetails((current) => {
        const next = { ...current };
        for (const result of results)
          if (result.status === "fulfilled") {
            const task = result.value;
            if (!next[task.id] || next[task.id].updated_at <= task.updated_at) next[task.id] = task;
          }
        return next;
      });
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") setError(errorMessage(failure.reason));
    });
    return () => {
      alive = false;
    };
    // Only refetch details when the server reports a task change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, taskRevision, bot?.id]);

  const completedRevision = botTasks
    .filter((task) => task.status === "completed")
    .map((task) => task.id)
    .join();
  useEffect(() => {
    if (!bot) return;
    let alive = true;
    setMemoryError("");
    void api
      .getMemories(bot.id)
      .then((values) => {
        if (alive) setMemories({ bot: bot.id, values });
      })
      .catch((err) => {
        if (alive) setMemoryError(errorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, [api, bot?.id, completedRevision]);

  useEffect(() => {
    if (view.kind !== "task" || details[view.id]) return;
    let alive = true;
    void api
      .getTask(view.id)
      .then((task) => {
        if (alive) setDetails((current) => ({ ...current, [task.id]: task }));
      })
      .catch((err) => {
        if (alive) setError(errorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, [api, view, details]);
  useEffect(() => {
    if (!bot) return;
    try {
      localStorage.setItem(`axelyn:bot:${storageScope}`, bot.id);
    } catch {
      /* Private browsing can disable storage. */
    }
  }, [bot?.id, storageScope]);
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setMobileChat(false);
        search.current?.focus();
      }
      if (event.key === "Escape" && !editor && !documentsOpen) {
        setInspectorOpen(false);
        setHelp(false);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [editor, documentsOpen]);
  useEffect(() => {
    if (!replyTask) setReplyId(null);
  }, [replyTask?.id]);
  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = "auto";
      composer.current.style.height = `${Math.min(composer.current.scrollHeight, 150)}px`;
    }
  }, [goal]);

  function selectBot(id: string) {
    setSelected(id);
    setMobileChat(true);
    setGoal("");
    setReplyId(null);
    setView({ kind: "overview" });
    if (window.innerWidth < 1180) setInspectorOpen(false);
  }
  function inspect(next: InspectorView) {
    setView(next);
    setInspectorOpen(true);
  }
  async function action(id: string, work: () => Promise<void>) {
    if (busy) return;
    setBusy(id);
    setError("");
    try {
      await work();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }
  async function submit() {
    if (!bot || goal.trim().length < 3 || sending) return;
    const text = goal.trim();
    setSending(true);
    setError("");
    try {
      acceptTask(
        replyTask ? await api.resumeTask(replyTask.id, text) : await api.startTask(bot.id, text),
      );
      setGoal("");
      setReplyId(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }
  function updateDocument(document: UploadedDocument) {
    setLibrary(
      (current) =>
        current && {
          ...current,
          documents: [document, ...current.documents.filter((doc) => doc.id !== document.id)],
        },
    );
  }
  async function uploadFiles(files: File[]) {
    if (!files.length || uploading) return;
    setDocumentsOpen(true);
    setLibraryError(null);
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
        errors.push(`${file.name}: ${errorMessage(err)}`);
      }
    }
    setUploading(null);
    if (errors.length) setLibraryError(errors.join(" "));
  }
  async function documentAction(id: string, work: () => Promise<void>) {
    setBusyDocument(id);
    setLibraryError(null);
    try {
      await work();
    } catch (err) {
      setLibraryError(errorMessage(err));
    } finally {
      setBusyDocument(null);
    }
  }
  const visibleBots = bots.filter((item) =>
    `${item.name} ${item.role}`.toLowerCase().includes(query.toLowerCase()),
  );
  const activeCount = summaries.filter((task) => WORKING.has(task.status)).length;

  return (
    <main
      className={`bot-workspace ${mobileChat ? "mobile-chat" : ""} ${inspectorOpen ? "inspector-is-open" : ""}`}
    >
      <aside className="bot-sidebar" aria-label="Your bots">
        <header className="sidebar-brand">
          <a
            href="/"
            aria-label="Axelyn home"
            onClick={(event) => {
              event.preventDefault();
              setMobileChat(false);
              setQuery("");
            }}
          >
            <span className="brand-symbol">
              a<span />
            </span>
            <span>
              axelyn<span className="brand-dot">.</span>
            </span>
          </a>
          <button
            className="icon-button"
            aria-label="Create a bot"
            onClick={() => setEditor({ kind: "bot" })}
          >
            <Plus size={19} />
          </button>
        </header>
        <label className="bot-search">
          <Search size={15} />
          <input
            ref={search}
            aria-label="Search bots"
            placeholder="Search your bots"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query ? (
            <button aria-label="Clear search" onClick={() => setQuery("")}>
              <X size={12} />
            </button>
          ) : (
            <kbd>⌘ K</kbd>
          )}
        </label>
        <div className="roster-heading">
          <span>Your team</span>
          <span>{bots.length}</span>
        </div>
        <nav className="bot-roster">
          {!loaded ? (
            <div className="loading-bots">
              <Loader2 size={17} className="spin" />
              Opening your team…
            </div>
          ) : (
            visibleBots.map((item) => {
              const latest = summaries.find((task) => task.bot_id === item.id);
              const needsInput = summaries.some(
                (task) => task.bot_id === item.id && task.status === "needs_input",
              );
              return (
                <button
                  className={`bot-row ${bot?.id === item.id ? "selected" : ""}`}
                  aria-current={bot?.id === item.id ? "true" : undefined}
                  onClick={() => selectBot(item.id)}
                  key={item.id}
                >
                  <span className="roster-avatar">
                    <BotAvatar name={item.name} />
                    {latest && WORKING.has(latest.status) && <span className="working-dot" />}
                  </span>
                  <span className="bot-row-content">
                    <span className="bot-row-title">
                      <strong>{item.name}</strong>
                      <time>{latest ? timeLabel(latest.updated_at) : ""}</time>
                    </span>
                    <span className={`bot-row-preview ${needsInput ? "needs-attention" : ""}`}>
                      {needsInput
                        ? "Waiting for your reply"
                        : latest
                          ? `${STATUS[latest.status]} · ${latest.summary || latest.goal}`
                          : item.role}
                    </span>
                  </span>
                  {needsInput && <span className="unread-dot" />}
                </button>
              );
            })
          )}
          {loaded && !visibleBots.length && (
            <p className="empty-note">
              {bots.length ? "No bots match your search." : "Your team is ready to begin."}
            </p>
          )}
          <button className="add-bot-row" onClick={() => setEditor({ kind: "bot" })}>
            <span>
              <Plus size={17} />
            </span>
            Create a bot
          </button>
        </nav>
        <footer className="sidebar-footer">
          <div className="team-status">
            <span className={activeCount ? "live-dot" : "idle-dot"} />
            {activeCount
              ? `${activeCount} ${activeCount === 1 ? "task" : "tasks"} in progress`
              : "Your team is ready"}
          </div>
          <button className="sidebar-link" onClick={() => setDocumentsOpen(true)}>
            <BookOpen size={17} />
            Knowledge<span>{library?.documents.length || ""}</span>
          </button>
          <div className="account-row">
            {accountMenu}
            <span>
              <strong>My workspace</strong>
              <small>Personal account</small>
            </span>
            <button
              className="icon-button"
              aria-label="How autopilot works"
              onClick={() => {
                setHelp(!help);
                setMobileChat(true);
              }}
            >
              <CircleHelp size={17} />
            </button>
          </div>
        </footer>
      </aside>
      <section
        className="conversation-panel"
        aria-label={bot ? `Conversation with ${bot.name}` : "Bot conversation"}
      >
        <header className="conversation-header">
          <button
            className="icon-button mobile-back"
            aria-label="Back to your team"
            onClick={() => setMobileChat(false)}
          >
            <ArrowLeft size={20} />
          </button>
          {bot && (
            <>
              <BotAvatar name={bot.name} size="small" />
              <button className="conversation-title" onClick={() => inspect({ kind: "overview" })}>
                <strong>{bot.name}</strong>
                <span>
                  Autopilot <ChevronDown size={11} />
                </span>
              </button>
            </>
          )}
          <div className="header-actions">
            <button
              className="icon-button"
              aria-label="Bot details and routines"
              aria-expanded={inspectorOpen}
              onClick={() => {
                setView({ kind: "overview" });
                setInspectorOpen(!inspectorOpen);
              }}
            >
              <Info size={19} />
            </button>
          </div>
        </header>
        {error && (
          <div className="workspace-error" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={14} />
            </button>
          </div>
        )}
        {help && (
          <div className="autopilot-help">
            <button className="icon-button" aria-label="Close help" onClick={() => setHelp(false)}>
              <X size={15} />
            </button>
            <strong>Give a goal. Come back to the work.</strong>
            <p>
              Your bot searches the knowledge library, writes a document, and checks that it saved.
              Runs continue in the background. Routines repeat on your schedule, and memory carries
              preferences between tasks.
            </p>
            <p>
              Add your documents in Knowledge. The included Sentral Ops SOPs are fictional sample
              data. Email and calendar actions need a future integration.
            </p>
          </div>
        )}
        {bot ? (
          <TaskConversation
            bot={bot}
            tasks={botTasks}
            details={details}
            busy={busy}
            onSuggest={(text) => {
              setGoal(text);
              composer.current?.focus();
            }}
            onArtifact={(task, artifact) => inspect({ kind: "artifact", task, artifact })}
            onTask={(id) => inspect({ kind: "task", id })}
            onCancel={(id) => void action(id, async () => acceptTask(await api.cancelTask(id)))}
            onReply={(id) => {
              setReplyId(id);
              composer.current?.focus();
            }}
            onRetry={(id) =>
              void action(id, async () =>
                acceptTask(await api.resumeTask(id, "Retry the task using the available context.")),
              )
            }
          />
        ) : (
          <div className="workspace-loading" role="status">
            {loaded ? (
              <>
                <p>Your workspace couldn’t load.</p>
                <button className="button secondary" onClick={() => location.reload()}>
                  Try again
                </button>
              </>
            ) : (
              <>
                <Loader2 size={22} className="spin" />
                <p>Getting your team ready…</p>
              </>
            )}
          </div>
        )}
        <div className="composer-area">
          {replyTask && (
            <div className="reply-context">
              <span>Replying to: {replyTask.goal}</span>
              <button aria-label="Start a new task instead" onClick={() => setReplyId(null)}>
                <X size={13} />
              </button>
            </div>
          )}
          <form
            className="task-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <button
              type="button"
              className="composer-attach"
              aria-label="Open knowledge library"
              onClick={() => setDocumentsOpen(true)}
            >
              <Plus size={20} />
            </button>
            <textarea
              ref={composer}
              aria-label={replyTask ? "Reply to the bot" : "Give your bot a task"}
              placeholder={
                replyTask
                  ? "Add the information your bot needs…"
                  : `Give ${bot?.name ?? "your bot"} a task…`
              }
              value={goal}
              maxLength={4000}
              rows={1}
              disabled={sending || !bot}
              onChange={(event) => setGoal(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void submit();
                }
              }}
            />
            <button
              className="send-task"
              aria-label={sending ? "Starting task" : replyTask ? "Send reply" : "Start task"}
              disabled={sending || !bot || goal.trim().length < 3}
            >
              {sending ? <Loader2 size={17} className="spin" /> : <ArrowUp size={18} />}
            </button>
          </form>
          <p className="composer-caption">
            {sending
              ? "Handing it over…"
              : replyTask
                ? "Your reply continues the same task."
                : "Assign the task. Your bot takes it from here."}
          </p>
        </div>
      </section>
      {bot && inspectorOpen && (
        <>
          <button
            className="inspector-backdrop"
            aria-label="Close details"
            onClick={() => setInspectorOpen(false)}
          />
          <WorkspaceInspector
            bot={bot}
            view={view}
            onView={setView}
            onClose={() => setInspectorOpen(false)}
            memories={memories.bot === bot.id ? memories.values : []}
            memoryLoading={memories.bot !== bot.id && !memoryError}
            memoryError={memoryError}
            routines={routines.filter((routine) => routine.bot_id === bot.id)}
            task={view.kind === "task" ? details[view.id] : undefined}
            busy={busy}
            documentCount={library?.documents.filter((doc) => doc.status === "indexed").length ?? 0}
            onEditBot={() => setEditor({ kind: "bot", bot })}
            onMemory={(memory) => setEditor({ kind: "memory", memory })}
            onForget={(memory) =>
              void action(memory.id, async () => {
                await api.forgetMemory(bot.id, memory.id);
                setMemories((current) => ({
                  ...current,
                  values: current.values.filter((item) => item.id !== memory.id),
                }));
              })
            }
            onRoutine={(routine) => setEditor({ kind: "routine", routine })}
            onToggle={(routine) =>
              void action(routine.id, async () => {
                const {
                  bot_id,
                  name,
                  goal,
                  completion_criteria,
                  recurrence,
                  timezone,
                  local_time,
                  weekday,
                } = routine;
                const saved = await api.saveRoutine(
                  {
                    bot_id,
                    name,
                    goal,
                    completion_criteria,
                    recurrence,
                    timezone,
                    local_time,
                    weekday,
                    enabled: !routine.enabled,
                  },
                  routine.id,
                );
                setRoutines((current) =>
                  current.map((item) => (item.id === saved.id ? saved : item)),
                );
              })
            }
            onRun={(routine) =>
              void action(routine.id, async () => {
                acceptTask(await api.runRoutine(routine.id));
                if (window.innerWidth < 1180) setInspectorOpen(false);
              })
            }
            onDeleteRoutine={(routine) =>
              void action(routine.id, async () => {
                await api.deleteRoutine(routine.id);
                setRoutines((current) => current.filter((item) => item.id !== routine.id));
              })
            }
            onKnowledge={() => setDocumentsOpen(true)}
          />
        </>
      )}
      <input
        hidden
        ref={fileInput}
        type="file"
        accept=".pdf,.md,application/pdf,text/markdown"
        multiple
        onChange={(event) => {
          void uploadFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <DocumentPanel
        open={documentsOpen}
        library={library}
        uploading={uploading}
        busyId={busyDocument}
        error={libraryError}
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
      {editor?.kind === "bot" && (
        <BotEditor
          bot={editor.bot}
          onClose={() => setEditor(null)}
          onSave={async (data) => {
            const saved = await api.saveBot(data, editor.bot?.id);
            setBots((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
            selectBot(saved.id);
            setEditor(null);
          }}
        />
      )}
      {bot && editor?.kind === "memory" && (
        <MemoryEditor
          memory={editor.memory}
          onClose={() => setEditor(null)}
          onSave={async (key, value) => {
            const saved = await api.saveMemory(bot.id, key, value);
            setMemories((current) => ({
              bot: bot.id,
              values: [saved, ...current.values.filter((item) => item.id !== saved.id)],
            }));
            setEditor(null);
          }}
        />
      )}
      {bot && editor?.kind === "routine" && (
        <RoutineEditor
          bot={bot}
          routine={editor.routine}
          onClose={() => setEditor(null)}
          onSave={async (data) => {
            const saved = await api.saveRoutine(data, editor.routine?.id);
            setRoutines((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
            setEditor(null);
          }}
        />
      )}
    </main>
  );
}
