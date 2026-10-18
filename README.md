# Sentral Ops Private SOP Assistant

A proof-of-capability demo for Axelyn and a prepared response for **Assessment Question 1:
Agentic RAG**.

This project shows how approved internal company documents can become a controlled AI
assistant that answers staff questions with source-backed responses, sensible operational
boundaries, and an inspectable agentic retrieval workflow.

The company data is fictional. It represents **Sentral Ops Supply Sdn. Bhd.**, a fictional B2B operations and facilities supply company in Klang Valley, Malaysia.

## What The Demo Proves

- Staff can ask internal operations questions in a simple web UI.
- Answers are generated only from approved markdown SOP documents.
- Each answer returns the source snippets used.
- The backend plans focused retrieval queries, runs multi-query vector search, deduplicates
  chunks, checks source sufficiency, and exposes an Agent Trace in the UI.
- Boundary-sensitive questions are flagged, including live delivery status, payment confirmation, stock availability, confidential data, and final approval authority.
- The implementation is intentionally small: FastAPI, Qdrant, OpenAI, and Vite React.

## Stack

- FastAPI backend on Python 3.12
- Qdrant vector database
- OpenAI embeddings and answer generation
- Vite + React + TypeScript frontend
- Docker Compose for local development and client demo runtime
- Production-style frontend container: static React build served by Nginx

## Assessment Guide

See [ASSESSMENT_GUIDE.md](ASSESSMENT_GUIDE.md) for the demo script, Agentic RAG
investigation, traditional RAG comparison, implementation flow, and test methodology.

## Quick Start

1. Copy the environment example:

```bash
cp .env.example .env
```

2. Add your OpenAI API key to `.env`.

3. Start the services:

```bash
docker compose up --build
```

4. Open the frontend:

```text
http://localhost:5173
```

The backend starts at `http://localhost:8000`. With `AUTO_INGEST_ON_STARTUP=true`, the backend ingests the fictional SOP documents when the collection is empty and an API key is configured.

You can also ingest manually:

```bash
curl -X POST http://localhost:8000/api/ingest
```

