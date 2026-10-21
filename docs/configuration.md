# Configuration

Copy `.env.example` to the repository root as `.env`. The backend loads that file
regardless of its working directory. Process environment variables take precedence;
Docker Compose also overrides several values for its internal service network.
Restart the local backend or recreate containers after changing server settings.

```bash
docker compose up -d --force-recreate backend worker
```

## AI provider

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | Empty | Backend credential for the configured provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API endpoint |
| `OPENAI_CHAT_MODEL` | `gpt-6-luna` | Answer model; choose a model available to your account |
| `OPENAI_REASONING_EFFORT` | `none` | Reasoning effort used by the client's GPT-6 handling |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Model used for documents and queries |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536` | Qdrant collection vector size; must match embedding output |

The configured endpoint must support both embeddings and chat completions. A custom
URL does not guarantee compatibility with every model's parameters. The client has
specific parameter handling for the existing GPT-6 defaults; other models use its
standard chat-completion path. Provider credentials belong only on the backend.
The autonomous task harness additionally requires Responses API support at the
configured endpoint. Its adapter uses Responses for all models and preserves reasoning
items across tool turns. Verify provider and model support before running tasks.

For example, an OpenRouter configuration uses its endpoint and provider-prefixed IDs:

```env
OPENAI_API_KEY=your-provider-key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_CHAT_MODEL=openai/gpt-6-luna
OPENAI_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Use model IDs available from your provider. Changing an embedding model requires a
fresh collection and reindexing. `OPENAI_EMBEDDING_DIMENSIONS` configures Qdrant; it
does not request a shortened embedding from the API.

## Clerk authentication

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_CLERK_PUBLISHABLE_KEY` | Empty | Public key for the frontend Clerk provider; embedded at build time |
| `CLERK_ISSUER_URL` | Empty | HTTPS Frontend API origin of the same Clerk instance |
| `CLERK_AUTHORIZED_PARTIES` | `BACKEND_CORS_ORIGINS` | Comma-separated frontend origins permitted in session tokens' `azp` claim |
| `CLERK_JWT_KEY` | Empty | Optional PEM **public** signing key; otherwise fetch the configured issuer's JWKS |
| `CLERK_AUDIENCE` | Empty | Optional expected `aud` claim if configured in your Clerk session tokens |

Create or select a Clerk application and copy its publishable key and Frontend API
origin from the dashboard. The issuer must be an HTTPS origin without a path, query,
or credentials. Local development defaults to `http://localhost:5173` as an authorized
frontend origin. Production Compose derives that origin from `APP_DOMAIN`.

Session verification uses RS256 signatures, the exact configured issuer, required
expiry/issued-at/not-before and identity/session claims, and an allowed `azp`. Pending
or inactive session statuses are rejected. Missing configuration fails closed. API
calls accept bearer session tokens; old workspace cookies cannot select an owner.
A Clerk secret key is not required for public-key verification. The optional public
PEM value can use literal `\n` escapes, which the backend normalizes.

