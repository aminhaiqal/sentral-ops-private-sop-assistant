# Sentral Ops Private SOP Assistant

A proof-of-capability demo for Axelyn.

This project shows how approved internal company documents can become a controlled AI assistant that answers staff questions with source-backed responses and sensible operational boundaries.

The company data is fictional. It represents **Sentral Ops Supply Sdn. Bhd.**, a fictional B2B operations and facilities supply company in Klang Valley, Malaysia.

## What The Demo Proves

- Staff can ask internal operations questions in a simple web UI.
- Answers are generated only from approved markdown SOP documents.
- Each answer returns the source snippets used.
- Boundary-sensitive questions are flagged, including live delivery status, payment confirmation, stock availability, confidential data, and final approval authority.
- The implementation is intentionally small: FastAPI, Qdrant, OpenAI, and Vite React.

## Stack

- FastAPI backend on Python 3.12
- Qdrant vector database
- OpenAI embeddings and answer generation
- Vite + React + TypeScript frontend
- Docker Compose for local development and client demo runtime
- Production-style frontend container: static React build served by Nginx

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

## Retrieval Controls

The assistant rejects weak matches before answer generation. If no retrieved SOP chunk reaches `MIN_SOURCE_SCORE`, the API returns an `outside_scope` warning and does not send low-relevance snippets to the model.

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

- Source-backed RAG over approved fictional SOP markdown files.
- Explicit boundary warnings for live ETA, payment confirmation, confidential data, public AI use, substitution, stock, and approval authority.
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
