import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ApiClient } from "../api";
import type { ConnectionsCatalog, DriveSource } from "./types";
import DriveFiles from "./DriveFiles";
import "./connections.css";

export default function DriveSourcePicker({
  api,
  source,
  onChange,
  onConnections,
}: {
  api: ApiClient;
  source: DriveSource | null;
  onChange: (value: DriveSource | null) => void;
  onConnections: () => void;
}) {
  const [data, setData] = useState<ConnectionsCatalog | null>(null),
    [error, setError] = useState("");
  const [fileNames, setFileNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    const refresh = () => {
      void api
        .connections()
        .then((result) => {
          if (alive) setData(result);
        })
        .catch((err) => {
          if (alive)
            setError(err instanceof Error ? err.message : "Unable to load Drive accounts.");
        });
    };
    refresh();
    window.addEventListener("axelyn:connections-changed", refresh);
    return () => {
      alive = false;
      window.removeEventListener("axelyn:connections-changed", refresh);
    };
  }, [api]);
  const accounts =
    data?.connections.filter((connection) => connection.status === "connected") ?? [];
  return (
    <section className="studio-form-section drive-source-picker">
      <h2>
        Background documents <span className="connection-mode">Optional</span>
      </h2>
      <p className="studio-field-help">
        Use up to two Drive documents about your offering or customer profile. The bot reads the
        first 2,000 characters of each file before research. Selected text is shared with your
        configured AI provider and saved in execution history.
      </p>
      {error && (
        <p className="studio-error" role="alert">
          {error}
        </p>
      )}
      <label>
        Google Drive account
        <select
          aria-label="Google Drive account"
          value={source?.connection_id ?? ""}
          onChange={(e) =>
            onChange(e.target.value ? { connection_id: e.target.value, file_ids: [] } : null)
          }
        >
          <option value="">No Drive access</option>
          {source && !accounts.some((account) => account.id === source.connection_id) && (
            <option value={source.connection_id}>
              Unavailable account — choose another or remove access
            </option>
          )}
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      </label>
      {source && (
        <>
          <p className="studio-field-help">
            {source.file_ids.length} / 2 files selected. Removing a selected file also revokes it
            for active runs.
          </p>
          <div className="drive-selected-files">
            {source.file_ids.map((id, index) => (
              <button
                type="button"
                key={id}
                onClick={() =>
                  onChange({ ...source, file_ids: source.file_ids.filter((item) => item !== id) })
                }
                aria-label={`Remove ${fileNames[id] ?? `selected document ${index + 1}`}`}
              >
                {fileNames[id] ?? `Selected document ${index + 1}`} <X size={12} />
              </button>
            ))}
          </div>
          {accounts.some((account) => account.id === source.connection_id) && (
            <DriveFiles
              api={api}
              connectionId={source.connection_id}
              onFiles={(files) =>
                setFileNames((current) => ({
                  ...current,
                  ...Object.fromEntries(files.map((file) => [file.id, file.name])),
                }))
              }
              selected={source.file_ids}
              onSelect={(file) =>
                onChange({
                  ...source,
                  file_ids: source.file_ids.includes(file.id)
                    ? source.file_ids.filter((id) => id !== file.id)
                    : [...source.file_ids, file.id].slice(0, 2),
                })
              }
            />
          )}
        </>
      )}
      {!accounts.length && data && (
        <p className="studio-field-help">
          Connect Google Drive in Connections, then reopen this form to select files.
        </p>
      )}
      <button type="button" className="studio-text-button" onClick={onConnections}>
        Manage connections
      </button>
    </section>
  );
}
