FROM node:22.14.0-bookworm-slim AS frontend
WORKDIR /src
COPY apps/frontend/package*.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS wheels
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY apps/backend/claire ./apps/backend/claire
RUN pip install --no-cache-dir uv==0.9.5 && uv export --quiet --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt && pip wheel --wheel-dir /wheels -r requirements.txt && pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels && groupadd -g 10001 claire && useradd -u 10001 -g claire -M claire
COPY apps/backend/migrations ./apps/backend/migrations
COPY alembic.ini ./
COPY --from=frontend /src/dist ./static
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "claire.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
