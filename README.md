# Sentral Ops

An open-source SOP assistant you can run, understand, and improve.

Ask a question about company procedures and get an answer with citations, the retrieved
source text, and a trace of each retrieval step. Built with React, FastAPI, Qdrant, and an
OpenAI-compatible API. The included company and its 11 SOPs are fictional.

## What you can explore

- **Retrieval you can inspect.** A deterministic planner creates up to three search
  queries, merges the results, and filters weak matches before generating an answer.
- **Sources beside the answer.** Citation labels connect answers to retrieved excerpts.
- **Operational boundaries.** Rule-based warnings flag requests for live status,
  confidential data, and approval decisions.
- **Your own documents.** Upload text-based PDFs and Markdown with optional private R2
  storage. Each browser workspace has its own document and retrieval scope.
- **Conversation context.** Recent turns support follow-up questions; chat history stays
  in the browser.

## Run locally

You need Docker Compose and an API key for the configured AI provider. API requests
use your provider's credits. R2 is optional when using the bundled SOPs.

```bash
git clone https://github.com/aminhaiqal/sentral-ops-private-sop-assistant.git
cd sentral-ops-private-sop-assistant
cp .env.example .env
```

Add your key to `OPENAI_API_KEY` in `.env`, then start the app:

```bash
docker compose up --build
```

Open **[localhost:5173](http://localhost:5173)**. Startup indexing runs when the shared
collection is empty and a key is configured. The frontend proxies API calls to the
backend; no credentials are sent to the browser.

Try asking:

- What is the refund approval process for damaged goods?
- When should a delivery delay be escalated?
- Can staff paste invoice data into ChatGPT?
- What is today's delivery ETA?

The API reference is at [localhost:8000/docs](http://localhost:8000/docs). To inspect
startup or indexing problems:

```bash
docker compose logs backend
curl http://localhost:8000/api/ready
```

Stop with `docker compose down`. The Qdrant volume is retained between runs.

## Learn the code

```text
frontend/src/       Chat UI, document library, browser history, source inspection
backend/app/       API, retrieval, guardrails, ingestion, document storage
backend/tests/     Offline tests with mocked providers and in-memory storage
data/sentral_ops/  Fictional Markdown SOP corpus
sample-uploads/    Four sample PDFs and questions with expected answers
deploy/            Portable HTTPS reverse-proxy configuration
docs/              Architecture, configuration, and deployment guides
```

Start with [the architecture guide](docs/architecture.md), then follow a question
through [`rag.py`](backend/app/rag.py). For uploads, start with
[`uploads.py`](backend/app/uploads.py) and the
[sample questions](sample-uploads/README.md).

| I want to… | Read |
| --- | --- |
| Understand chunking, retrieval, and grounding | [Architecture](docs/architecture.md) |
| Run the backend and frontend with hot reload | [Contributing](CONTRIBUTING.md) |
| Change providers, models, or upload storage | [Configuration](docs/configuration.md) |
| Host an HTTPS instance | [Deployment](docs/deployment.md) |
| Report a security issue | [Security policy](SECURITY.md) |

## Contribute

Bug fixes, clearer docs, retrieval improvements, accessibility fixes, and new tests
are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and useful starting points.
With Python 3.12 and Node.js 24 installed:

```bash
make setup
make check
```

The checks run offline without an AI key, R2 account, or running Qdrant server. CI runs
the same code checks, validates container builds, and scans Git history for secrets.

## Scope

This is an educational reference application. It has no user login, role-based access,
rate limiting, document approval workflow, or live business-system integration. A
workspace cookie scopes uploads; it does not establish a user's identity. Model
citations and rule-based warnings need human review and can be wrong.

Documents are sent to the configured embedding and answer provider as part of retrieval
and generation. Use fictional data while exploring. Read [SECURITY.md](SECURITY.md)
before hosting an instance or adapting it for real internal documents.

## License

[MIT](LICENSE), including the fictional sample documents. Copyright remains with the
project's author and contributors.
