# Google Drive connections through MCP

Open **Connections** in the Axelyn sidebar or visit `/#/studio/connections`.
This integration uses Pipedream Connect for account authorization and its hosted
MCP server for Drive tools. Axelyn's existing worker executes the registered skill;
no new queue, workflow engine, or service is required.

## Administrator setup

1. Create a [Pipedream Connect project](https://pipedream.com/docs/connect/mcp/developers).
2. Create a **client secret** API client in Pipedream's API settings. Record its
   client ID, client secret and project ID. These are Pipedream credentials, separate
   from the Google OAuth client used for Clerk sign-in.
3. Configure these server variables for **both the API and worker**:

   ```text
   PIPEDREAM_CLIENT_ID=<your Pipedream client ID>
   PIPEDREAM_CLIENT_SECRET=<your Pipedream client secret>
   PIPEDREAM_PROJECT_ID=proj_<your project ID>
   PIPEDREAM_ENVIRONMENT=development
   ```

   `development` is the default. For production, configure Pipedream Connect's
   production environment and use `production` consistently on both services.
   Review Pipedream's current production plan requirements. Accounts are separated
   by environment, project and API client; changing these does not transfer accounts.
   Never put client secrets in `VITE_*` variables, source control, bot instructions
   or chat. This integration does not require a Clerk secret or a new Clerk app.

4. For the narrowest Google authorization, configure a custom Google Drive OAuth
   client in Pipedream with `https://www.googleapis.com/auth/drive.readonly`, and set
   `PIPEDREAM_DRIVE_OAUTH_APP_ID=oa_<your OAuth app ID>` on both services. Register
   the callback URI Pipedream provides in Google Cloud, not an invented Axelyn
   callback. Complete the Google consent, test-user and verification steps appropriate
   to that client's deployment. See [Pipedream OAuth clients](https://pipedream.com/docs/connect/managed-auth/oauth-clients).
   This setting is optional when using Pipedream's official Google Drive OAuth
   client; its consent may request broader scopes. Axelyn still exposes only the
   three approved read operations below. Application restrictions do not narrow an
   OAuth token's actual Google permissions.
5. Install the locked backend dependencies and restart the API and worker. In a
   native development setup:

   ```bash
   backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
   ```

   For Compose, rebuild/recreate those two services with the deployment's existing
   Compose files and environment overlays. A plain container restart does not
   pick up changed environment values. Preserve the shared harness database volume.

The Connections page displays setup instructions when configuration is absent.
It never shows server credentials. The UI's readiness indicator checks configuration
presence; **Refresh accounts** exercises provider authentication.

## Connect and use Drive

1. Choose **Connect Google Drive**. Complete authorization in the new tab.
   A fallback link appears if the browser blocks popups; it expires in ten minutes.
2. Return to Axelyn and choose **Refresh accounts**. The backend fetches accounts
   from the provider for the verified Clerk user's workspace. Browser-supplied account
   IDs or OAuth callback parameters are never accepted as proof of ownership.
3. Choose **Browse files**, search by file name, and preview a document. Search
   returns at most 20 files. Other formats can be opened in Google Drive.
4. Create or edit a Lead Research Bot. Under **Background documents**, select the
   connected account and up to two files. This grants the `google_drive` tool and
   adds the registered **Drive context** skill before Research → Analyze → Save →
   optional Draft. Save and execute manually.
5. Review the Drive step's input/output, source document links and background text
   alongside the normal execution results. Reopening the app retains accounts,
   file selections, execution history, prospects and drafts.

Drive is optional. Bots without selected Drive files continue to use the original
sequence. Brave Search remains required for Lead Research's public prospect sources.
Drive documents provide background on your offering, not verification of prospect facts.

## Access and storage

- Clerk continues to verify the caller. A server-derived workspace ID maps to a
  Pipedream `external_user_id`; clients cannot choose either identity.
- Only account ID, a redacted display name, status, timestamps and provider namespace
  are stored in the existing SQLite database. Google access/refresh tokens remain
  with Pipedream. Pipedream access tokens are obtained server-side and not persisted.
- The short-lived connection link is returned only to its authenticated caller and
  kept in component memory. Its Connect token has account/app scopes, no tool execution
  or API proxy scope. It is not stored in bot configurations or activity records.
- Each bot grants one account and explicit file IDs. Live checks enforce local
  disconnects, disabled bots and removed file selections before subsequent work.
  Every MCP session also verifies current provider account ownership and health.
- **Disconnect** disables Axelyn access immediately, then attempts provider account
  removal. If removal fails, the UI reports that access is disabled locally and
  offers retry. **Refresh accounts never re-enables a disconnected account.**
  **Reconnect** explicitly restores local permission only after the provider confirms
  an existing healthy account; otherwise, complete fresh Google authorization first.
  Provider account removal does not guarantee revocation of the entire Google OAuth
  app grant. That grant can be reviewed separately in Google Account permissions.
- Disconnecting does not erase previously saved execution snapshots or text. Selected
  document text is sent to the configured AI provider and saved in execution history;
  the bot form discloses this before saving. Preview text is not persisted separately.
- Activity records include operation/status/time, not file content, search terms,
  provider bodies or credentials. The last 200 events per account are retained and
  connection requests are limited to 30 per minute per account.

## MCP boundary

The official Python MCP SDK connects over Streamable HTTP to the fixed endpoint
`https://remote.mcp.pipedream.net/v3`. Pipedream's control API is also fixed to
`https://api.pipedream.com/v1`. User-supplied MCP servers, command execution, custom
headers and arbitrary URLs are not supported. Redirects and environment proxies are
disabled; source links and returned download URLs are never fetched by Axelyn.

Tool discovery is filtered to these reviewed actions (hyphen/underscore variants
map to the same approved action):

| Action | Purpose |
| --- | --- |
| `google_drive-search-files` | Bounded file-name search |
| `google_drive-get-file` | Selected file metadata |
| `google_drive-download-file` | Return the selected file's text as an in-memory buffer |

Arguments are generated by deterministic code and validated against each discovered
input schema. Unexpected schemas fail with `connection_schema_changed`; there is no
fallback to arbitrary tool calls. Remote JSON Schema references are forbidden.
No discovered tool description is added to an LLM's available tools. No MCP sampling,
file-system roots or interactive tool requests are enabled.

Only Google Docs and UTF-8 plain text, Markdown and CSV files are read. File IDs and
MIME types are validated; shortcuts and binary/oversized content are rejected.
The download action requests a buffer and `text/plain`, never a provider file path.
Control responses are capped at 512 KB, MCP responses/events at 1 MB, and decoded
text at 128 KB. Previews show up to 8,000 characters; bots receive up to 2,000 per
selected file. Truncation is explicit.

Connection operations have a 30-second overall deadline; provider deletion has a
15-second deadline. MCP metadata/content calls each count against a run's existing
API-call budget. Authentication, negotiation and tool discovery are transport
overhead bounded by the same deadline/response caps, not separate charged skill calls.
There are no automatic retries of connection operations; a manual run retry preserves
the existing deadline, step attempts and spending. No external write tools or sending
capabilities are registered.

External document text is bounded, redacted for recognizable credential patterns,
and explicitly treated as untrusted data in AI instructions. It cannot alter skill
order, select tools or change permissions. Redaction is not a universal detector of
confidential information; select documents appropriate for the configured AI provider.

## Verify

```bash
make check
npm --prefix frontend run test:studio
```

Backend tests cover ownership, permissions, revocation during reads, persistence,
limits, provider HTTP contracts, unsupported content, malformed schemas, timeouts and
a real SDK client/server exchange through Streamable HTTP. The browser suite runs the
authenticated API and worker against temporary SQLite storage, replaces only external
providers, and checks connection → search → preview → select → run → reload → disconnect
and desktop/mobile layouts. No real Google or Clerk account is created by tests.

A live Google consent and Drive read still require an administrator's real Pipedream
configuration and the user's authorization. Provider doubles are confined to test files;
production never fabricates Drive files or successful connections.
