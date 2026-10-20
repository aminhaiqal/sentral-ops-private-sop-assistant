# Configuration

Copy `.env.example` to the repository root as `.env`. The backend loads that file
regardless of its working directory. Process environment variables take precedence;
Docker Compose also overrides several values for its internal service network.
Restart the local backend or recreate containers after changing server settings.

```bash
docker compose up -d --force-recreate backend
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
| `WORKSPACE_COOKIE_SECURE` | `false` | Require HTTPS for the workspace cookie; production Compose sets `true` |
| `VITE_API_URL` | Empty | Frontend build-time override; empty uses the same-origin `/api` proxy |
| `APP_DOMAIN` | Unset | Hostname required by the HTTPS Compose configuration |
| `SENTRAL_RELEASE` | `latest` | Local image tag used by production Compose |

Raise the source threshold to reject more weak matches. Lower it only after inspecting
missed questions and their source excerpts. Thresholds depend on the embedding model
and corpus; they are not calibrated confidence scores.

The frontend's `VITE_API_URL` is embedded during its build. Local Vite uses
`frontend/.env.local` or its process environment for overrides, rather than the root
backend `.env`. Both Compose files explicitly build it with the same-origin proxy.

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
and cookie behavior.
