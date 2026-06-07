import { AlertCircle, MessageSquareText } from "lucide-react";

import type { DemoQuestion } from "../types";

type DemoQuestionsProps = {
  questions: DemoQuestion[];
  onPick: (question: string) => void;
};

export default function DemoQuestions({ questions, onPick }: DemoQuestionsProps) {
  return (
    <section className="demo-panel">
      <div className="panel-heading">
        <MessageSquareText size={18} />
        <h2>Demo Questions</h2>
      </div>
      <div className="demo-list">
        {questions.map((item) => (
          <button
            type="button"
            className="demo-question"
            key={item.question}
            onClick={() => onPick(item.question)}
          >
            <span>{item.question}</span>
            {item.boundary_expected && <AlertCircle size={16} aria-label="Boundary expected" />}
          </button>
        ))}
      </div>
    </section>
  );
}
