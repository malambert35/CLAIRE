# CLAIRE

**Continuous Learning AI for Remembrance and Evolution**

A family-owned knowledge preservation platform with a replaceable AI layer.

An initial offline archive library also preserves UUID provenance, immutable Markdown/JSON revisions, contradictory testimony, recoverable tombstones and checksummed single-memory exports. It is not exposed through the API yet; resource authorization and database reconciliation must precede that step.

**Status: 0.1.0 foundation under development, not production-ready.** Authentication, family membership listing, migrations, health endpoints and a bilingual responsive interface are implemented. Memories, chat, retrieval, integrations, backup and succession are not yet available. No fake AI or persistence responses are provided.

Read the [architecture and six-phase checklist](docs/architecture.md), [installation guide](docs/install.md), [security model](SECURITY.md), and [recovery plan](docs/recovery.md).

## Quick development start

Requires Python 3.12+, uv, Node 22+, and Docker Compose v2 for PostgreSQL.

```sh
uv sync --frozen
cd apps/frontend
npm ci
npm run build
cd ../..
uv run pytest
uv run ruff check apps/backend tests
```

For a disposable local smoke test only, SQLite can run the identity foundation:

```sh
export CLAIRE_DATABASE_URL=sqlite:///./data/dev.db
export CLAIRE_ORIGIN=http://localhost:8000
export CLAIRE_SECURE_COOKIES=false
export CLAIRE_STATIC_DIR=apps/frontend/dist
mkdir -p data
uv run alembic upgrade head
uv run python -m claire.cli you@example.test --family-name 'Example family' --role family_admin
uv run uvicorn claire.main:create_app --factory --host 127.0.0.1
```

Open http://localhost:8000. SQLite is a test convenience, not the production database. Account passwords are entered interactively, never embedded in scripts. Add another family member with `--family-id UUID`; omission creates a separate household.

## API

OpenAPI JSON: `/openapi.json`. FastAPI documentation: `/docs` (the strict CSP currently blocks CDN Swagger assets; use the JSON specification with a local client).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Process health |
| GET | `/readyz` | Database and migration readiness |
| POST | `/api/v1/auth/login` | Opaque secure session |
| GET | `/api/v1/auth/me` | Current identity and CSRF token |
| POST | `/api/v1/auth/logout` | Revoke session |
| GET | `/api/v1/family/members` | Current household only |
| GET | `/api/v1/capabilities` | Implemented feature flags |

Mutations require an exact configured Origin; authenticated mutations also require `X-CSRF-Token`. Session cookies are HttpOnly, Secure, SameSite=Strict by default. There is no public registration or default account.

## License and dependencies

Apache-2.0. Dependency versions are locked in `uv.lock` and `apps/frontend/package-lock.json`. See [third-party notices](docs/third-party.md). Deployment images are version-pinned; digest verification and vulnerability scans are release gates, not an assertion that old pins remain safe indefinitely.
