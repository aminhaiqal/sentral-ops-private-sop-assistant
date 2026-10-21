import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Check,
  FileText,
  Loader2,
  RotateCw,
  Square,
} from "lucide-react";
import type { Artifact, Bot, Task, TaskSummary } from "../types";
import BotAvatar from "./BotAvatar";
import { activityLabel, dayLabel, STATUS, timeLabel, WORKING } from "../workspace";

const SUGGESTIONS = [
  [
    "Prepare an operations briefing",
    "Prepare a concise operations briefing from the knowledge library. Include the key policies, responsibilities and escalation paths, with citations.",
  ],
  [
    "Create a delivery checklist",
    "Create a practical checklist for handling a delayed delivery, based on the knowledge library. Include who to contact and when to escalate.",
  ],
  [
    "Draft a customer response guide",
    "Create a customer response playbook for refund requests using the policies in the knowledge library. Include response drafts and the approval process.",
  ],
];

export default function TaskConversation({
  bot,
  tasks,
  details,
  onSuggest,
  onArtifact,
  onTask,
  onCancel,
  onReply,
  onRetry,
  busy,
}: {
  bot: Bot;
  tasks: TaskSummary[];
  details: Record<string, Task>;
  onSuggest: (goal: string) => void;
  onArtifact: (task: Task, artifact: Artifact) => void;
  onTask: (id: string) => void;
  onCancel: (id: string) => void;
  onReply: (id: string) => void;
  onRetry: (id: string) => void;
  busy: string | null;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  useEffect(() => {
    nearBottom.current = true;
    scroll.current?.scrollTo({ top: scroll.current.scrollHeight });
  }, [bot.id]);
  const revision = tasks
    .map(
      (task) =>
        `${task.id}:${task.updated_at}:${details[task.id]?.events.length}:${details[task.id]?.artifacts.length}`,
    )
    .join();
  useEffect(() => {
    if (nearBottom.current)
      scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: "smooth" });
  }, [revision]);
  return (
    <div
      className="conversation-scroll"
      ref={scroll}
      onScroll={(e) => {
        const el = e.currentTarget;
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
      }}
    >
      {!tasks.length ? (
        <div className="welcome-conversation">
          <div className="day-divider">Today</div>
          <div className="message assistant-message">
            <BotAvatar name={bot.name} size="small" />
            <div className="message-content">
              <div className="bubble welcome-bubble">
                <p>Hey, I’m your {bot.name.toLowerCase()}.</p>
                <p>
                  {bot.role} Give me a task and I’ll work through it, save the result, and ask if I
                  need anything.
                </p>
              </div>
              <span className="message-meta">Ready when you are</span>
            </div>
          </div>
          <div className="suggested-tasks">
            <span>A FEW THINGS I CAN TAKE OFF YOUR PLATE</span>
            {SUGGESTIONS.map(([label, goal]) => (
              <button key={label} onClick={() => onSuggest(goal)}>
                {label}
                <ArrowUpRight size={15} />
              </button>
            ))}
          </div>
          <div className="knowledge-note">
            <FileText size={14} />
            <span>I work from your documents. Add your own in Knowledge.</span>
          </div>
        </div>
      ) : (
        <div className="task-thread">
          {tasks.map((summary, index) => {
            const task = details[summary.id];
            const exchange =
              task?.events.filter(
                (event) => event.kind === "needs_input" || event.kind === "user_input",
              ) ?? [];
            const activity = task?.events
              .filter((event) => event.kind !== "user_input")
              .slice(-1)[0];
            return (
              <article className="task-exchange" key={summary.id}>
                {(index === 0 ||
                  dayLabel(summary.created_at) !== dayLabel(tasks[index - 1].created_at)) && (
                  <div className="day-divider">{dayLabel(summary.created_at)}</div>
                )}
                <div className="message user-message">
                  <div className="message-content">
                    <div className="bubble">{summary.goal}</div>
                    <span className="message-meta">
                      {summary.routine_id ? "Scheduled task · " : ""}
                      {timeLabel(summary.created_at)}
                    </span>
                  </div>
                </div>
                {exchange.map((event, i) => (
                  <div
                    className={`message ${event.kind === "user_input" ? "user-message" : "assistant-message"}`}
                    key={`${event.at}-${i}`}
                  >
                    {event.kind !== "user_input" && <BotAvatar name={bot.name} size="small" />}
                    <div className="message-content">
                      <div className="bubble">{event.detail}</div>
                      <span className="message-meta">{timeLabel(event.at)}</span>
                    </div>
                  </div>
                ))}
                <div className="message assistant-message">
                  <BotAvatar name={bot.name} size="small" />
                  <div className="message-content">
                    <div className={`bubble result-bubble state-${summary.status}`}>
                      {WORKING.has(summary.status) ? (
                        <>
                          <div className="run-state">
                            <Loader2 className="spin" size={14} />
                            {summary.status === "queued" ? "On my list." : "I’m on it."}
                          </div>
                          <p className="run-description">
                            {summary.status === "queued"
                              ? "I’ll start as soon as the worker is available."
                              : "I’ll research your documents and save the finished work here. You can leave this page."}
                          </p>
                          {activity && summary.status === "running" && (
                            <button className="activity-link" onClick={() => onTask(summary.id)}>
                              {activityLabel(activity.kind, activity.detail)}
                              <ArrowUpRight size={12} />
                            </button>
                          )}
                        </>
                      ) : summary.status === "completed" ? (
                        <>
                          <div className="run-state success">
                            <Check size={14} />
                            Done
                          </div>
                          <div className="markdown">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {summary.summary ||
                                "Your document is ready. Open it below to review the result."}
                            </ReactMarkdown>
                          </div>
                        </>
                      ) : summary.status === "needs_input" ? (
                        <>
                          <div className="run-state attention">
                            A quick question before I continue
                          </div>
                          {!exchange.length && <p>{summary.exception}</p>}
                          <button className="text-action" onClick={() => onReply(summary.id)}>
                            Reply to this task <ArrowUpRight size={13} />
                          </button>
                        </>
                      ) : (
                        <>
                          <div className="run-state">{STATUS[summary.status]}</div>
                          <p>
                            {summary.status === "cancelled"
                              ? "This task was stopped. Any saved drafts are kept below."
                              : summary.exception || "The task stopped before it could finish."}
                          </p>
                          {summary.status === "failed" && (
                            <button
                              className="text-action"
                              disabled={busy === summary.id}
                              onClick={() => onRetry(summary.id)}
                            >
                              <RotateCw size={13} />
                              Retry task
                            </button>
                          )}
                          {summary.status === "limit_reached" && (
                            <p className="field-note">Try a smaller task to start a fresh run.</p>
                          )}
                        </>
                      )}
                    </div>
                    {task?.artifacts.map((artifact) => (
                      <button
                        key={artifact.id}
                        className="artifact-tile"
                        onClick={() => onArtifact(task, artifact)}
                      >
                        <span className="artifact-file">
                          <FileText size={21} />
                          <small>MD</small>
                        </span>
                        <span>
                          <strong>{artifact.title}</strong>
                          <small>
                            {summary.status === "completed" ? "Document ready" : "Draft"} · Markdown
                          </small>
                        </span>
                        <ArrowDownToLine size={16} />
                      </button>
                    ))}
                    <div className="message-meta task-meta">
                      <span>{timeLabel(summary.updated_at)}</span>
                      <button onClick={() => onTask(summary.id)}>View activity</button>
                      {WORKING.has(summary.status) && (
                        <button disabled={busy === summary.id} onClick={() => onCancel(summary.id)}>
                          <Square size={9} />
                          Stop
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
