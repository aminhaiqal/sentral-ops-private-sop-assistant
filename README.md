# Axelyn

A workspace for an AI team that takes document tasks from a goal to a saved deliverable.

Choose a bot, assign a task, and let the background worker research your knowledge,
write a cited document, and check the saved result. Open the deliverable from the
conversation, save preferences in bot memory, and schedule work to repeat while you’re
away. Built with React, Clerk, FastAPI, SQLite, Qdrant, and a Responses-compatible AI
provider. The included Sentral Ops company and its 11 SOPs are fictional sample data.

## What you can explore

- **Retrieval you can inspect.** A deterministic planner creates up to three search
  queries, merges the results, and filters weak matches before generating an answer.
- **Sources beside the answer.** Citation labels connect answers to retrieved excerpts.
- **Operational boundaries.** Rule-based warnings flag requests for live status,
  confidential data, and approval decisions.
- **Your own documents.** Upload text-based PDFs and Markdown with optional private R2
  storage. Each signed-in account has its own document and retrieval scope.
- **A team inbox.** Chief of Staff, Operations, Research Analyst, and Customer Support
  have separate instructions, memory, and task conversations. Create your own bots.
  Task history and deliverables are stored on the server and sync across sessions.
- **Scheduled routines.** Run document tasks daily, on weekdays, or weekly in your
  timezone. Pause, edit, delete, or run a routine immediately from bot details.
- **Autopilot harness.** Submit a document task with completion criteria. A separate
  worker chooses tools, searches SOPs, saves a cited deliverable, and checks it before
  marking the task complete. Progress and results survive worker restarts.
- **Bot memory.** Give a bot standing instructions and editable preferences. Subsequent
  jobs retrieve those preferences and prior artifact-check outcomes from SQLite.

## Bot Studio

Open **Bot Studio** from the sidebar to create a Lead Research Bot using a simple
form. It runs Research → Analyze → Save → Draft through registered skills, saves
account-scoped execution history, and generates outreach drafts without sending.
Web research requires a server-managed Brave Search API key; missing providers
produce setup instructions and a saved configuration error.

See [Bot Studio setup, architecture and verification](docs/bot-studio.md).

**Connections** adds Google Drive with direct Google authorization. Click **Connect**,
search and preview files, then select up to two documents as a bot's background
context. Drive access is optional and restricted to reading; Google authorization
requires server configuration. See [Google Drive setup](docs/google-drive-connections.md).

## Run locally

You need Docker Compose and an API key for the configured AI provider. API requests
use your provider's credits. R2 is optional when using the bundled SOPs.

```bash
git clone https://github.com/aminhaiqal/sentral-ops-private-sop-assistant.git
cd sentral-ops-private-sop-assistant
cp .env.example .env
```

Add your AI key to `OPENAI_API_KEY` in `.env`. Create or select an application in the
[Clerk Dashboard](https://dashboard.clerk.com/) and add its public configuration:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_publishable_key
CLERK_ISSUER_URL=https://your-instance.clerk.accounts.dev
```

Use the publishable key and Frontend API/issuer origin from the same Clerk instance.
The backend fetches that instance's public signing keys; no Clerk secret key is needed.
Then start the app:

```bash
docker compose up --build
```

Open **[localhost:5173](http://localhost:5173)**. Startup indexing runs when the shared
collection is empty and a key is configured. The frontend proxies API calls to the
backend. Clerk handles sign-in and sign-up; the frontend sends a fresh session bearer
token with each private API request. AI and storage credentials stay on the backend.
Missing Clerk configuration leaves private routes closed.

Try assigning a task:

- Prepare an operations briefing with the key policies and escalation paths.
- Create a checklist for handling delayed deliveries.
- Draft a customer response guide for refund requests.

Use **Knowledge** to upload your documents. Use **Bot details** to edit a bot, schedule
routines, and manage memory. The plus button in the composer opens the knowledge
library; uploads become available to all bots in your account once indexed.

The API reference is at [localhost:8000/docs](http://localhost:8000/docs). To inspect
startup or indexing problems:

```bash
docker compose logs backend
curl http://localhost:8000/api/ready
```

Stop with `docker compose down`. The Qdrant volume is retained between runs.

## Run an autopilot task

Compose starts the API and harness worker together. Assign tasks in the bot
conversation at [localhost:5173](http://localhost:5173). Progress updates automatically;
you can close the page and return to the work. If a bot needs information, choose
**Reply to this task** to continue the same run.

For API access, open [localhost:8000/docs](http://localhost:8000/docs) and use
**Autopilot tasks**, or submit a job from a terminal using your current Clerk session token in the local
`SENTRAL_SESSION_TOKEN` environment variable. Keep that token private. Swagger's
**Authorize** button accepts the same session token.

```bash
curl -H "Authorization: Bearer $SENTRAL_SESSION_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Prepare a delivery-delay escalation checklist","completion_criteria":"Save a practical Markdown checklist with citations to the relevant SOPs."}' \
  http://localhost:8000/api/tasks