Health checks:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/ready
curl http://localhost:5173/health
```

## Hosted Demo

The VPS deployment serves the demo at **https://sentral.axelyn.com** using
`docker-compose.prod.yml`. Caddy terminates HTTPS on the existing `memora_public`
network. The frontend proxies `/api/*` to FastAPI on the same origin; FastAPI and
Qdrant have no published host ports.

The deployment lives at `/opt/sentral-ops-private-sop-assistant` on `memora_vps`.
Its `.env` stays outside Git with mode `600`. Qdrant persists in the
`sentral_qdrant_storage` Docker volume. The three containers have combined RAM
limits of 1,152 MiB, restart automatically, and rotate their logs.

After copying updated source files to the deployment directory, deploy with:

```bash
cd /opt/sentral-ops-private-sop-assistant
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d --wait --wait-timeout 180
docker compose -f docker-compose.prod.yml ps
```

The shared Caddy route is in `deploy/Caddyfile.sentral` and must also remain in
the Memora deployment source at `/opt/memora/infra/caddy/Caddyfile` so subsequent
proxy releases retain it. Cloudflare has an `A` record for `sentral.axelyn.com`
pointing to the VPS. Keep the configured OpenAI API key on the server; the
browser receives no API credentials.

This remains a public demo over fictional SOPs, with no application login.

## Document Uploads

Open **Documents** or use the paperclip in the message box to upload PDF and
Markdown files. Originals, extracted text, and document metadata are saved in
a private Cloudflare R2 bucket under `R2_PREFIX` (default: `sentral-ops`).
The backend uses the S3-compatible API; storage credentials never reach the browser.

Configure `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and
`R2_SECRET_ACCESS_KEY` in the server `.env`. The VPS uses its existing private R2
storage with a separate `sentral-ops/` prefix. No public bucket URL is needed.

- Each browser gets an unguessable, HttpOnly workspace cookie. Document listing,
  downloads, deletion, and vector retrieval are scoped to that workspace.
- Shared fictional SOPs remain available in every workspace. Uploaded documents
  from other workspaces are excluded by the vector database query.
- Uploads are limited to 10 MiB and 200,000 extracted characters. PDFs can have
  up to 100 pages and must contain selectable text. Scanned and password-protected
  PDFs return an actionable error. PDF parsing runs in a separate process with
  memory, CPU, and wall-clock limits.
- An embedding-provider failure leaves the original safely stored. The document
  is marked **Saved · Not searchable yet** with an indexing retry action.
  Rejected API keys and exhausted API credits show an administrator action rather
  than suggesting retries will fix the configuration. After correcting the server
  `.env`, recreate the backend container and retry indexing; re-uploading is unnecessary.
- Removing a document deletes its indexed text and its R2 objects. Identical
  uploads within a workspace reuse the same document and vector IDs.
- Chat history is stored in the current browser; recent conversation turns are
  included when answering follow-up questions.

Useful endpoints: `GET/POST /api/documents`,
`POST /api/documents/{id}/index`, `GET /api/documents/{id}/download`, and
`DELETE /api/documents/{id}`. Upload with a multipart `file` field and retain
the workspace cookie between requests. A valid OpenAI key is still required
for indexing and answer generation.

### OpenRouter

For an OpenRouter key, configure its API endpoint and provider-prefixed model IDs:

```env
OPENAI_API_KEY=<your OpenRouter key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_CHAT_MODEL=openai/gpt-6-luna
OPENAI_REASONING_EFFORT=none
OPENAI_EMBEDDING_MODEL=openai/text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

`OPENAI_API_KEY` is the shared credential setting for the configured endpoint.
An OpenRouter key cannot authenticate against the direct OpenAI API. With a direct
OpenAI key, retain `https://api.openai.com/v1` and the unprefixed model IDs.
The embedding model and dimensions remain the same across these two routes.
See [OpenRouter's SDK integration](https://openrouter.ai/docs/guides/community/openai-sdk)
and [embedding API](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request).

## Retrieval Controls

The default answer model is `gpt-6-luna` with `OPENAI_REASONING_EFFORT=none`,
which preserves the demo's fast, non-reasoning answer workflow. Set the effort
to `low` or higher to evaluate more reasoning on complex SOP questions.
GPT-6 requests omit sampling parameters when reasoning is enabled. If you
explicitly select `gpt-6-astra` or `gpt-6.1-sol`, an effort of `none` becomes
`low` because those models do not support `none`.

The embedding model remains `text-embedding-3-small`, so changing the answer
model does not require rebuilding document embeddings. See the official
[GPT-6 model guide](https://developers.openai.com/api/docs/guides/latest-model)
and [API pricing](https://developers.openai.com/api/docs/pricing).

The assistant rejects weak matches before answer generation. If no retrieved SOP chunk reaches `MIN_SOURCE_SCORE`, the API returns an `outside_scope` warning and does not send low-relevance snippets to the model.

The agentic retrieval workflow:

- Checks boundaries before retrieval.
- Builds up to three retrieval queries from the original question and detected intent.
- Embeds planned queries in one batch.
- Searches Qdrant for each query.
- Deduplicates chunks and keeps the best score.
- Adds citation labels such as `S1` and `S2`.
- Sends only threshold-passing excerpts to the answer model.

Default controls:

```env
MIN_SOURCE_SCORE=0.22
MAX_CONTEXT_SOURCES=5
```

Raise `MIN_SOURCE_SCORE` if the assistant is too willing to answer loosely related questions. Lower it slightly if valid SOP questions are rejected after adding new documents.

## Local Backend Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:

```bash
cd backend
pytest
```

## Local Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Demo Questions

Try questions such as:

- What is the refund approval process for damaged goods?
- When should a delivery delay be escalated to Operations Manager?
- Can staff paste invoice data into ChatGPT?
- What should support check before escalating a missing item?
- What is required before issuing a credit note?
- Can I approve a RM2,000 refund?
- Is customer ABC's payment confirmed?
- What is today's delivery ETA?
- Can I substitute clinic gloves without customer approval?

## Important Boundaries

This demo does not include authentication, billing, multi-tenancy, production observability, live operational system sync, or a complex admin dashboard.

The assistant does not confirm live status, make final approvals, expose confidential customer data, or replace manager judgment. It answers from the approved fictional documents and points staff to the correct operational next step.

## Client Demo Readiness

The current implementation is ready for a controlled client proof demo:

- Agentic, source-backed RAG over approved fictional SOP markdown files.
- Explicit boundary warnings for live ETA, payment confirmation, confidential data, public AI use, substitution, stock, and approval authority.
- Frontend Agent Trace showing boundary check, query planning, retrieval, grounding check, and answer synthesis.
- Citation-backed answers with matching source cards.
- Out-of-scope rejection using retrieval score thresholds.
- Dockerized backend, frontend, and Qdrant.
- Non-root backend container user.
- Static frontend build served by Nginx.
- Container health checks.
- Focused backend tests for chunking, guardrails, and source filtering.

## True Production Checklist

Before using this with real company data, add:

- Authentication and role-based access control.
- Tenant or workspace isolation if serving more than one company.
- Audit logs for questions, answers, source snippets, and user identity.
- Secrets management outside `.env`.
- TLS termination and private networking for Qdrant.
- Data retention, deletion, and re-ingestion procedures.
- Monitoring, alerting, and structured logs.
- Human approval workflow for document publication.
- Security review for prompt injection and data exfiltration paths.
