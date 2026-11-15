# Validation record

2026-11-15, Windows development host, Python 3.12, Chromium via Playwright.

- Backend identity and archive tests: 11 passing with SQLite, then 11 passing with PostgreSQL.
- PostgreSQL 17 / pgvector 0.8.0 migration upgrade, downgrade and upgrade: passing on a disposable Docker database.
- TypeScript and Vite production build: passing.
- npm dependency audit: zero reported vulnerabilities at install time.
- Multi-stage Docker image build: passing on linux/amd64. A hash-checking failure for the local package was fixed by building its wheel separately from hashed third-party requirements.
- Container runtime smoke: UID 10001, read-only root, capabilities dropped; health and readiness both return success against disposable PostgreSQL.
- Browser: real FastAPI backend and synthetic account; login → family members → French → dark mode → mobile → logout passes. No page errors. Browser plugin unavailable; used installed Playwright Chromium. Desktop 1440×1000 and mobile 390×844, no horizontal page overflow.

## Visual comparison

Compared `docs/design-concept.png` against browser screenshots with view_image. Inspected white/green palette, serif headings, sans-serif controls, sidebar order/icons, whitespace, footer and responsive layout. The concept's app region is one part of a combined app/login board, so screenshots use practical separate viewports rather than the board's full native dimensions.

Intentional deviations: New memory is omitted until persistence is authorized through the API; an availability notice is added; account/logout controls are present; theme is a toggle rather than a dropdown. Main heading, empty-state text and privacy copy match. Mobile navigation scrolls horizontally within its own region. No screenshot is used as live UI. Screenshots are generated reproducibly by the e2e test into ignored data/ paths.

## Still unverified

Full Compose installation with least-privilege runtime credentials, arm64 images, external reverse proxy, Unraid host, CI hosted execution, image vulnerability scan/SBOM, and clean-host backup restoration. No LLM, RAG, MCP or voice operation is claimed. The archive library still needs database/file recovery reconciliation, resource permissions, concurrent/crash tests, complete family export/import, and independent backup verification before integration.
