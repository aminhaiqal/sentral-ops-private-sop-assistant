import { Database, RefreshCw, ShieldCheck } from "lucide-react";

import type { HealthResponse, IngestResponse } from "../types";

type SystemNoticeProps = {
  health: HealthResponse | null;
  ingesting: boolean;
  ingestResult: IngestResponse | null;
  onIngest: () => void;
};

export default function SystemNotice({
  health,
  ingesting,
  ingestResult,
  onIngest
}: SystemNoticeProps) {
  return (
    <section className="system-panel">
      <div className="panel-heading">
        <ShieldCheck size={18} />
        <h2>System</h2>
      </div>
      <div className="status-grid">
        <div>
          <span className="status-label">OpenAI</span>
          <strong className={health?.openai_configured ? "ok" : "bad"}>
            {health?.openai_configured ? "Configured" : "Missing key"}
          </strong>
        </div>
        <div>
          <span className="status-label">Collection</span>
          <strong>{health?.qdrant_collection ?? "Checking"}</strong>
        </div>
      </div>
      <p className="notice-text">Fictional demo company data. Internal Use Only.</p>
      {ingestResult && (
        <p className="ingest-result">
          <Database size={16} />
          {ingestResult.documents} docs · {ingestResult.chunks} chunks indexed
        </p>
      )}
      <button type="button" className="secondary-button" onClick={onIngest} disabled={ingesting}>
        <RefreshCw size={17} className={ingesting ? "spin" : undefined} />
        <span>{ingesting ? "Indexing" : "Index SOPs"}</span>
      </button>
    </section>
  );
}
