import { Check, Download, Loader2, RotateCw, Square } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Task } from "../types";
import { activityLabel, saveBlob, STATUS, WORKING } from "../workspace";

export default function TaskResult({
  task,
  busy,
  onCancel,
  onRetry,
}: {
  task: Task;
  busy: boolean;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const working = WORKING.has(task.status);
  const latest = task.events.filter((event) => event.kind !== "user_input").slice(-1)[0];
  return (
    <section className="task-result" aria-label="Task result">
      <div className="result-status" role="status" aria-live="polite">
        <span className={task.status === "completed" ? "complete" : ""}>
          {working ? (
            <Loader2 size={16} className="spin" />
          ) : task.status === "completed" ? (
            <Check size={16} />
          ) : null}
          {STATUS[task.status]}
        </span>
        {working && (
          <button onClick={onCancel} disabled={busy}>
            <Square size={12} />
            Stop
          </button>
        )}
        {task.status === "failed" && (
          <button onClick={onRetry} disabled={busy}>
            <RotateCw size={14} />
            Retry
          </button>
        )}
      </div>
      {working && (
        <p>{latest ? activityLabel(latest.kind, latest.detail) : "Preparing your document…"}</p>
      )}
      {task.exception && <p className="task-exception">{task.exception}</p>}
      {task.status === "limit_reached" && <p>Start a smaller task to continue with a fresh run.</p>}
      {task.status === "cancelled" && <p>Any saved drafts are kept below.</p>}
      {task.summary && (
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{task.summary}</ReactMarkdown>
        </div>
      )}
      {task.events
        .filter((event) => event.kind === "user_input")
        .map((event, index) => (
          <blockquote className="task-reply" key={index}>
            {event.detail}
          </blockquote>
        ))}
      {task.artifacts.map((artifact) => (
        <article className="artifact" key={artifact.id}>
          <header className="section-heading">
            <h2>
              {artifact.title}
              {task.status !== "completed" && <small>Draft</small>}
            </h2>
            <button
              aria-label={`Download ${artifact.title}`}
              onClick={() => {
                const filename =
                  artifact.title
                    .replace(/[^a-z0-9\s-]/gi, "")
                    .trim()
                    .slice(0, 100) || "document";
                saveBlob(
                  new Blob([artifact.content], { type: "text/markdown;charset=utf-8" }),
                  `${filename}.md`,
                );
              }}
            >
              <Download size={15} />
              <span className="download-label">Download</span>
            </button>
          </header>
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
          </div>
        </article>
      ))}
      {!!task.sources.length && (
        <details className="result-details">
          <summary>Sources · {task.sources.length}</summary>
          <ol className="sources">
            {task.sources.map((source) => (
              <li key={source.citation}>
                <strong>
                  [{source.citation}] {source.title}
                </strong>
                <p>{source.excerpt}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
      {!!task.events.length && (
        <details className="result-details">
          <summary>Activity</summary>
          <ol className="activity">
            {task.events.map((event, index) => (
              <li key={index}>{activityLabel(event.kind, event.detail)}</li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
