# Installation: Docker Compose, Ubuntu/Debian, and Unraid

This foundation is for evaluation with synthetic data. Production acceptance is pending.

## Host preparation

Install Docker Engine and Compose v2 from Docker's supported packages on Ubuntu/Debian, or use Unraid's Docker service and Compose management. No Docker socket is mounted in CLAIRE. CPU-only identity operation needs approximately 2 cores and 4 GB RAM. AI capacity is model-dependent and not yet integrated.

Copy `.env.example` to `.env`. On Unraid set paths under `/mnt/user/appdata/claire`: `archive`, `postgres`, `models`, `secrets`. Keep PostgreSQL on a suitable local filesystem/cache pool and use consistent backups; parity is not backup. App UID/GID defaults to 10001:10001; changing PUID/PGID changes the container identity, not ownership of existing files. Create archive directories and assign them to that numeric identity. PostgreSQL manages its own volume ownership; do not recursively chown it to the app user.

## Secrets and database roles

Create the secret directory with mode 0700. Generate separate random owner and runtime passwords; store files with mode 0600 (or a narrowly scoped group readable by the container UID). Required mounted files:

- `db_password`: PostgreSQL owner's raw password.
- `owner_database_url`: `postgresql+psycopg://claire_owner:URL_ENCODED_PASSWORD@claire-db/claire`.
- `database_url`: `postgresql+psycopg://claire_runtime:URL_ENCODED_PASSWORD@claire-db/claire`.

Do not commit these files. URI-encode passwords in URLs. Set `CLAIRE_ORIGIN` to the exact HTTPS browser origin. A reverse proxy or VPN should protect access; ports bind only to loopback, and PostgreSQL has no published port.

```sh
docker compose build
docker compose up -d claire-db
docker compose run --rm migrate
docker compose exec -T claire-db psql -U claire_owner -d claire < infrastructure/docker/runtime-role.sql
docker compose exec claire-db psql -U claire_owner -d claire
```

In psql run `\password claire_runtime`, enter the runtime password from your secret file, then `\q`. Account provisioning needs owner credentials, unlike normal web operation:

```sh
docker compose run --rm --entrypoint python migrate -m claire.cli owner@example.test --family-name 'Example family' --role family_admin
docker compose up -d claire-app claire-worker
```

Subsequent users should specify `--family-id` from the first command. Runtime privileges cannot create users or change schema. A future account-management UI must preserve this separation with a narrow provisioning service.

For local HTTP evaluation only use both files:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Open `http://localhost:8000` exactly. Secure cookies intentionally do not work over ordinary HTTP in the production configuration. Set a reverse proxy request-body limit of 16 KiB and a per-client authentication rate limit; account-level limits are also enforced by the backend. Configure TLS and forwarding headers explicitly rather than trusting arbitrary client-supplied proxy headers.

## Optional services

`--profile local-ai` starts a pinned Ollama service without GPU requirements. The foundation does not call it yet. Voice and backup profiles will be introduced with implemented services, not empty containers. GPU passthrough/NVIDIA Unraid instructions will accompany validated AI support; do not add privileged mode.

## Upgrade

Back up the database and files together before upgrades. Stop writes, run owner-only Alembic migrations, then start web/worker roles. Never run destructive downgrade against real data without a verified restore. The initial downgrade intentionally drops identity tables and is only exercised on disposable test databases. Reassess image pins and run scans before deployment.
