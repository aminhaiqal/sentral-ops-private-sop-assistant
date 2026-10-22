import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronRight,
  FilePenLine,
  History,
  Layers3,
  Loader2,
  Pencil,
  Play,
  Plus,
  Search,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import type { ApiClient } from "../api";
import type { StudioBot, StudioCatalog, StudioRun, StudioRunSummary } from "./types";
import StudioForm, { SKILL_ICONS } from "./StudioForm";
import ExecutionDetails, { dateTime, RunStatus } from "./ExecutionDetails";
import "./studio.css";
import ConnectionsPage from "../connections/Connections";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to load Bot Studio.";

function ConnectionsDialog({
  api,
  catalog,
  onClose,
}: {
  api: ApiClient;
  catalog: StudioCatalog;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="drive-connections-dialog"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      aria-label="Manage connections"
    >
      <button
        className="icon-button connections-dialog-close"
        aria-label="Close connections"
        onClick={onClose}
      >
        <X size={18} />
      </button>
      <ConnectionsPage api={api} catalog={catalog} />
    </dialog>
  );
}

function DeleteBot({
  bot,
  onDelete,
  onClose,
}: {
  bot: StudioBot;
  onDelete: () => Promise<void>;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="studio-delete-dialog"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      aria-labelledby="delete-bot-title"
    >
      <h2 id="delete-bot-title">Delete {bot.configuration.name}?</h2>
      <p>
        This removes the bot from your library and stops its active runs. Saved execution records
        are retained.
      </p>
      {error && (
        <p className="studio-error" role="alert">
          {error}
        </p>
      )}
      <footer>
        <button className="button secondary" disabled={busy} onClick={onClose}>
          Keep bot
        </button>
        <button
          className="button primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onDelete();
            } catch (err) {
              setError(message(err));
              setBusy(false);
            }
          }}
        >
          {busy ? "Deleting…" : "Delete bot"}
        </button>
      </footer>
    </dialog>
  );
}

