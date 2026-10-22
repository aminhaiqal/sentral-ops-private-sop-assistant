# Architecture

Axelyn has one flow: source documents → a task → a saved Markdown result.

## Application

- `frontend/src/App.tsx`: request input, history, polling, and document management.
- `frontend/src/components/TaskResult.tsx`: progress, results, downloads, sources, and activity.
- `frontend/src/AuthRoot.tsx`: Clerk sign-in and fresh bearer tokens for API requests.
- `backend/app/main.py`: health checks and private document endpoints.
- `backend/app/harness/`: task API, SQLite persistence, tools, and background worker.

## Execution

`POST /api/tasks` accepts a goal with optional completion criteria and context, and
returns a queued task. The worker claims it and lets the configured model select one
registered tool per turn: `search_documents`, `write_artifact`, `read_artifact`,
`complete_task`, or `request_input`.

Each turn and tool result is checkpointed. Saved pending calls and receipts allow a
restarted worker to recover without regenerating already committed work. Cancellation
wins over an in-flight response. A process lock allows one worker per local database.
Transient provider failures receive bounded retries; limits bound turns, reported
model tokens, active execution time, and context size. Resuming retains those limits.
These controls do not establish a hard provider spending cap.

Completion requires a saved artifact, a read-back matching its current content hash,
and citation labels that refer to retrieved sources. These checks validate storage
and label references, not factual support or semantic task completion.

## Documents and isolation

Clerk JWT verification binds each private request to an account-owned workspace.
The same account has the same scope across sessions. Browser-provided workspace IDs
and legacy cookies cannot override it. Team/organization permissions are not included.

Uploads accept UTF-8 Markdown and text-based PDFs, up to 10 MiB, 100 PDF pages, and
200,000 extracted characters. PDF extraction runs in a bounded subprocess. Linux
also applies a memory limit. Scanned PDFs and encrypted PDFs are unsupported.

R2 saves originals, extracted text, and metadata before indexing. A failed embedding
request leaves the upload available for retry. Content hashes deduplicate uploads
within an account. Qdrant searches require an exact workspace match; legacy shared
sample vectors are excluded. Deletion removes vectors before stored source objects.

Tasks, sources, transcripts, and artifacts persist in SQLite. Deleting a source file
does not remove prior task excerpts or results. No browser chat cache is used.
Existing task records remain readable when they contain retired bot metadata; that
metadata is ignored. Existing obsolete database tables are left untouched.
