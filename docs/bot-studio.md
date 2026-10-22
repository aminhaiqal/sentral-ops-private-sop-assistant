# Bot Studio

Bot Studio turns a saved responsibility into a manually executed, observable job.
Open **Bot Studio** from the Axelyn sidebar, or visit `/#/studio` while signed in.
The existing document workspace and its routines remain available separately.
Studio V1 supports manual execution only.

Optional [Google Drive connections](google-drive-connections.md) let users select
up to two background documents. Their registered Drive context skill runs before
the existing sequence; bots without Drive selections keep the original behavior.

Signed-out Studio links hand the URL hash to Clerk before mounting sign-in. Only a
validated same-origin Studio return path is retained in session storage, scoped to
the Clerk application; it is cleared when the session becomes active. No session
tokens or credentials are stored by this handoff.

## First bot

1. Choose **Create bot**. V1 uses the **Lead Research Bot** template.
2. Give it a name and an objective. Enter a target industry, location, public-source
   qualification criteria, and a truthful description of your offering.
3. Review the four skills (Draft is selected by default and optional) and grant **Brave Search**, **AI provider**, and
   **Axelyn database**. Connections are managed by the server administrator; users
   grant each bot permission to use them. Optional Drive accounts are connected by
   each user through Connections and limited to explicitly selected files.
   No credentials belong in objectives.
4. Set the desired output, minimum fit score, maximum prospects (1–8), and minimum
   qualified count. Save the bot, then choose **Run bot**.
5. Open the run to inspect each skill, its redacted inputs and outputs, logs,
   source evidence, saved prospects, and outreach drafts. Nothing is sent.

The library supports creating, editing, enabling/disabling, deleting and executing
bots. Deletion removes a bot from the library and stops its active runs; execution
records remain available under **All executions**. Existing runs retain their saved
configuration snapshot. Edits affect future runs, while disabling a bot or revoking
its tools stops subsequent work in an active run.

## Configure providers

