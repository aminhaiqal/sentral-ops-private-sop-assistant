# Contributing

Contributions should make this project easier to learn from or more useful to run.
Small, focused pull requests are welcome. For a large feature or architectural change,
open an issue first so we can agree on the direction.

## Development setup

Use Python 3.12, Node.js 24, npm, and Docker Compose. The backend's PDF subprocess
uses POSIX resource limits; use macOS, Linux, or WSL for backend development. Native
macOS runs use CPU and wall-clock limits; use Docker for the Linux memory cap as well.

From the repository root:

```bash
cp .env.example .env
make setup
docker compose up -d qdrant
```

Add an API key to `.env` for indexing and answers. You can work on tests, documentation,
and most UI changes without one. R2 is only required for document uploads.

In one terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm run dev
```

Use `http://localhost:5173` consistently. The Vite development server proxies `/api`
to the backend on port 8000. The backend reads the root `.env` regardless of its
working directory. Use `PYTHON=/path/to/python3.12 make setup` if needed.

Without Make, create `backend/.venv` with `python3.12 -m venv backend/.venv`, install
`backend/requirements-dev.txt` using that environment's pip, then run `npm ci` in
`frontend/`.

## Checks

```bash
make check       # Ruff lint and format, Prettier, pytest, TypeScript, Vite build
make format      # Apply import sorting and formatting
make test        # Backend tests only
make build       # Frontend type check and production build
```

The backend tests mock AI and object-storage calls and use Qdrant's in-memory mode.
Do not add tests that spend API credits or depend on private credentials. Add focused
regression coverage when changing behavior. A passing frontend build checks TypeScript
types; it does not prove compatibility with the API or correct browser behavior.

Before opening a PR, run `make check`. For changes to containers or networking, also run:

```bash
docker compose --env-file .env.example config --quiet
APP_DOMAIN=assistant.example.com docker compose --env-file .env.example -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.example build
```

For manual retrieval checks, use the questions in the README and
[sample upload guide](sample-uploads/README.md). Check the answer, citations, excerpts,
warnings, and Agent Trace. Mention which checks you ran in your PR.

## Useful starting points

- **Documentation:** improve setup instructions after trying them on a clean machine.
- **Retrieval:** add a missed SOP question as a test, then adjust the query rules.
- **Accessibility:** improve keyboard navigation and screen-reader feedback.
- **Uploads:** add malformed-file and provider-failure regression cases.
- **Evaluation:** add a small fictional question set with expected source documents.

Keep sample data fictional. Preserve the existing license and attribution. Never
include real internal documents, API keys, bucket contents, customer records, or
private deployment details in an issue, test fixture, screenshot, or PR.

## Dependencies

`backend/pyproject.toml` is the source for Python dependencies. The runtime and
development requirements files are generated, pinned install sets. After changing
dependencies, regenerate both with [uv](https://docs.astral.sh/uv/):

```bash
uv pip compile backend/pyproject.toml --universal --python-version 3.12 --output-file backend/requirements.txt
uv pip compile backend/pyproject.toml --extra dev --universal --python-version 3.12 --output-file backend/requirements-dev.txt
```

Update `frontend/package-lock.json` with npm when changing frontend dependencies.
Run `npm audit` in `frontend/` after updates. Dependency updates still need the normal
tests and build checks.

## Working together

Describe the problem, the resulting behavior, and how you checked it. Share enough
context to reproduce bugs. Be respectful, assume good intent, and keep feedback about
the work. Report sensitive security issues through [SECURITY.md](SECURITY.md).
