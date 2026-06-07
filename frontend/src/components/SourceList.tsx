import { FileText } from "lucide-react";

import type { SourceSnippet } from "../types";

type SourceListProps = {
  sources: SourceSnippet[];
};

export default function SourceList({ sources }: SourceListProps) {
  return (
    <div className="source-list">
      <h2>Sources</h2>
      {sources.length === 0 ? (
        <p className="muted">No approved sources returned.</p>
      ) : (
        sources.map((source) => (
          <article className="source-item" key={source.chunk_id}>
            <div className="source-heading">
              <FileText size={18} />
              <div>
                <h3>{source.title}</h3>
                <span>
                  {source.document_id} · {source.chunk_id} · {(source.score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <p>{source.excerpt}</p>
          </article>
        ))
      )}
    </div>
  );
}
