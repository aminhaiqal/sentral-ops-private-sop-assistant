import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  BookOpen,
  Brain,
  CalendarClock,
  Check,
  ChevronRight,
  Clock3,
  Download,
  FileText,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import type { Artifact, Bot, Memory, Routine, Task } from "../types";
import BotAvatar from "./BotAvatar";
import { activityLabel, saveBlob, STATUS } from "../workspace";

export type InspectorView =
  | { kind: "overview" }
  | { kind: "memory" }
  | { kind: "task"; id: string }
  | { kind: "artifact"; task: Task; artifact: Artifact };

export default function WorkspaceInspector({
  bot,
  view,
  onView,
  onClose,
  memories,
  memoryLoading,
  memoryError,
  routines,
  task,
  onEditBot,
  onMemory,
  onForget,
  onRoutine,
  onToggle,
  onRun,
  onDeleteRoutine,
  onKnowledge,
  busy,
  documentCount,
}: {
  bot: Bot;
  view: InspectorView;
  onView: (view: InspectorView) => void;
  onClose: () => void;
  memories: Memory[];
  memoryLoading: boolean;
  memoryError: string;
  routines: Routine[];
  task?: Task;
  onEditBot: () => void;
  onMemory: (memory?: Memory) => void;
  onForget: (memory: Memory) => void;
  onRoutine: (routine?: Routine) => void;
  onToggle: (routine: Routine) => void;
  onRun: (routine: Routine) => void;
  onDeleteRoutine: (routine: Routine) => void;
  onKnowledge: () => void;
  busy: string | null;
  documentCount: number;
}) {
  const [tab, setTab] = useState<"preference" | "outcome">("preference");
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (window.innerWidth >= 1180) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  const title =
    view.kind === "artifact"
      ? "Document"
      : view.kind === "task"
        ? "Task activity"
        : view.kind === "memory"
          ? "Memory"
          : "Bot details";
  return (
    <aside
      ref={panel}
      role={window.innerWidth < 1180 ? "dialog" : undefined}
      aria-modal={window.innerWidth < 1180 ? true : undefined}
      onKeyDown={(event) => {
        if (window.innerWidth >= 1180 || event.key !== "Tab") return;
        const controls = Array.from(
          panel.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), a[href], summary, [tabindex="0"]',
          ) ?? [],
        );
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      className={`workspace-inspector ${view.kind === "artifact" ? "artifact-inspector" : ""}`}
      aria-label={title}
    >
      <header className="inspector-header">
        <div>
          {view.kind !== "overview" && (
            <button
              className="icon-button"
              aria-label="Back to bot details"
              onClick={() => onView({ kind: "overview" })}
            >
              <ArrowLeft size={17} />
            </button>
          )}
          <h2>{title}</h2>
        </div>
        <button className="icon-button" aria-label="Close bot details" onClick={onClose}>
          <X size={17} />
        </button>
      </header>
      <div className="inspector-scroll">
        {view.kind === "overview" && (
          <>
            <div className="bot-profile">
              <BotAvatar name={bot.name} size="large" />
              <h2>{bot.name}</h2>
              <p>{bot.role}</p>
              <button className="subtle-button" onClick={onEditBot}>
                <Pencil size={12} />
                Edit bot
              </button>
            </div>
            {bot.instructions && (
              <section className="inspector-section">
                <h3>Instructions</h3>
                <p className="instructions-text">{bot.instructions}</p>
              </section>
            )}
            <section className="inspector-section">
              <div className="section-label">
                <h3>Routines</h3>
                <button
                  className="icon-button small"
                  aria-label="Create routine"
                  onClick={() => onRoutine()}
                >
                  <Plus size={16} />
                </button>
              </div>
              {!routines.length ? (
                <button className="empty-routine" onClick={() => onRoutine()}>
                  <CalendarClock size={19} />
                  <span>
                    <strong>Put a task on autopilot</strong>
                    <small>Set a daily or weekly routine.</small>
                  </span>
                  <Plus size={14} />
                </button>
              ) : (
                routines.map((routine) => (
                  <div className="routine-row" key={routine.id}>
                    <span className={`routine-indicator ${routine.enabled ? "enabled" : ""}`}>
                      {routine.enabled ? <Check size={10} /> : <Pause size={9} />}
                    </span>
                    <div>
                      <button className="routine-name" onClick={() => onRoutine(routine)}>
                        {routine.name}
                      </button>
                      <p>
                        {routine.enabled
                          ? `${routine.recurrence === "weekdays" ? "Weekdays" : routine.recurrence === "daily" ? "Every day" : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][routine.weekday]} at ${routine.local_time}`
                          : "Paused"}
                      </p>
                      <small className="routine-zone">{routine.timezone.replace(/_/g, " ")}</small>
                      <div className="routine-actions">
                        <button disabled={busy === routine.id} onClick={() => onRun(routine)}>
                          <Play size={10} />
                          Run now
                        </button>
                        <button disabled={busy === routine.id} onClick={() => onToggle(routine)}>
                          {routine.enabled ? "Pause" : "Resume"}
                        </button>
                        <button
                          className="danger-icon"
                          disabled={busy === routine.id}
                          aria-label={`Delete ${routine.name}`}
                          onClick={() => onDeleteRoutine(routine)}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                      {routine.enabled && (
                        <small className="next-run">
                          Next:{" "}
                          {new Date(routine.next_run_at).toLocaleString([], {
                            weekday: "short",
                            hour: "numeric",
                            minute: "2-digit",
                            timeZone: routine.timezone,
                          })}
                        </small>
                      )}
                    </div>
                  </div>
                ))
              )}
            </section>
            <section className="inspector-section">
              <h3>Context</h3>
              <button className="context-row" onClick={onKnowledge}>
                <span className="context-icon">
                  <BookOpen size={17} />
                </span>
                <span>
                  <strong>Knowledge</strong>
                  <small>
                    {documentCount
                      ? `${documentCount} of your documents indexed`
                      : "Add your documents"}
                  </small>
                </span>
                <ChevronRight size={14} />
              </button>
              <button className="context-row" onClick={() => onView({ kind: "memory" })}>
                <span className="context-icon">
                  <Brain size={17} />
                </span>
                <span>
                  <strong>Memory</strong>
                  <small>
                    {memoryLoading
                      ? "Loading…"
                      : memoryError
                        ? "Couldn’t load memory"
                        : `${memories.filter((m) => m.kind === "preference").length} preferences · ${memories.filter((m) => m.kind === "outcome").length} past results`}
                  </small>
                </span>
                <ChevronRight size={14} />
              </button>
            </section>
            <p className="inspector-footnote">
              This bot researches documents and saves deliverables. Email, calendar and browser
              actions aren’t connected yet.
            </p>
          </>
        )}
        {view.kind === "memory" && (
          <div className="memory-view">
            <p className="panel-description">What {bot.name} remembers between tasks.</p>
            <div className="memory-tabs">
              <button
                className={tab === "preference" ? "selected" : ""}
                onClick={() => setTab("preference")}
              >
                Preferences
              </button>
              <button
                className={tab === "outcome" ? "selected" : ""}
                onClick={() => setTab("outcome")}
              >
                Past results
              </button>
            </div>
            {tab === "preference" && (
              <button className="add-memory" onClick={() => onMemory()}>
                <Plus size={15} />
                Add a preference
              </button>
            )}
            {memoryError ? (
              <p className="panel-error" role="alert">
                {memoryError}
              </p>
            ) : memoryLoading ? (
              <p className="empty-note">Loading memory…</p>
            ) : !memories.filter((m) => m.kind === tab).length ? (
              <div className="memory-empty">
                <Brain size={28} />
                <p>
                  {tab === "preference"
                    ? "A little context goes a long way."
                    : "The first result starts here."}
                </p>
                <span>
                  {tab === "preference"
                    ? "Save your writing style, preferred format, or other instructions."
                    : "Completed tasks leave a record of what was saved. Future tasks can recall these records."}
                </span>
              </div>
            ) : (
              memories
                .filter((m) => m.kind === tab)
                .map((memory) => (
                  <div className="memory-row" key={memory.id}>
                    <div>
                      <strong>
                        {memory.kind === "preference"
                          ? memory.key.replace(/_/g, " ")
                          : "Completed work"}
                      </strong>
                      <button
                        className="icon-button small"
                        disabled={busy === memory.id}
                        aria-label={`Forget ${memory.key}`}
                        onClick={() => onForget(memory)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <p>{memory.value}</p>
                    <div className="memory-row-footer">
                      <small>
                        {memory.kind === "preference"
                          ? "Saved by you"
                          : "Saved from a completed task"}
                      </small>
                      {memory.kind === "preference" ? (
                        <button onClick={() => onMemory(memory)}>Edit</button>
                      ) : (
                        memory.source_task_id && (
                          <button
                            onClick={() => onView({ kind: "task", id: memory.source_task_id! })}
                          >
                            View task
                          </button>
                        )
                      )}
                    </div>
                  </div>
                ))
            )}
          </div>
        )}
        {view.kind === "task" &&
          (!task ? (
            <p className="empty-note" role="status">
              Loading task activity…
            </p>
          ) : (
            <div className="task-activity">
              <span className={`status-pill status-${task.status}`}>{STATUS[task.status]}</span>
              <h3>{task.goal}</h3>
              <p className="activity-criteria">{task.completion_criteria}</p>
              <ol>
                {task.events.map((event, i) => (
                  <li key={i}>
                    <span className="timeline-dot" />
                    <div>
                      <strong>{activityLabel(event.kind, event.detail)}</strong>
                      {event.kind === "needs_input" && <p>{event.detail}</p>}
                      <time>
                        {new Date(event.at).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </time>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="activity-budget">
                <Clock3 size={13} />
                {task.turns} / {task.max_turns} steps · {task.tokens.toLocaleString()} tokens
              </p>
            </div>
          ))}
        {view.kind === "artifact" && (
          <div className="artifact-preview">
            <span className="preview-file-icon">
              <FileText size={26} />
            </span>
            <h2>{view.artifact.title}</h2>
            <p className="artifact-subtitle">
              {view.task.status === "completed" ? "Saved document" : "Draft · task not completed"} ·
              Markdown
            </p>
            <button
              className="button secondary download-artifact"
              onClick={() =>
                saveBlob(
                  new Blob([view.artifact.content], { type: "text/markdown;charset=utf-8" }),
                  `${view.artifact.title.replace(/[^a-zA-Z0-9 -]/g, "").trim() || "document"}.md`,
                )
              }
            >
              <Download size={14} />
              Download
            </button>
            <div className="markdown artifact-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{view.artifact.content}</ReactMarkdown>
            </div>
            {view.task.sources.length > 0 && (
              <div className="artifact-sources">
                <h3>Sources used</h3>
                {view.task.sources.map((source) => (
                  <details key={source.citation}>
                    <summary>
                      {source.citation} {source.title}
                    </summary>
                    <p>{source.excerpt}</p>
                  </details>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
