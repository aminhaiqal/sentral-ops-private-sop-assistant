import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight,
  Check,
  HardDrive,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import type { ApiClient } from "../api";
import type { StudioCatalog } from "../studio/types";
import type { ConnectionsCatalog } from "./types";
import DriveFiles from "./DriveFiles";
import "./connections.css";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to load connections.";
const labels = {
  connected: "Connected",
  reconnect_required: "Reconnect required",
  disconnected: "Disconnected",
};

export default function Connections({ api, catalog }: { api: ApiClient; catalog: StudioCatalog }) {
  const [data, setData] = useState<ConnectionsCatalog | null>(null),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [link, setLink] = useState(""),
    [selected, setSelected] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  const load = useCallback(async () => {
    setData(await api.connections());
    window.dispatchEvent(new Event("axelyn:connections-changed"));
  }, [api]);
  useEffect(() => {
    let alive = true;
    void api
      .connections()
      .then((value) => {
        if (alive) setData(value);
      })
      .catch((err) => {
        if (alive) setError(message(err));
      });
    return () => {
      alive = false;
    };
  }, [api]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      await api.refreshConnections();
      await load();
      setLink("");
      setNotice("Connection status refreshed.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function connect() {
    // Open during the click so popup blockers do not discard the consent flow.
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    setBusy(true);
    setError("");
    setLink("");
    try {
      const result = await api.connectGoogleDrive();
      const url = new URL(result.url);
      if (
        url.protocol !== "https:" ||
        !(url.hostname === "pipedream.com" || url.hostname.endsWith(".pipedream.com")) ||
        url.username ||
        url.password
      )
        throw Error("The authorization link is invalid.");
      setLink(result.url);
      if (popup && !popup.closed) popup.location.href = result.url;
      setNotice(
        "Finish connecting in the Google authorization tab, then refresh accounts here. The link expires in 10 minutes.",
      );
    } catch (err) {
      popup?.close();
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function disconnect(id: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api.disconnectConnection(id);
      setNotice(result.message);
      if (selected === id) setSelected("");
      setConfirm(null);
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function reconnect(id: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api.reconnectConnection(id);
      setNotice(result.message);
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  const active = data?.connections.find(
    (connection) => connection.id === selected && connection.status === "connected",
  );
  return (
    <div className="connections-page">
      <div className="studio-page-heading">
        <div>
          <span className="studio-eyebrow">WORKSPACE ACCESS</span>
          <h1>Connections</h1>
          <p>Connect an account, then choose what each bot can read.</p>
        </div>
      </div>
      {error && (
        <p className="studio-error-banner" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="connections-notice" role="status">
          {notice}
        </p>
      )}
      {!data ? (
        <p role="status">Loading connections…</p>
      ) : (
        <>
          <section className="connection-provider" aria-labelledby="drive-provider-title">
            <div className="connection-provider-heading">
              <span className="connection-provider-icon">
                <HardDrive size={26} />
              </span>
              <div>
                <h2 id="drive-provider-title">Google Drive</h2>
                <p>Find documents and give your bots selected background material.</p>
              </div>
              <span className="connection-mode">Search & read</span>
            </div>
            <div className="connection-access-note">
              <ShieldCheck size={17} />
              <p>
                Axelyn enables reading only. Each bot gets the files you select. Review Google’s
                consent screen for the account permissions requested by Pipedream.
              </p>
            </div>
            {!data.configured ? (
              <div className="connection-setup">
                <h3>Administrator setup required</h3>
                <p>
                  Add your Pipedream Connect project credentials to the API and worker. Google
                  tokens stay with Pipedream.
                </p>
                <ul>
                  <li>PIPEDREAM_CLIENT_ID</li>
                  <li>PIPEDREAM_CLIENT_SECRET</li>
                  <li>PIPEDREAM_PROJECT_ID</li>
                  <li>PIPEDREAM_ENVIRONMENT</li>
                </ul>
                <a
                  href="https://pipedream.com/docs/connect/mcp/developers"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open setup guide <ArrowUpRight size={14} />
                </a>
              </div>
            ) : (
              <div className="connection-provider-actions">
                <button className="button primary" disabled={busy} onClick={() => void connect()}>
                  {busy ? <Loader2 size={15} className="spin" /> : <HardDrive size={15} />}Connect
                  Google Drive
                </button>
                <button className="button secondary" disabled={busy} onClick={() => void refresh()}>
                  <RefreshCw size={14} />
                  Refresh accounts
                </button>
                <small>
                  {data.environment === "development"
                    ? "Development connections"
                    : "Production connections"}
                </small>
              </div>
            )}
            {link && (
              <a
                className="connection-consent-link"
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                Continue Google Drive authorization <ArrowUpRight size={14} />
              </a>
            )}
            <div className="connection-account-list">
              {data.connections.map((connection) => (
                <div className="connection-account" key={connection.id}>
                  <div>
                    <strong>{connection.name}</strong>
                    <span
                      className={
                        connection.status === "connected"
                          ? "connection-ready"
                          : "connection-missing"
                      }
                    >
                      {labels[connection.status]}
                    </span>
                    <small>Checked {new Date(connection.checked_at).toLocaleString()}</small>
                  </div>
                  <div className="connection-account-actions">
                    {connection.status !== "connected" && (
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() => void reconnect(connection.id)}
                      >
                        Reconnect
                      </button>
                    )}
                    {connection.status === "connected" && (
                      <button
                        className="button secondary"
                        onClick={() => setSelected(connection.id)}
                      >
                        {selected === connection.id ? <Check size={14} /> : null}Browse files
                      </button>
                    )}
                    {confirm === connection.id ? (
                      <>
                        <span>Stop this account’s access?</span>
                        <button
                          className="button secondary"
                          disabled={busy}
                          onClick={() => setConfirm(null)}
                        >
                          Keep connected
                        </button>
                        <button
                          className="button secondary"
                          disabled={busy}
                          onClick={() => void disconnect(connection.id)}
                        >
                          Confirm disconnect
                        </button>
                      </>
                    ) : (
                      <button
                        className="studio-text-button"
                        disabled={busy}
                        onClick={() => setConfirm(connection.id)}
                      >
                        <Unplug size={13} />
                        {connection.status === "disconnected" ? "Retry removal" : "Disconnect"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {data.configured && !data.connections.length && (
                <p className="connections-loading">No Google Drive accounts connected yet.</p>
              )}
            </div>
          </section>
          {active && (
            <section className="connection-files-section">
              <h2>Files in {active.name}</h2>
              <DriveFiles key={active.id} api={api} connectionId={active.id} />
            </section>
          )}
          <section className="connections-built-in">
            <h2>Bot runtime connections</h2>
            {catalog.tools.map((tool) => (
              <div key={tool.id}>
                <strong>{tool.name}</strong>
                <span className={tool.configured ? "connection-ready" : "connection-missing"}>
                  {tool.configured ? "Ready" : "Setup required"}
                </span>
                <p>{tool.setup}</p>
              </div>
            ))}
          </section>
          {data.activity.length > 0 && (
            <section className="connections-activity">
              <h2>Recent connection activity</h2>
              <p>File contents, credentials and authorization links are excluded from this log.</p>
              {data.activity
                .filter((event) => event.status !== "started")
                .slice(0, 10)
                .map((event, index) => (
                  <div key={index}>
                    <span>{event.operation.replace(/_/g, " ")}</span>
                    <small>{event.status.replace(/_/g, " ")}</small>
                    <time>{new Date(event.created_at).toLocaleString()}</time>
                  </div>
                ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}
