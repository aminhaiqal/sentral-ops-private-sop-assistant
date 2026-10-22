import { useEffect, useRef, useState } from "react";
import { ExternalLink, FileText, Loader2, Search, X } from "lucide-react";
import type { ApiClient } from "../api";
import type { DriveDocument, DriveFile } from "./types";

export default function DriveFiles({
  api,
  connectionId,
  selected,
  onSelect,
  onFiles,
}: {
  api: ApiClient;
  connectionId: string;
  selected?: string[];
  onSelect?: (file: DriveFile) => void;
  onFiles?: (files: DriveFile[]) => void;
}) {
  const [query, setQuery] = useState(""),
    [files, setFiles] = useState<DriveFile[]>([]);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const [preview, setPreview] = useState<DriveDocument | null>(null),
    [reading, setReading] = useState<string | null>(null);
  const generation = useRef(0),
    previewGeneration = useRef(0);
  async function search(name: string) {
    const request = ++generation.current;
    setLoading(true);
    setError("");
    setFiles([]);
    try {
      const result = await api.driveFiles(connectionId, name);
      if (request === generation.current) {
        setFiles(result);
        onFiles?.(result);
      }
    } catch (err) {
      if (request === generation.current)
        setError(err instanceof Error ? err.message : "Unable to search Drive.");
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }
  useEffect(() => {
    setQuery("");
    setPreview(null);
    setReading(null);
    previewGeneration.current++;
    void search("");
    return () => {
      generation.current++;
      previewGeneration.current++;
    };
    // The account determines the request scope; typing does not make provider calls.
  }, [api, connectionId]);
  async function read(file: DriveFile) {
    const request = ++previewGeneration.current;
    setReading(file.id);
    setPreview(null);
    setError("");
    try {
      const document = await api.driveDocument(connectionId, file.id);
      if (request === previewGeneration.current) setPreview(document);
    } catch (err) {
      if (request === previewGeneration.current)
        setError(err instanceof Error ? err.message : "Unable to read this file.");
    } finally {
      if (request === previewGeneration.current) setReading(null);
    }
  }
  return (
    <div className="drive-browser">
      <div className="drive-search" role="search" aria-label="Google Drive files">
        <Search size={16} />
        <input
          aria-label="Search Drive files"
          placeholder="Search file names"
          maxLength={180}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void search(query);
            }
          }}
        />
        <button
          type="button"
          className="button secondary"
          disabled={loading}
          onClick={() => void search(query)}
        >
          {loading ? <Loader2 size={14} className="spin" /> : "Search"}
        </button>
      </div>
      <p className="studio-field-help">
        Up to 20 matches. Read Google Docs and text files; open other formats in Drive.
      </p>
      {error && (
        <p className="studio-error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p className="connections-loading" role="status">
          Searching Google Drive…
        </p>
      ) : !files.length && !error ? (
        <p className="connections-loading">No files found. Try a different name.</p>
      ) : null}
      <div className="drive-file-list">
        {files.map((file) => (
          <div className="drive-file" key={file.id}>
            {onSelect ? (
              <input
                type="checkbox"
                aria-label={`Use ${file.name}`}
                checked={selected?.includes(file.id) ?? false}
                disabled={
                  !file.readable || (!selected?.includes(file.id) && (selected?.length ?? 0) >= 2)
                }
                onChange={() => onSelect(file)}
              />
            ) : (
              <FileText size={17} />
            )}
            <span className="drive-file-name">
              <strong>{file.name}</strong>
              <small>
                {file.mime_type === "application/vnd.google-apps.document"
                  ? "Google Doc"
                  : file.mime_type}
                {!file.readable && " · open in Drive"}
              </small>
            </span>
            <div className="drive-file-actions">
              {file.readable && (
                <button
                  type="button"
                  className="studio-text-button"
                  disabled={!!reading}
                  onClick={() => void read(file)}
                >
                  {reading === file.id ? "Reading…" : "Preview"}
                </button>
              )}
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${file.name} in Drive`}
              >
                <ExternalLink size={15} />
              </a>
            </div>
          </div>
        ))}
      </div>
      {preview && (
        <section className="drive-preview" aria-label="Drive document preview">
          <header>
            <h3>{preview.file.name}</h3>
            <button
              type="button"
              className="icon-button"
              aria-label="Close file preview"
              onClick={() => setPreview(null)}
            >
              <X size={16} />
            </button>
          </header>
          <p>Preview only. This does not add the file to a bot.</p>
          <pre>{preview.text || "This document is empty."}</pre>
          {preview.truncated && <small>Showing the first 8,000 characters.</small>}
        </section>
      )}
    </div>
  );
}
