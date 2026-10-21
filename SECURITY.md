# Security

## Reporting a vulnerability

Please use [GitHub's private vulnerability reporting](https://github.com/aminhaiqal/sentral-ops-private-sop-assistant/security/advisories/new).
Include the affected version or commit, reproduction steps, and impact. Use fictional
data and redact credentials. If private reporting is unavailable, use the contact links
on the [maintainer's profile](https://github.com/aminhaiqal) to arrange a private report.
Do not post credentials, private documents, or exploit details in a public issue.

Security fixes currently target the latest `main` branch. There is no supported release
series or guaranteed response time.

## Current boundaries

This is an educational application with fictional fixtures, not a complete private
document platform. In particular:

- Private endpoints require a verified Clerk session bearer token. Signature, issuer,
  time claims, user/session identity, and authorized frontend origin are checked.
  Missing configuration fails closed; browser workspace cookies cannot authorize access.
- Workspaces belong to individual Clerk accounts. Team/organization permissions,
  rate limiting, and a security audit log are not implemented.
- Model prompts and keyword rules cannot guarantee protection from prompt injection,
  data disclosure, fabricated citations, or incorrect operational advice.
- Text is sent to the configured AI provider for embeddings and answer generation.
  Upload originals, extracted text, and metadata are stored in R2.
- Browser history can retain answer text and snippets after a source document is deleted.
  Signing out does not delete stored uploads or local chat caches. Retention is operator-managed.
- Authenticated question and upload routes can consume provider credits and storage. The
  HTTPS proxy blocks shared-corpus ingestion, but it does not restrict these other routes.
- Task submission can also consume provider credits asynchronously. Task transcripts,
  retrieved excerpts, and artifacts persist in the local SQLite database. Task events
  describe execution; they are not a security audit log. Workspace isolation and
  retention limitations apply to tasks as well as uploads.
- Bot profiles, owner preferences, and artifact-check outcome memories share that
  SQLite database, scoped by workspace and bot. The database is not encrypted by this
  application. Deleting a memory prevents future retrieval but does not erase prior
  task transcripts, model outputs, artifacts, or backups. Retrieved memory is sent to
  the configured model provider when the bot works on a task.

Before handling real internal documents, review the account access policy and add team
authorization where needed, request and spending limits, retention and deletion procedures, audit logging, and
monitoring. Review the data-processing terms of your AI and storage providers.

## Secrets and deployment

Keep `.env`, credentials, keys, real documents, and backups out of Git. The ignore rules
and CI secret scanner are safeguards, not proof that a file is safe to publish. If a
credential is exposed, revoke it at the provider; deleting it from a later commit is
insufficient.

Local Compose publishes services only on loopback. The HTTPS example keeps FastAPI and
Qdrant off host ports, binds token authorization to the frontend origin, and stores certificates in volumes.
Keep R2 private and scope its credentials to the required bucket. See
[deployment](docs/deployment.md) for configuration and persistence details.
