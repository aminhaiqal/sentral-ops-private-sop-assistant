import { AlertCircle, ChevronDown, FileText, Loader2, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { documentDownloadUrl } from "../api";
import type { ChatMessage } from "../types";

export default function AnswerCard({ message }: { message: ChatMessage }) {
  const response = message.response;
  return (
    <article className="assistant-message" aria-live="polite">
      <div className="assistant-label"><Sparkles size={16} /><span>Sentral</span></div>
      {message.pending ? <div className="thinking"><Loader2 size={16} className="spin" />Reading your sources…</div>
        : message.error ? <div className="message-error"><AlertCircle size={17} />{message.error}</div>
          : <>
            {response?.warnings.map((warning) => <p className="boundary-note" key={warning.category}>{warning.message}</p>)}
            <div className="answer-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>
              {response?.answer ?? message.content}
            </ReactMarkdown></div>
            {response && <div className="answer-details">
              <details className="sources-disclosure">
                <summary><FileText size={14} />Sources <span>{response.sources.length}</span><ChevronDown size={14} /></summary>
                <div className="source-list">
                  {response.sources.length === 0 && <p className="muted">No matching sources found.</p>}
                  {response.sources.map((source) => <div className="source-item" key={source.chunk_id}>
                    <div className="source-heading"><span className="citation-badge">{source.citation}</span>
                      {/upload-[a-f0-9]{32}/.test(source.document_id)
                        ? <a href={documentDownloadUrl(source.document_id.replace("upload-", ""))}>{source.title}</a>
                        : <strong>{source.title}</strong>}
                    </div><p>{source.excerpt}</p>
                  </div>)}
                </div>
              </details>
              <details className="trace-disclosure">
                <summary>How this answer was found<ChevronDown size={14} /></summary>
                <ol className="trace-list">{response.agent_steps.map((step) => <li key={step.name}>
                  <strong>{step.name}</strong><p>{step.detail}</p>
                </li>)}</ol>
              </details>
            </div>}
          </>}
    </article>
  );
}
