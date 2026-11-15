# Contributing

Use synthetic data only. Run `uv run pytest`, `uv run ruff check apps/backend tests`, and frontend `npm ci && npm run build`. Database migration tests may use `CLAIRE_TEST_DATABASE_URL` pointing only at a disposable database: they downgrade/drop test tables.

Keep archive schemas versioned and preserve UUIDs/provenance. Do not introduce remote data flows or tools without centralized authorization and explicit consent. Add negative cross-family tests before exposing any resource. Unimplemented integrations must report unavailable, never success.

Use small commits and document migration/recovery consequences. A release requires Docker integration and clean-host restoration in addition to unit tests. Read docs/architecture.md for the full roadmap.
