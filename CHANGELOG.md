# Changelog

## 0.1.0 — unreleased

- Replace the Debian runtime with digest-pinned Python 3.12 Alpine 3.24 and matching musl wheels; apply available OS fixes without suppressing Trivy findings. Add installed-runtime CI checks under non-root/read-only restrictions.

- Portable ZIP import with verified preview and checksum-bound confirmation, preserved history/provenance and a new private copy without overwriting existing memories.

- Owner-only portable ZIP download of complete memory revision history, including deleted memories; offline checksum and revision-chain verification without extraction.

- Chat now retrieves current authorized memory excerpts by keyword, without an indexing delay; local inference verified against a newly saved synthetic memory.

- Real local Ollama streaming chat, installed-model selection, private persisted history and cancellation.
- Owner-only conversation/message RLS, bounded context and explicit failure states; real-provider browser checks.

- Functional memory editor, Markdown display, title search, event-date view, private/family sharing, owner-only history, recoverable deletion and restoration.
- PostgreSQL row-level memory policies, negative authorization tests and interrupted-write catalogue recovery.
- Windows local startup script preserving existing accounts; browser workflow tests included in CI.

- Initial identity and household foundation, versioned API, migrations and worker lifecycle.
- Responsive English/French React interface with light/dark themes and truthful feature availability.
- Non-root Compose deployment, separate owner/runtime database credentials, CI checks.
- Preservation architecture and explicit remaining production acceptance gates.
