import { useEffect, useState } from "react";
import { Building2 } from "lucide-react";

import { askQuestion, getDemoQuestions, getHealth, ingestDocuments } from "./api";
import AnswerCard from "./components/AnswerCard";
import DemoQuestions from "./components/DemoQuestions";
import QuestionInput from "./components/QuestionInput";
import SystemNotice from "./components/SystemNotice";
import type { AskResponse, DemoQuestion, HealthResponse, IngestResponse } from "./types";

export default function App() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [demoQuestions, setDemoQuestions] = useState<DemoQuestion[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<IngestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([getHealth(), getDemoQuestions()])
      .then(([healthResult, questions]) => {
        setHealth(healthResult);
        setDemoQuestions(questions);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function submit(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (trimmed.length < 3 || loading) {
      return;
    }

    setQuestion(trimmed);
    setError(null);
    setLoading(true);
    try {
      const answer = await askQuestion(trimmed);
      setResponse(answer);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer.");
    } finally {
      setLoading(false);
    }
  }

  async function runIngest() {
    setError(null);
    setIngesting(true);
    try {
      const result = await ingestDocuments();
      setIngestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to index SOPs.");
    } finally {
      setIngesting(false);
    }
  }

  function pickDemo(nextQuestion: string) {
    void submit(nextQuestion);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          <Building2 size={24} />
        </div>
        <div>
          <h1>Sentral Ops Private SOP Assistant</h1>
          <p>Axelyn Proof Lab</p>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="workspace">
        <section className="query-panel">
          <QuestionInput
            value={question}
            loading={loading}
            onChange={setQuestion}
            onSubmit={() => void submit()}
          />
          <AnswerCard response={response} loading={loading} />
        </section>

        <aside className="side-panel">
          <SystemNotice
            health={health}
            ingesting={ingesting}
            ingestResult={ingestResult}
            onIngest={() => void runIngest()}
          />
          <DemoQuestions questions={demoQuestions} onPick={pickDemo} />
        </aside>
      </div>
    </main>
  );
}
