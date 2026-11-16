# Security and reporting

Pre-release software: do not entrust real family archives to this foundation.

Report vulnerabilities privately to the repository maintainer through GitHub private vulnerability reporting once hosting is configured. Do not attach real family data or secrets to public issues.

## Boundaries

- Opaque random sessions, hash-only token storage, expiration and revocation; Argon2 password hashes.
- Same-origin mutation checks plus session-bound CSRF tokens; secure cookies by default.
- No administrator override in the family member endpoint. Runtime credentials do not own the schema.
- Memory routes enforce owner-only writes, private/family visibility, current-revision ACL checks and PostgreSQL RLS. Historical revisions remain private to their owner. Local Ollama retrieval is permission-filtered. No remote AI transmission or shell tools are enabled.
- File uploads are bounded, original downloads are authenticated, and binary content is not passed to the model. Immich MCP supports explicit read-only operations restricted to the configuring family administrator; member access and LLM tool execution remain disabled.
- Logging excludes bodies, passwords and session tokens. Audit records contain actor ID, action and time.
- Non-root app containers, read-only root filesystems, dropped capabilities, no host socket, private database port.

Host administrators can read unencrypted application files, database contents, process memory and backups. Application privacy is not protection against host-level control. Family administrator status is not an entitlement to another user's future private memories. Succession must not become an inactivity-triggered disclosure mechanism.

## Threat model and pending controls

| Threat | Present control / remaining work |
| --- | --- |
| Compromised account | Session revocation and account login throttling; MFA/OIDC and UI revocation pending |
| Cross-family requests | Identity-derived family ID and RLS for memories, chat, files and Immich settings. MCP results are restricted to the configuring administrator; graph and member delegation remain pending. |
| Malicious documents | Bounded text/binary/ZIP imports; no PDF extraction or active embedded documents. Format signatures are not antivirus scanning. |
| Prompt injection | Local chat treats archive text as untrusted; no model-driven tool execution. MCP descriptions are not interpreted as policy or prompts. |
| Compromised MCP | Fixed read-tool allowlist, runtime discovery, bounded responses, validated/pinned endpoints, no redirects and no fetching returned URLs. A compromised MCP server still controls its own upstream actions; trust that server and limit its Immich key. |
| Remote leakage | Ollama remains local-only. Explicit administrator MCP connections transmit only protocol messages, narrow read arguments and the optional proxy token; no CLAIRE memories or chat history are sent. |
| Host compromise | Out of application boundary; host encryption and access control required |
| Ransomware | Offline/immutable encrypted backup and restore exercises pending |
| Backup compromise | No backup feature yet; keys must remain external to ordinary exports |

Account limiter alone does not mitigate distributed random-address floods. Reverse proxy rate limiting is required. Initial login-row creation still needs concurrency stress coverage. Dependency scanning is configured in CI; passing it does not replace a security review.

Immich proxy tokens are authenticated-encrypted in PostgreSQL using a persistent filesystem key. Neither normal configuration responses nor validation errors include the token. Ordinary archive exports exclude the key; host-level backups must protect it together with the database. `barryw/ImmichMCP` uses its container's upstream Immich key for every request, so a shared MCP endpoint is not per-family-member authorization. See [Immich setup and limits](docs/immich.md).
