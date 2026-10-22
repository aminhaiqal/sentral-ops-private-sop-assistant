# Contributing

Keep the project focused on one document-task workflow. Preserve the existing license
and attribution. Use fictional fixtures; keep real documents, tokens, and keys out of Git.

## Development

Use Python 3.12, Node.js 24, and Docker Compose. macOS, Linux, or WSL is required for
the PDF subprocess resource limits. Docker also enforces the Linux memory cap.

```bash
cp .env.example .env
make setup
docker compose up -d qdrant
```

Configure the root environment as described in [Configuration](docs/configuration.md).
Run these in separate terminals:

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

```bash
cd backend
.venv/bin/python -m app.harness.worker
```

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the backend on port 8000.

## Checks

```bash
make check                              # Formatting, backend/frontend tests, production build
npm --prefix frontend run test:browser  # Browser workflow and responsive layout
make format                             # Apply formatting
```

Backend tests mock providers and storage, generate their own auth keys, and use
in-memory Qdrant. Browser tests use a mocked task API and do not contact Clerk or AI
providers. Install Chromium once with `cd frontend && npx playwright install chromium`.

For container changes, also validate both Compose configurations and build:

```bash
docker compose --env-file .env.example config --quiet
APP_DOMAIN=assistant.example.com VITE_CLERK_PUBLISHABLE_KEY=pk_live_example CLERK_ISSUER_URL=https://clerk.example.com docker compose --env-file .env.example -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.example build
```

## Dependencies

`backend/pyproject.toml` defines Python dependencies. The requirements files pin their
install sets. Regenerate both after a dependency change:

```bash
uv pip compile backend/pyproject.toml --universal --python-version 3.12 --output-file backend/requirements.txt
uv pip compile backend/pyproject.toml --extra dev --universal --python-version 3.12 --output-file backend/requirements-dev.txt
```

Use npm to update the frontend lockfile when changing its dependencies. Describe the
resulting behavior and validation in each PR. Report security issues through
[SECURITY.md](SECURITY.md).
