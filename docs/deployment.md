# Deployment

The default Compose file is for local development. Its published ports bind to
`127.0.0.1`. The HTTPS configuration is a portable hosting example with its own Caddy
proxy. It does not depend on an existing VPS, shared Docker network, or private domain.

Read [SECURITY.md](../SECURITY.md) before exposing an instance. This application has no
login or rate limiting. Use fictional data and restrict access at your proxy until you
add those controls.

## HTTPS instance

Use a Linux server with Docker Compose, a domain pointing to it, and ports 80 and 443
available for Caddy. From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Set your AI key and append `APP_DOMAIN=assistant.example.com` using your actual
hostname, without `https://` or a path. Configure R2 only if you need uploads.

```bash
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --build --wait --wait-timeout 180
docker compose -f docker-compose.prod.yml ps
```

Caddy handles HTTPS. Only the proxy publishes host ports. The frontend forwards `/api`
to FastAPI, and Qdrant is reachable on the backend network. Production Compose sets
the allowed browser origin and secure cookie from `APP_DOMAIN`.

The example adds restart policies, service memory limits, health checks, and rotated
container logs. These do not replace monitoring, access control, or backups.

## Updating an existing deployment

The former production example used an external shared proxy network. This configuration
runs its own proxy and needs exclusive use of ports 80 and 443. If a reverse proxy
already owns those ports, adapt the frontend routing and network to that proxy before
starting this configuration. Do not run a second listener on the same ports.

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

## Persistence and recovery

Qdrant vectors live in the `qdrant_storage` volume. Caddy certificates and configuration
use `caddy_data` and `caddy_config`. Upload originals, extracted text, and metadata live
in the configured R2 bucket. Chats live only in each browser's local storage.

Back up Qdrant and R2 separately. Avoid `docker compose down --volumes` unless you intend
to delete the local volumes. Deleting a volume does not delete R2 objects.

Shared-corpus ingestion upserts stable chunk IDs without deleting old chunks. To rebuild
after removing SOPs or changing embeddings, select a fresh `QDRANT_COLLECTION`, restart
the backend, and ingest. Existing R2 upload metadata is not reset automatically; plan
upload reindexing separately before migrating a populated instance.
