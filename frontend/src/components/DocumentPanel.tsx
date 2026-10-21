import { useEffect, useRef } from "react";
import { Check, Download, FileText, Loader2, RotateCw, Trash2, Upload, X } from "lucide-react";
import type { DocumentLibrary } from "../types";

type Props = {
  open: boolean;
  library: DocumentLibrary | null;
  uploading: string | null;
  busyId: string | null;
  error: string | null;
  onClose: () => void;
  onPickFiles: () => void;
  onUpload: (files: File[]) => void;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
  onDownload: (id: string, filename: string) => void;
};

function fileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentPanel(props: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (props.open && !dialog.current?.open) dialog.current?.showModal();
    if (!props.open && dialog.current?.open) dialog.current.close();
  }, [props.open]);
  return (
    <dialog
      ref={dialog}
      className="document-panel"
      aria-labelledby="documents-title"
      onCancel={props.onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) props.onClose();
      }}
    >
      <div className="document-panel-inner">
        <header className="document-header">
          <h2 id="documents-title">Documents</h2>
          <button className="icon-button" aria-label="Close documents" onClick={props.onClose}>
            <X size={20} />
          </button>
        </header>
        <p className="panel-description">Add documents to ask questions about them.</p>
        <button
          type="button"
          className="upload-dropzone"
          onClick={props.onPickFiles}
          disabled={!!props.uploading || !props.library?.storage_configured}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            if (!props.uploading) props.onUpload(Array.from(event.dataTransfer.files));
          }}
        >
          {props.uploading ? <Loader2 size={23} className="spin" /> : <Upload size={23} />}
          <strong>{props.uploading ? "Saving document…" : "Click to upload or drop files"}</strong>
          <span>{props.uploading ?? "PDF or Markdown · Up to 10 MB per file"}</span>
        </button>
        {props.error && (
          <p className="panel-error" role="alert">
            {props.error}
          </p>
        )}
        {props.library && !props.library.storage_configured && (
          <p className="panel-error">Document uploads are temporarily unavailable.</p>
        )}
        <div className="library-heading">
          <h3>Your documents</h3>
          <span>{props.library?.documents.length ?? 0}</span>
        </div>
        {!props.library ? (
          <p className="empty-library">Loading documents…</p>
        ) : !props.library.documents.length ? (
          <div className="empty-library">
            <FileText size={26} />
            <p>Your documents will appear here.</p>
            <span>They stay available in your account.</span>
          </div>
        ) : (
          <ul className="document-list">
            {props.library.documents.map((doc) => (
              <li className="document-row" key={doc.id}>
                <FileText size={19} className="document-icon" />
                <div className="document-info">
                  <button
                    className="document-name"
                    onClick={() => props.onDownload(doc.id, doc.filename)}
                    title={doc.filename}
                  >
                    {doc.filename}
                  </button>
                  <span>
                    {fileSize(doc.size_bytes)} ·{" "}
                    {doc.status === "indexed" ? "Ready to ask" : "Saved · Not searchable yet"}
                  </span>
                  {doc.indexing_error && <p>{doc.indexing_error}</p>}
                </div>
                <div className="document-actions">
                  {props.busyId === doc.id ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <>
                      {doc.status === "saved" ? (
                        <button
                          className="icon-button small"
                          onClick={() => props.onRetry(doc.id)}
                          title="Retry indexing"
                          aria-label={`Index ${doc.filename}`}
                        >
                          <RotateCw size={15} />
                        </button>
                      ) : (
                        <Check size={15} className="document-ready" />
                      )}
                      <button
                        className="icon-button small"
                        onClick={() => props.onDownload(doc.id, doc.filename)}
                        aria-label={`Download ${doc.filename}`}
                      >
                        <Download size={15} />
                      </button>
                      <button
                        className="icon-button small"
                        onClick={() => props.onDelete(doc.id)}
                        aria-label={`Remove ${doc.filename}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="included-library">
          <FileText size={17} />
          <div>
            <strong>Sentral Ops sample library</strong>
            <p>{props.library?.demo_documents ?? 11} included SOPs · Fictional company data</p>
          </div>
        </div>
      </div>
    </dialog>
  );
}
