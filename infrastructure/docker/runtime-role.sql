-- Run as claire_owner after migrations. Supply the role password interactively
-- using psql \password claire_runtime; never store it in this file.
CREATE ROLE claire_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE claire TO claire_runtime;
GRANT USAGE ON SCHEMA public TO claire_runtime;
GRANT SELECT ON families, users, alembic_version TO claire_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions, login_attempts TO claire_runtime;
GRANT INSERT ON audit TO claire_runtime;
GRANT SELECT, INSERT, UPDATE ON memories TO claire_runtime;
