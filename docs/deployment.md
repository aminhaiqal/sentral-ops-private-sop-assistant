# Deployment

The default Compose file is for local development. Its published ports bind to
`127.0.0.1`. The HTTPS configuration is a portable hosting example with its own Caddy
proxy. It does not depend on an existing VPS, shared Docker network, or private domain.

Read [SECURITY.md](../SECURITY.md) before exposing an instance. Clerk authentication
protects individual workspaces. Rate limiting and team permissions remain unimplemented;
use fictional data while evaluating the reference application.

## HTTPS instance

Use a Linux server with Docker Compose, a domain pointing to it, and ports 80 and 443
available for Caddy. From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Set your AI key and append `APP_DOMAIN=assistant.example.com` using your actual
hostname, without `https://` or a path. Configure R2 only if you need uploads.
Set `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_ISSUER_URL` for your Clerk production instance,
and configure that frontend domain in Clerk. The publishable key is a frontend build
argument; changing it requires rebuilding the frontend image. Clerk secret keys are
not needed for this public-key verification integration.
Use a `pk_live_` publishable key from the claimed application's production instance.
Create that instance with `npx -y clerk@latest deploy` in your terminal and complete
the DNS and OAuth steps before switching the deployed app to its production keys.
The production configuration requires both public auth settings and restricts token
origins to `https://APP_DOMAIN`.

```bash
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --build --wait --wait-timeout 180
docker compose -f docker-compose.prod.yml ps
```

Caddy handles HTTPS. Only the proxy publishes host ports. The frontend forwards `/api`
to FastAPI, and Qdrant is reachable on the backend network. Production Compose sets
the allowed browser/token origin from `APP_DOMAIN`.

The example adds restart policies, service memory limits, health checks, and rotated
container logs. These do not replace monitoring, access control, or backups.
The `worker` service executes queued document tasks separately from API requests.
It and the backend share `harness_state` on this host. Run one worker and keep this
SQLite volume local; distributed workers and network-filesystem SQLite are unsupported.

## Updating an existing deployment

The former production example used an external shared proxy network. This configuration
runs its own proxy and needs exclusive use of ports 80 and 443. If a reverse proxy
already owns those ports, adapt the frontend routing and network to that proxy before
starting this configuration. Do not run a second listener on the same ports.

For a Docker network shared with an existing proxy, set `SHARED_PROXY_NETWORK` and
include the shared-proxy override on every command:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.shared-proxy.yml config --quiet
docker compose -f docker-compose.prod.yml -f docker-compose.shared-proxy.yml up -d --build --wait --wait-timeout 180
```

The override disables the standalone proxy and makes the frontend available to the
existing proxy as `sentral_frontend:5173`. Keep the host route in the existing proxy's
configuration. The `sentral` project name preserves the existing Qdrant volume and
adds the separate harness database volume; do not remove either volume during updates.

If the server already has AI and storage credentials in `.env`, keep them there.
Public production auth settings can be stored separately in `.env.production` and
loaded using `docker compose --env-file .env --env-file .env.production ...` with
the same Compose files. Environment files are excluded from Git and container build
contexts. Never copy a developer's entire environment over the server's credentials.

To apply source or configuration updates:

```bash
docker compose -f docker-compose.prod.yml up -d --build --force-recreate --wait --wait-timeout 180
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

## Indexing and health

The public proxy blocks `POST /api/ingest`. Run shared-corpus ingestion on the server:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.ingestion
```

`GET /api/health` checks that the API is running. `GET /api/ready` additionally checks
Qdrant connectivity. Neither verifies provider credits, model availability, or upload
storage. Ask a known fictional SOP question to check the complete retrieval path.
The readiness endpoint does not check the harness worker. Inspect `docker compose
-f docker-compose.prod.yml logs --tail=100 worker` and submit a fictional task to verify
background execution.

## Persistence and recovery

Qdrant vectors live in the `qdrant_storage` volume. Caddy certificates and configuration
use `caddy_data` and `caddy_config`. Upload originals, extracted text, and metadata live
in the configured R2 bucket. Chats live only in each browser's local storage.
Task transcripts, retrieved evidence, and Markdown artifacts live in `harness_state`.
Bot profiles, preferences, and cross-job outcome records share that database and volume.
Signing in to the same Clerk account restores access from another device or session.
Legacy anonymous workspace cookies no longer grant access to private endpoints.

Back up Qdrant and R2 separately. Avoid `docker compose down --volumes` unless you intend
to delete the local volumes. Deleting a volume does not delete R2 objects.
Back up the task database separately using SQLite's backup facility, or stop the
API and worker and take a consistent database/WAL backup. Do not copy only a live SQLite file
while ignoring its WAL. Automated task retention and deletion are not implemented.

Shared-corpus ingestion upserts stable chunk IDs without deleting old chunks. To rebuild
after removing SOPs or changing embeddings, select a fresh `QDRANT_COLLECTION`, restart
the backend, and ingest. Existing R2 upload metadata is not reset automatically; plan
upload reindexing separately before migrating a populated instance.
