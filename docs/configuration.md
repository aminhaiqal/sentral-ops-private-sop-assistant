# Configuration

Copy `.env.example` to `.env` at the repository root. The backend reads it regardless
of its working directory. Keep credentials on the backend; `VITE_` values are public.
The API and worker need the same provider, retrieval, storage, and database settings.

## AI provider

| Variable | Default |
| --- | --- |
| `OPENAI_API_KEY` | Required for model and embedding requests |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `OPENAI_CHAT_MODEL` | `gpt-6-luna` |
| `OPENAI_REASONING_EFFORT` | `none` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536` |

The endpoint must support Responses tool calling and embeddings. Chat Completions
compatibility alone is insufficient. The worker uses `store=False` and passes
reasoning items back between turns. Provider usage is billed to your API account.

## Retrieval and storage

`QDRANT_URL` defaults to `http://localhost:6333`; Compose overrides it with the service
address. `QDRANT_COLLECTION` defaults to `sentral_ops_sops` to preserve existing
uploads. `MIN_SOURCE_SCORE` defaults to `0.22` and measures vector similarity, not
answer accuracy. Changing embedding dimensions requires a compatible collection
and a deliberate reindex of uploaded documents.

For a private R2 bucket, set `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and
`R2_SECRET_ACCESS_KEY`. `R2_PREFIX` defaults to `sentral-ops` to preserve existing
objects. Without storage configuration, document uploads are unavailable.

## Clerk authentication

Set `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_ISSUER_URL` from the same Clerk application.
The issuer must be an HTTPS origin. No Clerk secret key is required.

`CLERK_AUTHORIZED_PARTIES` is a comma-separated list of permitted frontend origins;
it defaults to `BACKEND_CORS_ORIGINS` (`http://localhost:5173`). Optional settings are
`CLERK_AUDIENCE` and `CLERK_JWT_KEY`, a PEM verification key. Otherwise public signing
keys are fetched from the configured issuer. Missing auth configuration fails closed.

Leave `VITE_API_URL` empty to use the frontend proxy. The publishable key is a
frontend build value; changing it requires rebuilding the frontend.

## Worker limits

| Variable | Default |
| --- | --- |
| `HARNESS_DB_PATH` | `var/harness.sqlite3` under the repository root |
| `HARNESS_MAX_TURNS` | `16` |
| `HARNESS_MAX_TOKENS` | `32000` |
| `HARNESS_MAX_CONTEXT_CHARS` | `200000` |
| `HARNESS_MAX_RUNTIME_SECONDS` | `600` |
| `HARNESS_REQUEST_TIMEOUT_SECONDS` | `60` |

Compose persists the database at `/app/var/harness.sqlite3`. Run one worker per
local database. Reported model usage excludes embeddings and requests whose usage
was lost before checkpointing. See [Architecture](architecture.md).
