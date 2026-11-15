# Security and reporting

Pre-release software: do not entrust real family archives to this foundation.

Report vulnerabilities privately to the repository maintainer through GitHub private vulnerability reporting once hosting is configured. Do not attach real family data or secrets to public issues.

## Boundaries

- Opaque random sessions, hash-only token storage, expiration and revocation; Argon2 password hashes.
- Same-origin mutation checks plus session-bound CSRF tokens; secure cookies by default.
- No administrator override in the family member endpoint. Runtime credentials do not own the schema.
- No remote AI transmission, MCP execution, shell tools, uploads or memory routes are enabled.
- Logging excludes bodies, passwords and session tokens. Audit records contain actor ID, action and time.
- Non-root app containers, read-only root filesystems, dropped capabilities, no host socket, private database port.

Host administrators can read unencrypted application files, database contents, process memory and backups. Application privacy is not protection against host-level control. Family administrator status is not an entitlement to another user's future private memories. Succession must not become an inactivity-triggered disclosure mechanism.

## Threat model and pending controls

| Threat | Present control / remaining work |
| --- | --- |
| Compromised account | Session revocation and account login throttling; MFA/OIDC and UI revocation pending |
| Cross-family requests | Family ID derived from authenticated identity; resource RLS and private-memory tests pending |
| Malicious documents | Uploads disabled; sandboxed extraction, size/zip limits and quarantine required before enablement |
| Prompt injection | No tool/model execution; future untrusted content cannot alter policy or grant permissions |
| Compromised MCP | Disabled; per-user credentials, transport validation and read-only allowlists required |
| Remote leakage | No provider calls; centralized consent receipts and minimization required |
| Host compromise | Out of application boundary; host encryption and access control required |
| Ransomware | Offline/immutable encrypted backup and restore exercises pending |
| Backup compromise | No backup feature yet; keys must remain external to ordinary exports |

Account limiter alone does not mitigate distributed random-address floods. Reverse proxy rate limiting is required. Initial login-row creation still needs concurrency stress coverage. Dependency scanning is configured in CI; passing it does not replace a security review.
