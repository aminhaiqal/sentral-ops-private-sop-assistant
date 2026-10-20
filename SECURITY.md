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

- There is no user authentication, role-based authorization, rate limiting, or audit log.
- Workspace cookies act as bearer credentials. They scope stored documents and vector
  queries but do not identify a person or establish company tenancy.
- Model prompts and keyword rules cannot guarantee protection from prompt injection,
  data disclosure, fabricated citations, or incorrect operational advice.
- Text is sent to the configured AI provider for embeddings and answer generation.
  Upload originals, extracted text, and metadata are stored in R2.
- Browser history can retain answer text and snippets after a source document is deleted.
  Losing a workspace cookie does not remove stored uploads. Retention is operator-managed.
- Public question and upload routes can consume provider credits and storage. The
  HTTPS proxy blocks shared-corpus ingestion, but it does not restrict these other routes.

Before handling real internal documents, add authenticated access, enforced authorization,
request and spending limits, retention and deletion procedures, audit logging, and
monitoring. Review the data-processing terms of your AI and storage providers.

## Secrets and deployment

Keep `.env`, credentials, keys, real documents, and backups out of Git. The ignore rules
and CI secret scanner are safeguards, not proof that a file is safe to publish. If a
credential is exposed, revoke it at the provider; deleting it from a later commit is
insufficient.

Local Compose publishes services only on loopback. The HTTPS example keeps FastAPI and
Qdrant off host ports, uses secure workspace cookies, and stores certificates in volumes.
Keep R2 private and scope its credentials to the required bucket. See
[deployment](docs/deployment.md) for configuration and persistence details.
