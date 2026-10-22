# Security

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/aminhaiqal/sentral-ops-private-sop-assistant/security/advisories/new).
Use fictional reproduction data and redact credentials. Security fixes target `main`;
there is no guaranteed response time.

## Boundaries

- Private endpoints require a verified Clerk session bearer token. Signatures, issuer,
  time claims, user/session identity, and authorized frontend origins are checked.
  Missing configuration fails closed. Legacy workspace cookies grant no access.
- Workspaces belong to individual accounts. Team permissions, global rate limiting,
  a security audit log, and automated retention are not implemented.
- Source text is sent to the configured AI provider for embeddings and task execution.
  R2 stores originals, extracted text, and metadata. SQLite stores task transcripts,
  retrieved excerpts, activity, and results without application-level encryption.
- Deleting a source does not erase its excerpts from earlier tasks or backups.
  Signing out does not delete server-side work. Retention is operator-managed.
- Task and upload requests can consume provider credits and storage. Worker execution
  limits do not guarantee a hard spending cap.
- Prompts and citation-label checks do not guarantee factual accuracy, complete
  evidence support, or protection from prompt injection.

Review access, retention, provider data-processing terms, and operational controls
before handling sensitive documents.

## Deployment

Keep `.env`, credentials, real documents, and backups out of Git. Revoke any exposed
credential at its provider. CI secret scanning is a safeguard, not proof of safety.
Local Compose exposes services only on loopback. The HTTPS example keeps FastAPI and
Qdrant off host ports. Keep the R2 bucket private and its credentials scoped.
See [Deployment](docs/deployment.md) for persistence and backups.
