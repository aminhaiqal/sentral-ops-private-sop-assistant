# Axelyn

A small workspace for turning a request and source documents into a cited document.
Add PDF or Markdown files, describe what you need, and open or download the result.
Tasks continue in the background; History keeps previous work available.

There are no bot profiles, templates, routines, or separate workflow builders.

## Run locally

You need Docker Compose, an AI provider supporting the Responses and embeddings APIs,
a Clerk application, and a private Cloudflare R2 bucket for source documents.

```bash
cp .env.example .env
```

Configure these values in `.env`:

- `OPENAI_API_KEY`, and the provider URL and models if using a custom provider.
- `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_ISSUER_URL` from the same Clerk application.
- `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`.

```bash
docker compose up --build
```

Open [localhost:5173](http://localhost:5173), sign in, add your documents, and submit a
request. Documents remain available for later tasks. No demo documents are seeded.
Use **History** to return to ongoing or completed tasks. A task that needs information
shows a reply field; failed tasks can be retried and active tasks can be stopped.

## How it works

React calls an authenticated FastAPI API. A separate worker searches account-scoped
Qdrant vectors, writes a Markdown artifact, reads it back, and checks its citation
labels before completion. SQLite stores tasks and results; R2 stores source files.
The same Clerk account can access its work across sessions and devices.

Completion checks establish that an artifact was saved and read back with valid
citation labels. They do not establish factual accuracy or full satisfaction of the
request. Source excerpts and execution activity are available beside each result.

## API

The API reference is at [localhost:8000/docs](http://localhost:8000/docs).
Private requests require a Clerk session bearer token.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/tasks` | Start a task with `{"goal":"Your request"}` |
| `GET /api/tasks` | List recent tasks |
| `GET /api/tasks/{id}` | Read status, artifacts, sources, and activity |
| `POST /api/tasks/{id}/resume` | Supply `{"message":"More context"}` |
| `POST /api/tasks/{id}/cancel` | Stop a task |
| `/api/documents` | List, upload, index, download, and delete source files |
| `/api/health`, `/api/ready` | API and retrieval health |

## Develop

With Python 3.12 and Node.js 24 installed:

```bash
make setup
make check
npm --prefix frontend run test:browser
```

The tests use fictional inline fixtures and mocked providers; no private keys or
external model calls are needed. See [Contributing](CONTRIBUTING.md).

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Deployment](docs/deployment.md)
- [Security](SECURITY.md)

Existing task history and uploads remain accessible after upgrading. The retired bot,
routine, Studio, connections, standalone Q&A, and demo-ingestion APIs are removed.