Configure sign-in methods and production domains in Clerk. Personal account workspaces
are supported; organization roles and shared workspace membership are not implemented.
Clerk's short-lived session tokens are verified locally, with no per-request online
session-revocation lookup. See [Clerk's session verification guidance](https://clerk.com/docs/guides/sessions/manual-jwt-verification).

## Retrieval and networking

| Variable | Default | Purpose |
| --- | --- | --- |
| `QDRANT_URL` | `http://localhost:6333` | Vector database endpoint; Compose uses `http://qdrant:6333` |
| `QDRANT_COLLECTION` | `sentral_ops_sops` | Collection holding shared SOPs and scoped uploads |
| `MIN_SOURCE_SCORE` | `0.22` | Minimum similarity score before answer generation |
| `MAX_CONTEXT_SOURCES` | `5` | Maximum excerpts sent to the answer model |
| `AUTO_INGEST_ON_STARTUP` | `false` in code, `true` in the example | Index shared SOPs if the collection is empty |
| `DATA_DIR` | `data/sentral_ops` under the project root | Directory containing shared Markdown documents |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed browser origins |
| `VITE_API_URL` | Empty | Frontend build-time override; empty uses the same-origin `/api` proxy |
| `APP_DOMAIN` | Unset | Hostname required by the HTTPS Compose configuration |
| `SENTRAL_RELEASE` | `latest` | Local image tag used by production Compose |

Raise the source threshold to reject more weak matches. Lower it only after inspecting
missed questions and their source excerpts. Thresholds depend on the embedding model
and corpus; they are not calibrated confidence scores.

The frontend reads public `VITE_` values from the root `.env` or `.env.local` and its
process environment. Only `VITE_` variables are exposed to the frontend bundle; keep
AI and storage secrets outside that prefix. Both Compose files explicitly pass the
publishable key at build time and use the same-origin `/api` proxy. Rebuild the frontend
after changing its Clerk publishable key or API URL.

## Autopilot harness

| Variable | Default | Purpose |
| --- | --- | --- |
| `HARNESS_DB_PATH` | `var/harness.sqlite3` under the project root | Shared local SQLite database; Compose overrides it to `/app/var/harness.sqlite3` |
| `HARNESS_MAX_TURNS` | `16` | Maximum model requests per task, including failed or interrupted attempts |
| `HARNESS_MAX_TOKENS` | `32000` | Reported model-token allowance per task, checked between operations |
| `HARNESS_MAX_CONTEXT_CHARS` | `200000` | Maximum serialized model transcript size before another operation |
| `HARNESS_MAX_RUNTIME_SECONDS` | `600` | Active execution allowance, checked between operations |
| `HARNESS_REQUEST_TIMEOUT_SECONDS` | `60` | Provider request timeout; SDK automatic retries are disabled in the worker |

Turn, token, and runtime allowances are saved when a task is created and retained on
resume. Changing these defaults affects new tasks. The transcript limit and request
timeout use the worker's current configuration. Embedding usage and requests lost to a
crash are not included in reported model tokens. Provider input usage can exceed the
remaining allowance in a single request. Use account-level spending controls when
you need a hard financial cap.

Compose runs the separate worker automatically. For native development, start it in
another terminal after starting the API and indexing the fictional SOPs:

```bash
cd backend
.venv/bin/python -m app.harness.worker
```

Use `--once` to process at most one eligible job. The worker and API must share
`HARNESS_DB_PATH` on one host. The worker's process lock prevents concurrent workers
against the same database. Results are available through `/api/tasks`; the existing
chat interface continues using `/api/ask`.

Bot profiles and memories use that same database without additional configuration.
Include a workspace-owned `bot_id` when creating a task to enable memory retrieval.
Profiles and preferences can be managed through `/api/bots`. Preferences are bounded
to 20 per bot; automatic retrieval includes these active preferences and at most five
past outcomes. Memory context counts against `HARNESS_MAX_CONTEXT_CHARS`.

## Optional document uploads

Uploads require a private Cloudflare R2 bucket. Set all four credentials on the backend:

```env
R2_ENDPOINT=https://your-account-id.r2.cloudflarestorage.com
R2_BUCKET=your-private-bucket
R2_ACCESS_KEY_ID=your-access-key-id
R2_SECRET_ACCESS_KEY=your-secret-access-key
R2_PREFIX=sentral-ops
```

The backend needs object read, write, delete, and list access. Use bucket-scoped
credentials and keep the bucket private. No public bucket URL or browser-side R2
credentials are needed. Follow the provider's
[R2 token instructions](https://developers.cloudflare.com/r2/api/tokens/).

Without R2, the shared SOP assistant still works and document uploads are unavailable.
The prefix separates the application's objects from other bucket contents; workspace
IDs scope access within that prefix. See [architecture](architecture.md) for retention
and account workspace behavior.
