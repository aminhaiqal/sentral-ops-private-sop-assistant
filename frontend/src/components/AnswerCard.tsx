import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

import type { AskResponse } from "../types";
import AgentTrace from "./AgentTrace";
import SourceList from "./SourceList";

type AnswerCardProps = {
  response: AskResponse | null;
  loading: boolean;
};

function formatCategory(category: string): string {
  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function AnswerCard({ response, loading }: AnswerCardProps) {
  if (loading) {
    return (
      <section className="answer-card state-card" aria-live="polite">
        <ShieldAlert size={22} />
        <p>Checking approved SOP sources...</p>
      </section>
    );
  }

  if (!response) {
    return (
      <section className="answer-card state-card">
        <CheckCircle2 size={22} />
        <p>Ready for a Sentral Ops SOP question.</p>
      </section>
    );
  }

  return (
    <section className="answer-card" aria-live="polite">
      {response.warnings.length > 0 && (
        <div className="warning-list">
          {response.warnings.map((warning) => (
            <div className="warning" key={`${warning.category}-${warning.message}`}>
              <AlertTriangle size={18} />
              <div>
                <strong>{formatCategory(warning.category)}</strong>
                <p>{warning.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="answer-body">
        <h2>Answer</h2>
        {response.answer.split("\n").map((line, index) => (
          <p key={`${line}-${index}`}>{line}</p>
        ))}
      </div>

      <AgentTrace steps={response.agent_steps} />
      <SourceList sources={response.sources} />
    </section>
  );
}
