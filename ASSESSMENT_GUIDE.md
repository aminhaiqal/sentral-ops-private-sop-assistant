# Assessment Guide: Question 1 - Agentic RAG

This project is prepared for Question 1 from the assessment:

- Build an Agentic RAG that retrieves chunks correctly.
- Demo a working prototype.
- Discuss thought process and implementation flow.
- Investigate Agentic RAG as a whole.
- Compare traditional RAG and agentic RAG.
- Explain test cases used to assure quality.
- Bonus: citations, retrieval accuracy, performance, Docker deployment.

## Prototype Summary

The system is a private SOP assistant for a fictional Malaysian operations company,
Sentral Ops Supply Sdn. Bhd. Staff ask operational questions in a React web UI. The
FastAPI backend retrieves approved SOP chunks from Qdrant, applies guardrails, and asks
OpenAI to synthesize a source-backed answer.

The frontend shows:

- The answer.
- Boundary warnings when the question asks for live status, payment confirmation,
  approval authority, confidential data, public AI use, stock, or substitution.
- An Agent Trace showing the backend's reasoning workflow.
- Source citations such as `S1`, `S2`, and the exact retrieved chunks.

## Agentic RAG Flow

The backend implements a small deterministic agent workflow in `backend/app/rag.py`.
It is intentionally lightweight, explainable, and testable.

1. Boundary check
   - Uses rule-based guardrails to detect high-risk operational questions.
   - Examples: live ETA, payment confirmation, confidential data, approval decisions.

2. Query planning
   - Starts with the user's original question.
   - Adds focused retrieval queries based on detected intent and guardrail category.
   - Example: "Can staff paste invoice data into ChatGPT?" also searches for invoice
     handling and confidential-data AI policy chunks.

3. Multi-query retrieval
   - Embeds each planned query.
   - Runs vector search against Qdrant for each query.
   - Deduplicates repeated chunks by `chunk_id`.
   - Keeps the best score for duplicate chunks.

4. Grounding check
   - Applies `MIN_SOURCE_SCORE` to reject weak matches.
   - Limits context with `MAX_CONTEXT_SOURCES` to keep answer generation focused.
   - If no source passes the threshold, the assistant refuses to answer as policy.

5. Answer synthesis
   - Sends only approved source excerpts to the LLM.
   - Requires source IDs like `[S1]` on factual claims.
   - Returns the sources and Agent Trace to the client for inspection.

## Traditional RAG vs Agentic RAG

Traditional RAG usually follows a single fixed path:

1. Embed the user question.
2. Retrieve top-k chunks.
3. Put chunks in the prompt.
4. Generate an answer.

Agentic RAG adds decision points around retrieval and grounding:

- It plans retrieval instead of relying on one query.
- It can run several focused searches for one user question.
- It checks whether the retrieved evidence is good enough before generating.
- It exposes intermediate steps so users can inspect the workflow.
- It can combine tools such as guardrails, vector search, source filtering, and answer
  generation into one controlled process.

This project keeps the agent deterministic rather than asking the LLM to plan. That makes
the demo easier to test, cheaper to run, and safer for SOP workflows where explainability
matters.

## Retrieval Accuracy And Performance

Accuracy controls:

- Markdown documents are split into deterministic overlapping chunks.
- Domain-specific planned queries improve recall for multi-intent questions.
- Duplicate chunks are merged before ranking.
- Low-score chunks are filtered out before the LLM sees them.
- The UI shows source scores and excerpts for manual inspection.

Performance controls:

- The retrieval plan is capped at three queries.
- Embeddings for planned queries are requested in one batch.
- Context is capped with `MAX_CONTEXT_SOURCES`.
- Qdrant handles vector search efficiently.
- The deterministic planner avoids an extra LLM planning call.

## Test Methodology

Backend tests are in `backend/tests`.

Run them with:

```bash
cd backend
pytest
```

Current test coverage focuses on:

- Chunking quality
  - Stable chunk IDs.
  - Reasonable word limits.
  - Overlap behavior.

- Guardrails
  - Public AI and confidential-data detection.
  - Payment confirmation boundaries.
  - Live delivery ETA boundaries.
  - Approval authority boundaries.
  - Product substitution boundaries.
  - False-positive checks for normal SOP questions.

- Agentic RAG helpers
  - Domain-specific retrieval planning.
  - Boundary warnings feeding focused retrieval.
  - Deduplication of duplicate chunks.
  - Relevance threshold filtering.
  - Citation label assignment.

Frontend verification:

```bash
cd frontend
npm run build
```

The build confirms TypeScript schemas match the backend response shape, including
`agent_steps` and source `citation` fields.

## Demo Script

Recommended 15 to 20 minute flow:

1. Explain the problem
   - Staff need fast SOP answers without exposing confidential data or inventing live
     operational status.

2. Show architecture
   - React UI, FastAPI backend, OpenAI embeddings and chat model, Qdrant vector store,
     markdown SOP corpus.

3. Run ingestion
   - Click the indexing button or call `POST /api/ingest`.

4. Ask normal SOP questions
   - "What is the refund approval process for damaged goods?"
   - Show answer, citations, source snippets, and Agent Trace.

5. Ask boundary-sensitive questions
   - "Can staff paste invoice data into ChatGPT?"
   - "What is today's delivery ETA?"
   - Show warning behavior and grounded SOP response.

6. Ask an out-of-scope question
   - Use a question not covered by the SOP documents.
   - Show that the assistant refuses when no source passes the threshold.

7. Explain tests and quality controls
   - Run `pytest`.
   - Explain retrieval thresholds, citations, source inspection, and guardrail tests.

8. Close with production considerations
   - Authentication, RBAC, audit logging, document approval workflow, monitoring,
     private networking, and stronger prompt-injection testing.

## Docker Demo

The project includes Docker support for the assessment bonus point:

```bash
cp .env.example .env
docker compose up --build
```

Frontend:

```text
http://localhost:5173
```

Backend:

```text
http://localhost:8000
```
