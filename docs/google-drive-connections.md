# Google Drive connections

Users open **Connections**, click **Connect** beside Google Drive, and authorize
with Google. Axelyn detects completion automatically. Google credentials stay on
the server. App sign-in continues to use Clerk; Drive authorization is separate.

## One-time owner setup

1. In Google Cloud, enable the **Google Drive API** for your project.
2. Configure the OAuth consent screen: app branding, audience, support information,
   and test users while the application is in Testing.
3. Create an OAuth client with application type **Web application**. Use a dedicated
   client for Drive; do not change Clerk's Google sign-in configuration.
4. Register this exact authorized redirect URI for production:

   ```text
   https://sentral.axelyn.com/api/connections/google-drive/callback
   ```

5. Set these server variables for **both the API and worker**, using your deployment's
   private configuration. Do not commit credentials or put secrets in `VITE_*` variables.

   ```text
   GOOGLE_DRIVE_CLIENT_ID=<Google OAuth client ID>
   GOOGLE_DRIVE_CLIENT_SECRET=<Google OAuth client secret>
   GOOGLE_DRIVE_REDIRECT_URI=https://sentral.axelyn.com/api/connections/google-drive/callback
   ```

6. Recreate the API and worker with the updated configuration, preserving their
   shared persistent volume. Connect a Google account from the app to verify consent.

Local Vite development can use
`http://localhost:5173/api/connections/google-drive/callback`, with the existing API
proxy. Register that exact URI in Google too. Keep the browser and callback on the
same hostname so the browser-binding cookie is available. HTTP callbacks are accepted
only for `localhost` and `127.0.0.1`; deployed callbacks require HTTPS.

The requested scope is `https://www.googleapis.com/auth/drive.readonly`. It permits
browsing existing files without writes and is a **restricted Google scope**. Configure
it in the consent screen. Public distribution can require Google verification and
additional review. Testing-mode grants can expire and require reconnection. Follow
[Google's web-server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server)
and [Drive scope requirements](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
This implementation's bot permissions further restrict reads to explicitly selected
files; the underlying Google grant covers the user's readable Drive files.

## Connect and use files

1. Open **Bot Studio → Connections → Connect**.
2. Choose a Google account and approve read-only Drive access. The popup closes and
   Axelyn shows **Connected** automatically. If popups are blocked, use the displayed
   Google authorization link. An unfinished attempt can resume after a page reload
   in the same tab for up to ten minutes, or be cancelled.
3. Browse file names and preview a supported document.
4. In a bot's form, select that account and up to **two documents** as background context.
5. Run the bot manually. The saved execution includes the selected source links and
   bounded excerpts. External content is untrusted evidence, not instructions.

Drive context is optional. Lead Research still needs the configured web-search and
AI providers to discover and evaluate public prospects. The app never sends outreach.

## Credentials and account isolation

- Clerk authenticates both authorization start and final completion. The Google
  callback alone cannot attach an account. The current user must own the attempt.
- Authlib implements the authorization-code exchange with S256 PKCE. Random state
  and an HttpOnly, SameSite=Lax browser cookie bind each single-use callback to its
  initiating browser. Attempts expire after ten minutes; production cookies are Secure.
- State and browser nonces are hashed. PKCE verifiers and pending grants are encrypted.
  Finalization is transactional and idempotent. Replaying an old completion never
  reactivates an account disconnected later.
- Access and refresh tokens are encrypted with Fernet and bound to the account,
  connection and configured Google client. They never appear in API responses or logs.
- By default the server atomically creates a private `google-drive.key` beside the
  SQLite database, in the shared `var` volume. **Back up the database and this key
  together.** Missing or incorrect keys fail closed. An administrator can instead
  supply `GOOGLE_DRIVE_TOKEN_ENCRYPTION_KEY`, a valid Fernet key, identically on both
  services before connecting accounts. Changing keys requires a planned migration;
  automatic key rotation is not implemented.
- Expiring access tokens refresh on the server. Credential revisions and ownership
  checks prevent an in-flight refresh from restoring a disconnected account. Revoked
  grants show **Reconnect required**. Reauthorizing the same Google account preserves
  its connection ID and existing bot selections.
- Disconnect disables local access and removes stored credentials first, then asks
  Google to revoke the grant. If Google cannot confirm revocation, the UI directs
  users to Google Account permissions. Google revocation may affect other grants
  for the same Google client and account. Existing execution records remain saved.
- OAuth callback query strings are excluded from API and Nginx access logs. Any
  additional edge proxy must also avoid logging callback query parameters. Callback
  pages have no external resources and use no-store and no-referrer headers, plus
  a page-level no-referrer policy for proxies that override response headers.

## MCP and runtime limits

Axelyn uses the official MCP SDK in-process to expose three approved tools over the
stable Drive API: `google_drive_search_files`, `google_drive_get_file`, and
`google_drive_read_file`. No additional MCP service or hosted integration provider is
needed. Registered deterministic code chooses tools; the model cannot discover
unrestricted tools, execute code, or provide arbitrary server URLs.

Tool schemas and responses are validated. Remote schema references are rejected.
Outbound requests use fixed Google endpoints, with redirects and environment proxies
disabled. Only Google Docs exported as text, UTF-8 plain text, Markdown and CSV are
supported. PDF, binary files, folders and shortcuts are not readable in V1.

- Search returns at most 20 matching names in the user's corpus. Shared-drive browsing
  and pagination are not implemented.
- Reads are capped at 128 KB; JSON responses at 512 KB. Previews expose at most 8,000
  characters, and bot context at most 2,000 characters per selected file.
- Operations have a 30-second deadline; disconnect revocation has a 15-second deadline.
  There are no automatic connection retries.
- Each MCP tool invocation counts toward the bot's API-call budget. OAuth exchange
  and refresh are separately bounded transport operations.
- Connection operations are limited to 30 per minute per account, authorization starts
  to ten per ten minutes, and activity history to the most recent 200 records.

## Verification

`make check` covers OAuth validation, encrypted persistence, user isolation, callback
replay and browser binding, expiry, refresh and disconnect races, MCP permissions,
response limits, safe errors, and bot execution with Drive context.
`npm --prefix frontend run test:studio` exercises the Connect popup through the real
callback, automatic completion, file selection and a persisted worker execution.
Only external Google, search and AI responses are simulated in these tests. A live
Google consent and read require the owner's configured OAuth client and Google account.