function HistoryTable({
  runs,
  onOpen,
}: {
  runs: StudioRunSummary[];
  onOpen: (id: string) => void;
}) {
  return (
    <div className="studio-table-wrap">
      <table className="studio-history-table">
        <thead>
          <tr>
            <th>Execution</th>
            <th>Status</th>
            <th>Started</th>
            <th>Results</th>
            <th>AI tokens</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <button className="studio-table-name" onClick={() => onOpen(run.id)}>
                  <span className="studio-run-id">{run.id.slice(0, 8)}</span>
                  {run.bot_name}
                </button>
              </td>
              <td>
                <RunStatus status={run.status} />
              </td>
              <td>{dateTime(run.started_at ?? run.created_at)}</td>
              <td>{run.result_count} prospects</td>
              <td>{(run.usage.input_tokens + run.usage.output_tokens).toLocaleString()}</td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Open execution ${run.id.slice(0, 8)}`}
                  onClick={() => onOpen(run.id)}
                >
                  <ChevronRight size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!runs.length && (
        <div className="studio-history-empty">
          <History size={23} />
          <h3>No executions yet</h3>
          <p>Choose Run bot to start. Progress and results are saved here.</p>
        </div>
      )}
    </div>
  );
}

export default function Studio({
  api,
  accountMenu,
  path,
  onNavigate,
  onClose,
}: {
  api: ApiClient;
  accountMenu: ReactNode;
  path: string;
  onNavigate: (path: string) => void;
  onClose: () => void;
}) {
  const [catalog, setCatalog] = useState<StudioCatalog | null>(null),
    [bots, setBots] = useState<StudioBot[]>([]);
  const [loaded, setLoaded] = useState(false),
    [error, setError] = useState("");
  const [query, setQuery] = useState(""),
    [connections, setConnections] = useState(false),
    [deleting, setDeleting] = useState<StudioBot | null>(null);
  const [busy, setBusy] = useState<string | null>(null),
    [run, setRun] = useState<StudioRun | null>(null),
    [runs, setRuns] = useState<StudioRunSummary[]>([]),
    [historyLoading, setHistoryLoading] = useState(false);
  const requestKeys = useRef(new Map<string, string>());
  const [runReload, setRunReload] = useState(0);
  const editMatch = path.match(/^\/bots\/([a-f0-9]+)\/edit$/),
    botMatch = path.match(/^\/bots\/([a-f0-9]+)$/),
    runMatch = path.match(/^\/runs\/([a-f0-9]+)$/);
  const botId = editMatch?.[1] ?? botMatch?.[1],
    runId = runMatch?.[1];
  const bot = bots.find((item) => item.id === botId);
  const isNew = path === "/bots/new",
    isHistory = path === "/history" || !!botMatch;
  const isConnections = path === "/connections";
  const isLibrary = path === "/" || path === "";
  const loadLibrary = useCallback(async () => {
    const [profiles, metadata] = await Promise.allSettled([api.studioBots(), api.studioCatalog()]);
    if (profiles.status === "fulfilled") setBots(profiles.value);
    else setError(message(profiles.reason));
    if (metadata.status === "fulfilled") setCatalog(metadata.value);
    else setError(message(metadata.reason));
    setLoaded(true);
  }, [api]);
  useEffect(() => {
    let alive = true,
      fetching = false;
    async function refresh() {
      if (fetching || document.hidden) return;
      fetching = true;
      const results = await Promise.allSettled([api.studioBots(), api.studioCatalog()]);
      if (alive) {
        if (results[0].status === "fulfilled") setBots(results[0].value);
        else setError(message(results[0].reason));
        if (results[1].status === "fulfilled") setCatalog(results[1].value);
        else setError(message(results[1].reason));
        setLoaded(true);
      }
      fetching = false;
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 4000);
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
  useEffect(() => {
    if (!runId) {
      setRun(null);
      return;
    }
    let alive = true,
      fetching = false,
      done = false;
    async function refresh() {
      if (fetching || (done && !document.hidden)) return;
      fetching = true;
      try {
        const next = await api.studioRun(runId!);
        if (alive) {
          setRun(next);
          done = !["queued", "running"].includes(next.status);
        }
      } catch (err) {
        if (alive) setError(message(err));
      } finally {
        fetching = false;
      }
    }
    setRun(null);
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [api, runId, runReload]);
  const historyRevision = bots.map((item) => `${item.id}:${item.last_run?.updated_at}`).join();
  useEffect(() => {
    if (!isHistory) return;
    let alive = true;
    setHistoryLoading(true);
    void api
      .studioRuns(botMatch?.[1])
      .then((values) => {
        if (alive) setRuns(values);
      })
      .catch((err) => {
        if (alive) setError(message(err));
      })
      .finally(() => {
        if (alive) setHistoryLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [api, isHistory, botMatch?.[1], historyRevision]);
  useEffect(() => {
    setError("");
  }, [path]);
  async function start(botId: string) {
    if (busy) return;
    setBusy(botId);
    setError("");
    let key = requestKeys.current.get(botId);
    if (!key) {
      key = crypto.randomUUID();
      requestKeys.current.set(botId, key);
    }
    try {
      const next = await api.startStudioRun(botId, key);
      requestKeys.current.delete(botId);
      setRun(next);
      onNavigate(`/runs/${next.id}`);
      void loadLibrary();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(null);
    }
  }
  async function control(retry: boolean) {
    if (!run || busy) return;
    setBusy(run.id);
    setError("");
    try {
      const next = retry ? await api.retryStudioRun(run.id) : await api.cancelStudioRun(run.id);
      setRun(next);
      if (retry) setRunReload((value) => value + 1);
      void loadLibrary();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(null);
    }
  }
  const visible = bots.filter((item) =>
    `${item.configuration.name} ${item.configuration.objective}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const missing = catalog?.tools.filter((tool) => !tool.configured) ?? [];
  return (
    <main className="studio-shell">
      <header className="studio-topbar">
        <div className="studio-topbar-left">
          <button
            className="studio-workspace-link"
            onClick={onClose}
            aria-label="Back to Axelyn workspace"
          >
            <span className="brand-symbol">
              a<span />
            </span>
            <span>axelyn.</span>
          </button>
          <span className="studio-topbar-separator" />
          <button className="studio-current-product" onClick={() => onNavigate("/")}>
            <Layers3 size={17} />
            Bot Studio
          </button>
        </div>
        <div className="studio-topbar-right">
          <button className="studio-connections-button" onClick={() => onNavigate("/connections")}>
            <span
              className={missing.length ? "studio-connection-dot missing" : "studio-connection-dot"}
            />
            <span>Connections</span>
            <Settings2 size={14} />
          </button>
          {accountMenu}
        </div>
      </header>
      <nav className="studio-nav" aria-label="Studio navigation">
        <button
          className={isLibrary || isNew || botId ? "selected" : ""}
          onClick={() => onNavigate("/")}
        >
          <Layers3 size={15} />
          Bot library
        </button>
        <button
          className={path === "/history" || runId ? "selected" : ""}
          onClick={() => onNavigate("/history")}
        >
          <History size={15} />
          All executions
        </button>
        <button
          className={isConnections ? "selected" : ""}
          onClick={() => onNavigate("/connections")}
        >
          <Settings2 size={15} />
          Connections
        </button>
        <button className="studio-return-link" onClick={onClose}>
          <ArrowLeft size={13} />
          Workspace
        </button>
      </nav>
      <div className="studio-body">
        {error && (
          <div className="studio-error-banner" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss Studio error"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {!loaded ? (
          <div className="studio-loading" role="status">
            <Loader2 size={22} className="spin" />
            Opening Bot Studio…
          </div>
        ) : !catalog ? (
          <div className="studio-loading">
            <p>Studio couldn’t load its supported templates and connections.</p>
            <button className="button secondary" onClick={() => void loadLibrary()}>
              Try again
            </button>
          </div>
        ) : (
          <>
            {isConnections && <ConnectionsPage api={api} catalog={catalog} />}
            {isLibrary && (
              <>
                <div className="studio-page-heading">
                  <div>
                    <span className="studio-eyebrow">YOUR AUTOMATION WORKSPACE</span>
                    <h1>
                      Bot library<span className="studio-title-count">{bots.length}</span>
                    </h1>
                    <p>
                      Give a bot a responsibility. Run it, review the result, and keep the work.
                    </p>
                  </div>
                  <button className="button primary" onClick={() => onNavigate("/bots/new")}>
                    <Plus size={15} />
                    Create bot
                  </button>
                </div>
                {missing.length > 0 && (
                  <div className="studio-setup-banner">
                    <span>
                      <strong>Finish connection setup</strong>
                      {missing.map((item) => item.name).join(" and ")}{" "}
                      {missing.length > 1 ? "need" : "needs"} server configuration. You can create a
                      bot now.
                    </span>
                    <button onClick={() => onNavigate("/connections")}>
                      View setup
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                )}
                <div className="studio-library-toolbar">
                  <span>
                    {bots.length} {bots.length === 1 ? "bot" : "bots"} · Manual execution
                  </span>
                  <label>
                    <Search size={14} />
                    <input
                      aria-label="Search Studio bots"
                      placeholder="Search bots"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </label>
                </div>
                {bots.length ? (
                  <div className="studio-table-wrap">
                    <table className="studio-bot-table">
                      <thead>
                        <tr>
                          <th>Bot / responsibility</th>
                          <th>Status</th>
                          <th>Last execution</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((item) => {
                          const config = item.configuration;
                          return (
                            <tr key={item.id}>
                              <td>
                                <button
                                  className="studio-bot-name"
                                  onClick={() => onNavigate(`/bots/${item.id}`)}
                                >
                                  <span className="studio-template-icon">
                                    <Search size={18} />
                                  </span>
                                  <span>
                                    <strong>{config.name}</strong>
                                    <small>{config.objective}</small>
                                  </span>
                                </button>
                              </td>
                              <td>
                                {!config.enabled ? (
                                  <span className="studio-disabled-label">Disabled</span>
                                ) : item.last_run ? (
                                  <RunStatus status={item.last_run.status} />
                                ) : (
                                  <span className="studio-ready-label">Ready</span>
                                )}
                              </td>
                              <td>
                                {item.last_run ? (
                                  <button
                                    className="studio-last-run"
                                    onClick={() => onNavigate(`/runs/${item.last_run!.id}`)}
                                  >
                                    {dateTime(item.last_run.created_at)}
                                    <small>
                                      {item.last_run.result_count} prospects
                                      <ArrowUpRight size={11} />
                                    </small>
                                  </button>
                                ) : (
                                  <span className="studio-not-run">Not run yet</span>
                                )}
                              </td>
                              <td>
                                <div className="studio-row-actions">
                                  <button
                                    className="studio-run-button"
                                    disabled={busy === item.id || !config.enabled}
                                    onClick={() => void start(item.id)}
                                  >
                                    {busy === item.id ? (
                                      <Loader2 size={13} className="spin" />
                                    ) : (
                                      <Play size={12} />
                                    )}
                                    Run
                                  </button>
                                  <button
                                    className="icon-button"
                                    aria-label={`Edit ${config.name}`}
                                    onClick={() => onNavigate(`/bots/${item.id}/edit`)}
                                  >
                                    <Pencil size={14} />
                                  </button>
                                  <button
                                    className="icon-button"
                                    aria-label={`Delete ${config.name}`}
                                    onClick={() => setDeleting(item)}
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {!visible.length && (
                      <p className="studio-no-search">No bots match your search.</p>
                    )}
                  </div>
                ) : (
                  <div className="studio-empty-library">
                    <span className="studio-empty-icon">
                      <Search size={27} />
                    </span>
                    <span className="studio-eyebrow">START WITH ONE USEFUL JOB</span>
                    <h2>Your first lead researcher</h2>
                    <p>
                      Find relevant companies, evaluate the evidence, save qualified prospects, and
                      prepare outreach for your review.
                    </p>
                    <div className="studio-template-sequence">
                      {catalog.skills
                        .filter((skill) => skill.id !== "drive_context")
                        .map((skill) => {
                          const Icon = SKILL_ICONS[skill.id];
                          return (
                            <span key={skill.id}>
                              <Icon size={14} />
                              {skill.name}
                            </span>
                          );
                        })}
                    </div>
                    <button className="button primary" onClick={() => onNavigate("/bots/new")}>
                      Create Lead Research Bot
                      <ArrowUpRight size={15} />
                    </button>
                    <small>Real search sources. Saved results. Drafts only.</small>
                  </div>
                )}
                <div className="studio-library-footer">
                  <FilePenLine size={16} />
                  <p>One supported template. Four reusable skills. Your tools, your permissions.</p>
                  <button onClick={() => onNavigate("/connections")}>
                    Manage connections
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </>
            )}
            {(isNew || editMatch) &&
              (isNew || bot ? (
                <StudioForm
                  api={api}
                  key={bot?.id ?? "new"}
                  bot={bot}
                  catalog={catalog}
                  onBack={() => onNavigate("/")}
                  onConnections={() => setConnections(true)}
                  onSave={async (data) => {
                    const saved = await api.saveStudioBot(data, bot?.id);
                    await loadLibrary();
                    onNavigate(`/bots/${saved.id}`);
                  }}
                />
              ) : (
                <div className="studio-loading">
                  <p>This bot is unavailable or belongs to another account.</p>
                  <button className="button secondary" onClick={() => onNavigate("/")}>
                    Back to library
                  </button>
                </div>
              ))}
            {isHistory && (
              <>
                <button className="studio-back" onClick={() => onNavigate("/")}>
                  <ArrowLeft size={15} />
                  Bot library
                </button>
                <div className="studio-page-heading">
                  <div>
                    <span className="studio-eyebrow">
                      {bot ? "BOT DETAILS" : "SAVED EXECUTIONS"}
                    </span>
                    <h1>{bot?.configuration.name ?? "Execution history"}</h1>
                    <p>
                      {bot?.configuration.objective ??
                        "Open a run to inspect the skills, source evidence, results and drafts."}
                    </p>
                  </div>
                  {bot && (
                    <div className="studio-heading-actions">
                      <button
                        className="button secondary"
                        onClick={() => onNavigate(`/bots/${bot.id}/edit`)}
                      >
                        <Pencil size={14} />
                        Edit bot
                      </button>
                      <button
                        className="button primary"
                        disabled={busy === bot.id || !bot.configuration.enabled}
                        onClick={() => void start(bot.id)}
                      >
                        <Play size={13} />
                        Run bot
                      </button>
                    </div>
                  )}
                </div>
                {bot && (
                  <div className="studio-bot-facts">
                    <div>
                      <span>Target</span>
                      <strong>{bot.configuration.target.industry}</strong>
                      <small>{bot.configuration.target.location}</small>
                    </div>
                    <div>
                      <span>Skills</span>
                      <strong>
                        {bot.configuration.skills
                          .map((skill) =>
                            skill === "drive_context"
                              ? "Drive context"
                              : skill[0].toUpperCase() + skill.slice(1),
                          )
                          .join(" → ")}
                      </strong>
                      <small>Fixed, registered sequence</small>
                    </div>
                    <div>
                      <span>Expected results</span>
                      <strong>
                        {bot.configuration.expected_results.minimum_qualified}–
                        {bot.configuration.target.max_prospects} qualified prospects
                      </strong>
                      <small>Minimum fit score: {bot.configuration.target.minimum_score}/100</small>
                    </div>
                    <div>
                      <span>Trigger</span>
                      <strong>Manual</strong>
                      <small>Runs only when you choose</small>
                    </div>
                  </div>
                )}
                <div className="studio-history-heading">
                  <h2>Previous executions</h2>
                  <span>{runs.length} saved runs</span>
                </div>
                {historyLoading && !runs.length ? (
                  <p className="studio-loading" role="status">
                    Loading executions…
                  </p>
                ) : (
                  <HistoryTable runs={runs} onOpen={(id) => onNavigate(`/runs/${id}`)} />
                )}
              </>
            )}
            {runId &&
              (run?.id === runId ? (
                <ExecutionDetails
                  key={run.id}
                  run={run}
                  busy={!!busy}
                  onBack={() => onNavigate("/history")}
                  onCancel={() => void control(false)}
                  onRetry={() => void control(true)}
                  onRunAgain={() => void start(run.bot_id)}
                  canRunAgain={bots.some(
                    (item) => item.id === run.bot_id && item.configuration.enabled,
                  )}
                />
              ) : error ? (
                <div className="studio-loading">
                  <p>This execution could not be loaded.</p>
                  <button
                    className="button secondary"
                    onClick={() => setRunReload((value) => value + 1)}
                  >
                    Try again
                  </button>
                </div>
              ) : (
                <div className="studio-loading" role="status">
                  <Loader2 size={22} className="spin" />
                  Loading execution…
                </div>
              ))}
            {!isLibrary && !isNew && !editMatch && !isHistory && !runId && (
              <div className="studio-loading">
                <p>This Studio page could not be found.</p>
                <button className="button secondary" onClick={() => onNavigate("/")}>
                  Back to library
                </button>
              </div>
            )}
          </>
        )}
      </div>
      {catalog && connections && (
        <ConnectionsDialog api={api} catalog={catalog} onClose={() => setConnections(false)} />
      )}{" "}
      {deleting && (
        <DeleteBot
          bot={deleting}
          onClose={() => setDeleting(null)}
          onDelete={async () => {
            await api.deleteStudioBot(deleting.id);
            setDeleting(null);
            await loadLibrary();
            onNavigate("/");
          }}
        />
      )}
    </main>
  );
}
