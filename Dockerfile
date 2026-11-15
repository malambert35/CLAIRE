FROM node:22.14.0-bookworm-slim AS frontend
WORKDIR /src
COPY apps/frontend/package*.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS wheels
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY apps/backend/claire ./apps/backend/claire
RUN pip install --no-cache-dir uv==0.9.5 && uv export --quiet --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt && pip wheel --wheel-dir /wheels -r requirements.txt && pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CLAIRE_DATA_DIR=/data
WORKDIR /app
RUN apk upgrade --no-cache
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels && addgroup -g 10001 claire && adduser -D -H -u 10001 -G claire claire
COPY apps/backend/migrations ./apps/backend/migrations
COPY alembic.ini ./
COPY --from=frontend /src/dist ./static
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "claire.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