V1 uses one search provider: [Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get).
Create a Web Search API subscription/key in the
[Brave API dashboard](https://api-dashboard.search.brave.com). On the host, add
`BRAVE_SEARCH_API_KEY` to the environment used by **both the API and worker**.
Do not put the value in a browser variable, bot configuration, source control or chat.
Existing Compose services both load the server's `.env`; use your host editor to add
this setting, then recreate the API and worker. With the development Compose file:

```bash
docker compose up -d --build backend worker
```

For native development, use the project's existing root configuration and start the
API and worker from `backend/` in separate terminals:

```bash
.venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m app.harness.worker
```

The AI connection reuses `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL` and
`OPENAI_REASONING_EFFORT`. The configured provider/model must support the Responses
API with [strict structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
There is no silent fallback to unvalidated JSON or fabricated research.

`GET /api/studio/catalog` returns connection readiness and setup instructions, never
credentials. A missing or rejected provider produces a persisted configuration error
with instructions. Creating a bot does not call a provider. The database connection
is built in; each record is bound to the verified Clerk account workspace.

Optional administrator settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `STUDIO_MAX_TOKENS` | `40000` | Total charged token bound per run |
| `STUDIO_MAX_API_CALLS` | `8` | Search and AI requests, including retries |
| `STUDIO_MAX_LLM_CALLS` | `4` | AI requests, including retries |
| `STUDIO_RUN_TIMEOUT_SECONDS` | `240` | Deadline from the first execution start |
| `STUDIO_INPUT_USD_PER_MILLION` | unset | Your configured model's input price |
| `STUDIO_OUTPUT_USD_PER_MILLION` | unset | Your configured model's output price |
| `STUDIO_MAX_COST_USD` | `0.50` | AI spending ceiling when both prices are configured |

Use your provider's actual rates for the configured model. Without both rates, the
UI explicitly shows **Rates not configured** and enforces token/API limits instead
of claiming a dollar estimate. Search-provider fees are not included in AI cost.
Before each AI request the runtime reserves a conservative UTF-8 byte bound for
input tokens plus the output cap. Known usage replaces that reservation. Lost,
timed-out or interrupted requests retain the reservation and are marked unreported.

## Architecture

No new service, ORM, graph engine or queue is introduced. `httpx`, already installed
with the AI SDK, is declared as a production dependency. Optional Drive connections
add the official `mcp` SDK, its `httpx2` transport, `jsonschema` validation,
Authlib for direct Google OAuth and cryptography for encrypted token storage.
Drive tools run in-process over the stable Google API.
Playwright is a development-only dependency for repeatable browser verification.

- React uses the existing authenticated API client and Clerk session boundary.
- FastAPI exposes account-scoped `/api/studio` routes.
- Studio tables use the existing `TaskStore.connection()` and SQLite database/volume.
- The existing worker alternates between Studio jobs and document tasks, under the
  same process lock. Restart recovery preserves completed steps and usage reservations.
- Code-defined templates specify approved registered sequences; Lead Research permits
  Research → Analyze → Save, optionally followed by Draft. Selected Drive sources
  prepend the registered Drive context skill. Users cannot submit
  executable code, custom tool endpoints, arbitrary skill identifiers or workflows.

The default Lead Research sequence is:

1. **Research:** up to two deterministic Brave queries, at most 16 candidate sources.
   Search snippets are untrusted data. Only validated public HTTPS source links are
   accepted; the server never fetches prospect URLs or follows search API redirects.
2. **Analyze:** one schema-constrained AI evaluation of every candidate. Company names
   and evidence quotes must match the retrieved source text. Code validates IDs,
   scores and provenance, removes duplicates by source host and normalized company
   name, and caps the number of qualified results.
3. **Save:** commit qualified prospects and the Save step output in one transaction.
   A stable account/bot/host identity also makes repeated saves idempotent.
4. **Draft:** one schema-constrained AI request produces exactly one outreach draft
   for each saved prospect. It cannot send messages or select additional tools.

Every skill has an identifier, description, typed input/output schemas, permitted
tools, effect classification and handler in `registry.py`. Per-skill data is
validated before and after execution. The shared contracts do not depend on a
specific bot ID, so additional code-reviewed templates can reuse these skills.
Configuration belongs to the typed bot target, expected-results and optional Drive source schemas;
no free-form skill program or arbitrary configuration dictionary is accepted.

Data records:

| Record | Storage |
| --- | --- |
| Templates and skill definitions | Versioned code and catalog metadata |
| Individual bots/configurations | `studio_bots`, revisioned configuration JSON |
| Runs | `studio_runs`, submission key, configuration snapshot, usage and limits |
| Steps/results/logs | Typed, checkpointed run state with timestamps and redacted data |
| Qualified prospects | `studio_prospects`, isolated by account and bot |
| Approval requests | Typed run-state contract; empty in V1 because no external action exists |

Submission keys prevent repeated HTTP requests from creating duplicate runs. A bot
can have one active run, and an account can have three. Completed steps are skipped
on retry/recovery. Transient read/AI errors receive one automatic retry; a step may
have at most three attempts across recovery and manual retries. Failed runs retain
their original deadline and spending limits. Saved prospects survive a later draft
failure and can be inspected from the Save step or partial results.

## Security and result checks

The existing Clerk JWT verification derives ownership; callers cannot choose a
workspace. All private Studio endpoints enforce it, including historical runs and
archived bots. Server-owned credentials are never serialized in Studio records or
returned to clients. Redaction covers credential fields, recognizable key/token
patterns, and rejected input values in validation errors. Do not place secrets in
free-text content; pattern redaction is not a general secret-detection guarantee.

Provider errors expose a safe code, status and recovery instruction. Logs contain run
and skill identifiers, timestamps and safe messages. Unexpected errors log exception
types and stack locations, not provider bodies, credentials or raw input payloads.

The network surface is deliberately narrow: Brave's fixed HTTPS endpoint and the
administrator-configured AI endpoint. API redirects are disabled. User-provided URLs
are not requested by the backend. External source text is kept as data in bounded
prompts; models receive no executable tools. An unregistered external write effect
fails closed with `approval_required`. Adding a sending integration requires a real
approval and execution/reconciliation mechanism first; no such integration exists in V1.

**Source checked** means the company name and quote match a search result, not that
all business facts are independently verified. V1 does not crawl websites or verify
email addresses, current employment, deliverability, or legal company identity.
Public search snippets may be stale or incomplete. Fit scores and natural-language
criteria involve AI judgment and need human review. The measured success flag checks
minimum count, score/evidence validation, deduplication, persistence and draft coverage
when the Draft skill is selected;
it does not certify semantic satisfaction of every free-text instruction.

## Verification

```bash
make check
cd frontend
npx playwright install chromium
npm run test:studio
```

The browser suite starts an isolated API and background runtime against a temporary
SQLite database, uses locally signed test JWTs through the real authentication
verifier, and replaces only the test entrypoint and provider responses. No real Clerk
users are created. Production source contains no mock providers or authentication
bypass. It checks create → execute → saved prospects/drafts → logs → reload → edit →
account isolation → mobile → delete → retained history. Backend tests also check
failed steps, retries, restart safety, budgets, URL restrictions and provider contracts.

Set `STUDIO_SCREENSHOT_DIR` to a temporary directory when running `test:studio` to
retain screenshots for review. Install the browser once; browser tests are separate
from the fast offline `make check` command.

## V2 candidates

- Per-account provider connections using an encrypted credential store.
- More precise source verification and purpose-specific lead-data providers.
- Per-account daily quotas, model rate configuration, retention/export policies.
- Reviewed templates that reuse the same registered skills.
- Approval records plus connector idempotency/reconciliation before any external write.
- Scheduling or webhooks only after trigger ownership and quotas are designed.
- Distributed queue/leases only when sequential single-host execution becomes limiting.
