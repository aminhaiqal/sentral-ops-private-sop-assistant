import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, HardDrive, Loader2, ShieldCheck } from "lucide-react";
import type { ApiClient } from "../api";
import type { StudioCatalog } from "../studio/types";
import type { ConnectionsCatalog } from "./types";
import DriveFiles from "./DriveFiles";
import {
  googleAuthorizationUrl,
  pendingGoogleAuth,
  saveGoogleAuth,
  type PendingGoogleAuth,
} from "./googleAuth";
import "./connections.css";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to connect Google Drive.";
const labels = {
  connected: "Connected",
  reconnect_required: "Reconnect required",
  disconnected: "Disconnected",
};
function storage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export default function Connections({ api }: { api: ApiClient; catalog?: StudioCatalog }) {
  const [data, setData] = useState<ConnectionsCatalog | null>(null),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [pending, setPending] = useState<PendingGoogleAuth | null>(null),
    [fallback, setFallback] = useState("");
  const [selected, setSelected] = useState(""),
    [confirm, setConfirm] = useState<string | null>(null);
  const popup = useRef<Window | null>(null),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    void api
      .connections()
      .then((value) => {
        if (alive.current) {
          setData(value);
          setPending(pendingGoogleAuth(storage(), value.account_scope));
        }
      })
      .catch((err) => {
        if (alive.current) setError(message(err));
      });
    return () => {
      alive.current = false;
    };
  }, [api]);
  useEffect(() => {
    if (!pending || !data) return;
    let stopped = false,
      fetching = false;
    const scope = data.account_scope;
    function clear() {
      saveGoogleAuth(storage(), scope, null);
      setPending(null);
      setFallback("");
      popup.current?.close();
      popup.current = null;
    }
    async function poll() {
      if (stopped || fetching) return;
      if (Date.now() >= pending!.expires_at) {
        clear();
        setError("Google sign-in expired. Click Connect to try again.");
        return;
      }
      fetching = true;
      try {
        const flow = await api.googleDriveAuthStatus(pending!.flow_id);
        if (stopped) return;
        if (flow.status === "ready" || flow.status === "complete") {
          const connection = await api.completeGoogleDriveAuth(pending!.flow_id);
          const catalog = await api.connections();
          if (stopped) return;
          clear();
          setData(catalog);
          setSelected(connection.status === "connected" ? connection.id : "");
          setNotice(
            connection.status === "connected"
              ? "Google Drive connected."
              : "This account is disconnected. Click Connect to authorize it again.",
          );
          window.dispatchEvent(new Event("axelyn:connections-changed"));
        } else if (["failed", "expired"].includes(flow.status)) {
          clear();
          setError(
            flow.error === "authorization_cancelled"
              ? "Google sign-in was cancelled. Click Connect when you’re ready."
              : "Google Drive wasn’t connected. Click Connect to try again.",
          );
        }
      } catch (err) {
        if (!stopped) {
          clear();
          setError(message(err));
        }
      } finally {
        fetching = false;
      }
    }
    void poll();
    const timer = setInterval(() => void poll(), 1500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [api, pending, data?.account_scope]);

  async function connect() {
    if (!data || busy || pending) return;
    popup.current = window.open("about:blank", "_blank");
    if (popup.current) popup.current.opener = null;
    setBusy(true);
    setError("");
    setNotice("");
    setFallback("");
    try {
      const result = await api.connectGoogleDrive();
      const url = googleAuthorizationUrl(result.url);
      if (
        !/^[a-f0-9]{32}$/.test(result.flow_id) ||
        result.expires_in < 1 ||
        result.expires_in > 600
      )
        throw new Error("Invalid Google sign-in attempt.");
      const attempt = {
        flow_id: result.flow_id,
        expires_at: Date.now() + result.expires_in * 1000,
      };
      saveGoogleAuth(storage(), data.account_scope, attempt);
      if (!alive.current) return;
      setPending(attempt);
      if (popup.current && !popup.current.closed) popup.current.location.href = url;
      else setFallback(url);
    } catch (err) {
      popup.current?.close();
      if (alive.current) setError(message(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function cancel() {
    if (!pending || !data) return;
    setBusy(true);
    try {
      await api.cancelGoogleDriveAuth(pending.flow_id);
      saveGoogleAuth(storage(), data.account_scope, null);
      setPending(null);
      setFallback("");
      popup.current?.close();
      setNotice("Google sign-in cancelled.");
    } catch (err) {
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
      setData(await api.connections());
      window.dispatchEvent(new Event("axelyn:connections-changed"));
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
          <h1>Connections</h1>
          <p>Connect the apps your bots work with.</p>
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
                <p>Let your bots read the documents you choose.</p>
              </div>
              <button
                className="button primary"
                aria-label="Connect Google Drive"
                disabled={!data.configured || busy || !!pending}
                onClick={() => void connect()}
              >
                {busy || pending ? <Loader2 size={15} className="spin" /> : null}
                {pending ? "Connecting…" : "Connect"}
              </button>
            </div>
            <div className="connection-access-note">
              <ShieldCheck size={16} />
              <p>
                You approve access with Google. Bots can read selected files; they cannot change or
                delete them.
              </p>
            </div>
            {!data.configured && (
              <p className="connection-not-ready">
                Google Drive setup is not finished yet. The app owner needs to enable Google
                authorization.
              </p>
            )}
            {pending && (
              <div className="connection-pending" role="status">
                <span>Finish signing in with Google. This page will update automatically.</span>
                <button
                  className="studio-text-button"
                  disabled={busy}
                  onClick={() => void cancel()}
                >
                  Cancel
                </button>
              </div>
            )}
            {fallback && (
              <a
                className="connection-consent-link"
                href={fallback}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                Continue with Google <ArrowUpRight size={14} />
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
                  </div>
                  <div className="connection-account-actions">
                    {connection.status === "connected" ? (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => setSelected(connection.id)}
                        >
                          {selected === connection.id ? <Check size={14} /> : null}Browse files
                        </button>
                        {confirm === connection.id ? (
                          <>
                            <span>Disconnect this account?</span>
                            <button
                              className="studio-text-button"
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
                            Disconnect
                          </button>
                        )}
                      </>
                    ) : (
                      <button
                        className="studio-text-button"
                        disabled={busy || !!pending || !data.configured}
                        onClick={() => void connect()}
                      >
                        Reconnect
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
          {active && (
            <section className="connection-files-section">
              <h2>Files in {active.name}</h2>
              <DriveFiles key={active.id} api={api} connectionId={active.id} />
            </section>
          )}
          {data.activity.some((event) => event.status !== "started") && (
            <details className="connections-activity">
              <summary>Connection activity</summary>
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
            </details>
          )}
        </>
      )}
    </div>
  );
}
