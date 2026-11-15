# Validation record

## Portable memory export

24 backend tests pass with SQLite (two opt-in PostgreSQL/live-model tests skipped). Export tests cover owner-only access, another family's denial, original private revisions, deleted history, Unicode preservation, tampering and unexpected file paths. Two Playwright Chromium workflows pass, including a real ZIP download and French mobile export control. The downloaded two-revision ZIP passes `python -m claire.portable`; mobile screenshot inspected at 390px with no horizontal overflow. Production frontend build and Ruff pass. Browser plugin unavailable; existing Playwright workflow used. PostgreSQL rerun was unavailable because Docker Desktop's Linux engine was stopped. Full restore/import is not claimed.

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

The memory update enables New memory and adds editor, story, history, trash and restore states within the same palette/typography. Account/logout controls are present; theme is a toggle rather than a dropdown. Main heading, empty-state text and privacy copy match. Mobile navigation scrolls horizontally within its own region. No screenshot is used as live UI. Screenshots are generated reproducibly by the e2e test into ignored data/ paths.

## Memory workflow update

17 backend tests pass with PostgreSQL, including non-bypass RLS checks, cross-family denial, private/family sharing and revocation, owner-only editing/history, confirmation/CSRF, stale revisions, durable reload, tombstones/restoration, catalogue reconciliation after an interrupted write and preservation of existing accounts during upgrade. Two Chromium workflows pass: identity/localization/theme and create → reload → edit → original revision → delete → restore, including French mobile layout. A textarea accessibility label found during browser testing was corrected. The frontend production build passes.

## Still unverified

Full Compose installation with least-privilege runtime credentials, arm64 images, external reverse proxy, Unraid host, and clean-host backup restoration. RAG, MCP and voice operation remain unimplemented. Power-loss/filesystem stress tests, automatic archive-write recovery, complete family export/import and independent backup verification remain open. The date-sorted view accepts ISO year, month or day precision; it is not a knowledge graph.

## Hosted CI

GitHub backend/frontend tests and dependency audits pass. The container build passes, but Trivy blocks release on OS package findings. Refreshing the Python base from Debian 12 to digest-pinned Debian 13 reduced the report from 143 high/critical findings (9 critical) to 49 high findings (0 critical). Runtime OS updates are now applied during build to consume available fixes. Remaining findings require triage; the blocking scan is not weakened and no production image is published. SBOM generation/upload runs even when the scan fails. See the repository Actions page for the current report.

## Local chat update

23 backend tests pass against disposable PostgreSQL, including private chat RLS, cross-owner access denial, generation overlap, provider failures and cloud-alias rejection. Real Ollama 0.40.3 with qwen3:8b passed browser inference, persisted reload and cancellation checks. Desktop and mobile screenshots were inspected; no horizontal overflow or page errors were observed. Chat has no archive context. Full Compose/GPU inference remains unverified.
