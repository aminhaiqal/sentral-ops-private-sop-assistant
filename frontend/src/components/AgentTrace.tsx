import { AlertTriangle, CheckCircle2, Workflow } from "lucide-react";

import type { AgentStep } from "../types";

type AgentTraceProps = {
  steps: AgentStep[];
};

function statusIcon(status: string) {
  if (status === "warning") {
    return <AlertTriangle size={16} />;
  }

  return <CheckCircle2 size={16} />;
}

export default function AgentTrace({ steps }: AgentTraceProps) {
  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="agent-trace">
      <div className="trace-heading">
        <Workflow size={18} />
        <h2>Agent Trace</h2>
      </div>
      <ol>
        {steps.map((step) => (
          <li
            className={step.status === "warning" ? "trace-step warning-step" : "trace-step"}
            key={step.name}
          >
            {statusIcon(step.status)}
            <div>
              <strong>{step.name}</strong>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
