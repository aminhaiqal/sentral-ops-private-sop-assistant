import { useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  RotateCw,
  Square,
  XCircle,
} from "lucide-react";
import type { OutreachDraft, Prospect, StudioRun } from "./types";
import { saveBlob } from "../workspace";
import { SKILL_ICONS } from "./StudioForm";

export const RUN_LABELS = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};
export function RunStatus({ status }: { status: keyof typeof RUN_LABELS }) {
  return (
    <span className={`studio-status studio-status-${status}`}>
      {status === "running" ? (
        <Loader2 size={12} className="spin" />
      ) : status === "completed" ? (
        <Check size={12} />
      ) : status === "failed" ? (
        <XCircle size={12} />
      ) : (
        <span />
      )}
      {RUN_LABELS[status]}
    </span>
  );
}
export function dateTime(value: string | null) {
  return value
    ? new Date(value).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
}

export default function ExecutionDetails({
  run,
  busy,
  onBack,
  onCancel,
  onRetry,
  onRunAgain,
  canRunAgain,
}: {
  run: StudioRun;
  busy: boolean;
  onBack: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onRunAgain: () => void;
  canRunAgain: boolean;
}) {
  const [tab, setTab] = useState<"results" | "activity" | "configuration">("results");
  const [stepId, setStepId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState("");
  const active = run.status === "queued" || run.status === "running";
  const saveStep = run.steps.find(
    (step) => step.skill_id === "save" && step.status === "completed",
  );
  const prospects =
    run.result?.prospects ?? (saveStep?.output?.prospects as Prospect[] | undefined) ?? [];
  const drafts =
    run.result?.drafts ??
    (run.steps.find((step) => step.skill_id === "draft")?.output?.drafts as
      OutreachDraft[] | undefined) ??
    [];
  const step = run.steps.find((item) => item.skill_id === stepId);
  const totals = run.usage;
  const duration =
    run.started_at && run.completed_at
      ? Math.max(0, Math.round((Date.parse(run.completed_at) - Date.parse(run.started_at)) / 1000))
      : null;
  async function copy(draft: OutreachDraft) {
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopyState(draft.prospect_id);
      setTimeout(() => setCopyState(""), 2000);
    } catch {
      setCopyState("Clipboard unavailable. Select the draft text to copy it.");
    }
  }
  return (
    <div className="studio-execution">
      <button className="studio-back" onClick={onBack}>
        <ArrowLeft size={15} />
        Execution history
      </button>
      <div className="studio-page-heading">
        <div>
          <span className="studio-eyebrow">EXECUTION DETAILS</span>
          <h1>{run.bot_name}</h1>
          <p>
            Run <code>{run.id.slice(0, 8)}</code> · {dateTime(run.created_at)}
          </p>
        </div>
        <div className="studio-heading-actions">
          <RunStatus status={run.status} />
          {active ? (
            <button className="button secondary" onClick={onCancel} disabled={busy}>
              <Square size={12} />
              Stop run
            </button>
          ) : (
            <>
              <button
                className="button secondary"
                onClick={() =>
                  saveBlob(
                    new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }),
                    `axelyn-run-${run.id.slice(0, 8)}.json`,
                  )
                }
              >
                <Download size={14} />
                Export
              </button>
              <button
                className="button primary"
                onClick={onRunAgain}
                disabled={busy || !canRunAgain}
                title={
                  canRunAgain
                    ? "Start a new execution"
                    : "This bot is disabled or deleted. Create a new bot to execute this job again."
                }
              >
                Run again
                <ArrowUpRight size={14} />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="studio-run-metrics">
        <div>
          <span>Started</span>
          <strong>{dateTime(run.started_at)}</strong>
        </div>
        <div>
          <span>Completed</span>
          <strong>
            {dateTime(run.completed_at)}
            {duration !== null ? ` · ${duration}s` : ""}
          </strong>
        </div>
        <div>
          <span>AI tokens</span>
          <strong>
            {(totals.input_tokens + totals.output_tokens).toLocaleString()}
            {totals.unreported_llm_calls > 0 ? " + unreported calls" : ""}
          </strong>
          <small>
            {totals.input_tokens.toLocaleString()} in · {totals.output_tokens.toLocaleString()} out
          </small>
        </div>
        <div>
          <span>Estimated AI cost</span>
          <strong>
            {totals.estimated_cost_usd !== null
              ? `$${totals.estimated_cost_usd.toFixed(4)}`
              : "Rates not configured"}
          </strong>
          <small>
            {totals.api_calls} API calls · {totals.llm_calls} AI calls
          </small>
        </div>
      </div>
      {run.error && (
        <div className="studio-run-error" role="alert">
          <XCircle size={18} />
          <div>
            <strong>{run.error.code.replace(/_/g, " ")}</strong>
            <p>{run.error.message}</p>
            {run.error.retryable && (
              <button className="studio-text-button" onClick={onRetry} disabled={busy}>
                <RotateCw size={13} />
                Retry incomplete steps
              </button>
            )}
          </div>
        </div>
      )}
      <div className="studio-run-layout">
        <aside className="studio-step-list">
          <h2>Skill execution</h2>
          {run.steps.map((item) => {
            const Icon = SKILL_ICONS[item.skill_id];
            return (
              <button
                key={item.skill_id}
                className={`studio-step studio-step-${item.status} ${stepId === item.skill_id ? "selected" : ""}`}
                onClick={() => {
                  setStepId(item.skill_id);
                  setTab("activity");
                }}
              >
                <Icon size={18} />
                <span>
                  <strong>{item.skill_id[0].toUpperCase() + item.skill_id.slice(1)}</strong>
                  <small>
                    {item.status === "pending" ? (active ? "Waiting" : "Not run") : item.status}
                    {item.attempts
                      ? ` · ${item.attempts} ${item.attempts === 1 ? "attempt" : "attempts"}`
                      : ""}
                  </small>
                </span>
                {item.status === "completed" ? (
                  <CheckCircle2 size={16} />
                ) : item.status === "running" ? (
                  <Loader2 size={15} className="spin" />
                ) : item.status === "failed" ? (
                  <XCircle size={16} />
                ) : (
                  <Circle size={14} />
                )}
              </button>
            );
          })}
          <div className="studio-limit-note">
            <strong>Run limits</strong>
            <p>
              {run.limits.max_steps} steps · {run.limits.max_api_calls} API calls ·{" "}
              {run.limits.max_tokens.toLocaleString()} token budget · {run.limits.timeout_seconds}s
            </p>
            {totals.unreported_llm_calls > 0 && (
              <p>Timed-out or interrupted AI calls retain a conservative budget charge.</p>
            )}
          </div>
        </aside>
        <section className="studio-run-content">
          <div className="studio-result-tabs">
            <button
              className={tab === "results" ? "selected" : ""}
              onClick={() => {
                setTab("results");
                setStepId(null);
              }}
            >
              Results <span>{prospects.length}</span>
            </button>
            <button
              className={tab === "activity" ? "selected" : ""}
              onClick={() => setTab("activity")}
            >
              Activity & logs
            </button>
            <button
              className={tab === "configuration" ? "selected" : ""}
              onClick={() => setTab("configuration")}
            >
              Run configuration
            </button>
          </div>
          {tab === "results" && (
            <>
              <div className="studio-result-intro">
                <h2>
                  {run.result
                    ? "Research results"
                    : prospects.length
                      ? "Saved results from an incomplete run"
                      : active
                        ? "Your bot is working"
                        : "No results saved"}
                </h2>
                <p>
                  {run.result?.summary ??
                    (active
                      ? "The worker will publish validated results here. You can leave this page and return later."
                      : "Review the step error and logs. Completed step outputs remain available in Activity.")}
                </p>
                {run.result && (
                  <span className={`studio-outcome ${run.result.criteria_met ? "met" : ""}`}>
                    {run.result.criteria_met ? <Check size={13} /> : <Circle size={13} />}{" "}
                    {run.result.criteria_met
                      ? "Minimum result count met"
                      : "Minimum result count not met"}
                  </span>
                )}
              </div>
              <div className="studio-prospect-list">
                {prospects.map((prospect) => {
                  const draft = drafts.find((item) => item.prospect_id === prospect.id);
                  return (
                    <article className="studio-prospect" key={prospect.id}>
                      <div className="studio-prospect-heading">
                        <div>
                          <h3>{prospect.company_name}</h3>
                          <a href={prospect.url} target="_blank" rel="noopener noreferrer">
                            {new URL(prospect.url).hostname}
                            <ExternalLink size={11} />
                          </a>
                        </div>
                        <span className="studio-fit-score">
                          {prospect.score}
                          <small>/100 fit</small>
                        </span>
                      </div>
                      <p>{prospect.reason}</p>
                      <details className="studio-evidence">
                        <summary>
                          Source evidence checked <ChevronRight size={12} />
                        </summary>
                        <blockquote>{prospect.evidence_quote}</blockquote>
                        <a href={prospect.url} target="_blank" rel="noopener noreferrer">
                          {prospect.source_title}
                          <ArrowUpRight size={12} />
                        </a>
                        <small>
                          Retrieved {dateTime(prospect.researched_at)}. Name and quote match the
                          search source; company facts still need your review.
                        </small>
                        {prospect.missing_information.length > 0 && (
                          <p>Missing information: {prospect.missing_information.join("; ")}</p>
                        )}
                      </details>
                      {draft && (
                        <div className="studio-outreach-draft">
                          <div>
                            <span>OUTREACH DRAFT · NOT SENT</span>
                            <button onClick={() => void copy(draft)}>
                              <Copy size={12} />
                              {copyState === prospect.id ? "Copied" : "Copy draft"}
                            </button>
                          </div>
                          <h4>{draft.subject}</h4>
                          <p>{draft.body}</p>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
              {copyState.includes("Clipboard") && (
                <p className="studio-error" role="alert">
                  {copyState}
                </p>
              )}
              <div className="studio-review-note">
                <CheckCircle2 size={16} />
                <div>
                  <strong>
                    {run.approvals.length
                      ? `${run.approvals.length} approval requests`
                      : "No external actions requested"}
                  </strong>
                  <p>
                    Review the prospects and drafts before contacting anyone. This bot has no
                    sending capability.
                  </p>
                </div>
              </div>
              {run.result && (
                <details className="studio-measurement-note">
                  <summary>What the result checks cover</summary>
                  <p>{run.result.criteria_note}</p>
                </details>
              )}
            </>
          )}
          {tab === "activity" && (
            <>
              {step && (
                <div className="studio-step-details">
                  <div>
                    <h2>{step.skill_id[0].toUpperCase() + step.skill_id.slice(1)} step</h2>
                    <span>{step.status}</span>
                  </div>
                  <p>
                    Started {dateTime(step.started_at)} · Finished {dateTime(step.completed_at)}
                  </p>
                  {step.error && <p className="studio-error">{step.error.message}</p>}
                  <details open>
                    <summary>Input · sensitive values redacted</summary>
                    <pre>{JSON.stringify(step.input, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>Output · validated structured data</summary>
                    <pre>{JSON.stringify(step.output, null, 2)}</pre>
                  </details>
                </div>
              )}
              <div className="studio-event-log">
                <h2>Execution log</h2>
                {run.logs.map((event, i) => (
                  <div key={`${event.at}-${i}`}>
                    <time>{dateTime(event.at)}</time>
                    <span className={`log-kind log-${event.kind}`}>
                      {event.kind.replace(/_/g, " ")}
                    </span>
                    <p>{event.message}</p>
                  </div>
                ))}
              </div>
            </>
          )}
          {tab === "configuration" && (
            <div className="studio-run-configuration">
              <h2>Settings used for this run</h2>
              <p>
                This saved snapshot preserves the objective, target and permissions used at
                submission. Later edits apply to new runs; access can be revoked immediately.
              </p>
              <dl>
                <dt>Objective</dt>
                <dd>{run.configuration.objective}</dd>
                <dt>Target</dt>
                <dd>
                  {run.configuration.target.industry} · {run.configuration.target.location}
                </dd>
                <dt>Qualification criteria</dt>
                <dd>{run.configuration.target.qualification_criteria}</dd>
                <dt>Offering</dt>
                <dd>{run.configuration.target.offering}</dd>
                <dt>Expected results</dt>
                <dd>{run.configuration.expected_results.description}</dd>
                <dt>Permitted tools</dt>
                <dd>{run.configuration.tools.join(", ")}</dd>
                <dt>Trigger</dt>
                <dd>Manual</dd>
              </dl>
              <details>
                <summary>Configuration JSON · sensitive values redacted</summary>
                <pre>{JSON.stringify(run.configuration, null, 2)}</pre>
              </details>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