```

The response is a queued task. Copy its `id`, then read its progress and deliverable:

```bash
curl -H "Authorization: Bearer $SENTRAL_SESSION_TOKEN" http://localhost:8000/api/tasks/TASK_ID
```

The worker runs search, write, read-back, and completion tools autonomously. A
`needs_input` task identifies a blocker; provide context through
`POST /api/tasks/TASK_ID/resume` with `{"message":"Your clarification"}`. Cancel
through `POST /api/tasks/TASK_ID/cancel`. Limits apply across retries and resumes.

The bot workspace uses the background task API. The original question-answering
endpoint remains available through `/api/ask`. Email, calendar, browser automation,
and other external app actions are not connected. Bots can research documents and
save Markdown deliverables; they cannot send messages or change external systems.
Completion checks validate saved artifacts and citation labels, not factual accuracy
or semantic satisfaction of every requested criterion. See the
[harness architecture](docs/architecture.md#autopilot-harness) for the execution model.

## Try bot memory

To see the complete memory lifecycle without an AI key, Qdrant, or Docker:

```bash
cd backend
.venv/bin/python -m app.harness.memory_demo
```

This uses a **scripted model and a fictional SOP** to exercise the real harness and
SQLite store. It saves a checklist preference, runs a job, reopens the database,
edits the preference, and runs a second job that sees the correction and previous
outcome. It then deletes the preference and checks that retrieval omits it. The
command prints the database path so you can inspect the records afterward. Each run
uses a separate demo database under `var/`; it never calls the model provider.

In the workspace, choose **Bot details → Memory** to add, edit, or forget a
preference. Completed jobs also leave artifact-check records that later tasks can
recall. Bot instructions are editable through **Edit bot**.

For API-driven jobs, open `/docs` and use **Bot profiles and memory**:

1. `POST /api/bots` with `{"name":"Operations","role":"Prepare SOP-backed guides","instructions":"Use plain language."}`.
2. Copy the bot `id`, then `PUT /api/bots/BOT_ID/preferences/report_format` with `{"value":"checklist"}`.
3. Submit `POST /api/tasks` with that `bot_id`, a `goal`, and `completion_criteria`.
4. Inspect `GET /api/bots/BOT_ID/memories` for preferences and completed-task evidence.
5. Edit a preference with the same PUT endpoint, or delete a record through `DELETE /api/bots/BOT_ID/memories/MEMORY_ID`.

Use a Clerk session token for the same account on all requests. Preferences can have
an optional timezone-aware `expires_at`; expired records are excluded from retrieval.
Bot memory is isolated by account and bot. The account's workspace remains stable
across sessions and devices. Existing anonymous workspaces are retained in storage
but are not automatically assigned to a newly signed-in account.

The model cannot create preferences or mark its own assertions as verified memories.
Completion records are produced by the harness after artifact checks, in the same
transaction as task completion. They establish those checks, not semantic accuracy
or the outcome of an external app action.

## Learn the code

```text
frontend/src/       Bot inbox, task conversations, routines, memory, knowledge and previews
backend/app/       API, retrieval, guardrails, ingestion, document storage, harness
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

This is an educational reference application with Clerk authentication and individual
account workspaces. It has no team/organization permissions, global API rate limiting,
or document approval workflow. Google Drive connections have a separate account-scoped
rate limit and require a configured Google OAuth client. Model citations and rule-based
warnings need human review and can be wrong. Browser chat history stays on the device,
scoped by account; documents, tasks, and bot memory persist on the backend.

Documents are sent to the configured embedding and answer provider as part of retrieval
and generation. Use fictional data while exploring. Read [SECURITY.md](SECURITY.md)
before hosting an instance or adapting it for real internal documents.

## License

[MIT](LICENSE), including the fictional sample documents. Copyright remains with the
project's author and contributors.
