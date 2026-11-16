"""All-in-one lifecycle. Root coordinates; PostgreSQL and CLAIRE run separately unprivileged."""

import argparse
import fcntl
import json
import os
import pwd
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

DATA = Path("/data")
PGDATA = DATA / "postgres"
STATE = Path("/run/claire")
SOCKET = Path("/run/postgresql")
PG_BIN = Path("/usr/libexec/postgresql18")
ADMIN_URL = "postgresql+psycopg://postgres@/claire?host=/run/postgresql"


def identity(name):
    account = pwd.getpwnam(name)
    return {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": [], "umask": 0o077}


def directory(path, name, mode):
    if path.is_symlink():
        raise RuntimeError(f"Refusing symbolic link: {path}")
    path.mkdir(parents=True, exist_ok=True)
    account = pwd.getpwnam(name)
    os.chown(path, account.pw_uid, account.pw_gid)
    path.chmod(mode)


def environment(admin=False):
    env = dict(os.environ)
    env.pop("CLAIRE_DATABASE_URL", None)
    env.pop("CLAIRE_DATABASE_URL_FILE", None)
    env["CLAIRE_DATA_DIR"] = str(DATA / "archive")
    if admin:
        env["CLAIRE_DATABASE_URL"] = ADMIN_URL
    else:
        env["CLAIRE_DATABASE_URL_FILE"] = str(STATE / "database_url")
    return env


def sql(query, database="postgres"):
    # Passwords are sent on stdin, never on the command line or in logs.
    result = subprocess.run(
        [
            str(PG_BIN / "psql"),
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-h",
            str(SOCKET),
            "-U",
            "postgres",
            "-d",
            database,
        ],
        input=query,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        **identity("postgres"),
    )
    if result.returncode:
        raise RuntimeError("Database provisioning failed; no application started")
    return result.stdout.strip()


def secret():
    directory(DATA / "secrets", "root", 0o700)
    path = DATA / "secrets" / "runtime-password"
    if path.is_symlink():
        raise RuntimeError("Refusing linked credential file")
    if not path.exists():
        with path.open("x") as output:
            output.write(secrets.token_hex(32))
            output.flush()
            os.fsync(output.fileno())
    path.chmod(0o600)
    value = path.read_text().strip()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("Invalid runtime credential file; restore it from backup")
    return value


def provision():
    if sql("SELECT 1 FROM pg_database WHERE datname='claire';") != "1":
        sql("CREATE DATABASE claire;")
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env=environment(admin=True),
        timeout=120,
        check=True,
        **identity("postgres"),
    )
    password = secret()
    sql(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='claire_runtime') THEN "
        "CREATE ROLE claire_runtime LOGIN; END IF; END $$;"
    )
    sql(
        "ALTER ROLE claire_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
        f"NOBYPASSRLS PASSWORD '{password}';"
    )
    grants = "\n".join(
        line
        for line in Path("/app/runtime-role.sql").read_text().splitlines()
        if not line.startswith("CREATE ROLE ")
    )
    sql(grants, "claire")
    path = STATE / "database_url"
    path.write_text(f"postgresql+psycopg://claire_runtime:{password}@127.0.0.1:5432/claire")
    os.chown(path, 0, pwd.getpwnam("claire").pw_gid)
    path.chmod(0o440)


def health():
    state = json.loads((STATE / "services.json").read_text())
    for pid in state.values():
        os.kill(pid, 0)
    with urlopen("http://127.0.0.1:8000/readyz", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("Web not ready")


def serve():
    if os.getuid() != 0:
        raise RuntimeError("AIO coordinator must start as root; services drop privileges automatically")
    if os.environ.get("CLAIRE_ORIGIN", "https://localhost") == "https://localhost":
        raise RuntimeError("Set CLAIRE_ORIGIN to your exact browser URL before starting")
    os.umask(0o077)
    directory(DATA, "root", 0o755)
    lock = (DATA / ".aio.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another AIO container is using this data directory") from None
    directory(STATE, "root", 0o755)
    directory(SOCKET, "postgres", 0o755)
    directory(DATA / "archive", "claire", 0o700)
    ready = STATE / "services.json"
    ready.unlink(missing_ok=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    processes = {}
    try:
        if PGDATA.is_symlink():
            raise RuntimeError("Refusing linked database directory")
        if not (PGDATA / "PG_VERSION").exists():
            if PGDATA.exists() and any(PGDATA.iterdir()):
                raise RuntimeError("Incomplete/non-AIO database directory; preserve it and investigate")
            directory(PGDATA, "postgres", 0o700)
            subprocess.run(
                [
                    str(PG_BIN / "initdb"),
                    "-D",
                    str(PGDATA),
                    "-U",
                    "postgres",
                    "--auth-local=peer",
                    "--auth-host=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C",
                ],
                timeout=120,
                check=True,
                **identity("postgres"),
            )
        if (PGDATA / "PG_VERSION").read_text().strip() != "18":
            raise RuntimeError("AIO requires PostgreSQL 18 data; major-version migration must be explicit")
        if PGDATA.is_symlink():
            raise RuntimeError("Refusing linked database directory")
        # Override inherited cluster settings: the database never listens outside this container.
        hba = STATE / "pg_hba.conf"
        hba.write_text(
            "local all postgres peer\nlocal all all reject\n"
            "host claire claire_runtime 127.0.0.1/32 scram-sha-256\n"
            "host all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
        )
        hba.chmod(0o644)
        processes["postgres"] = subprocess.Popen(
            [
                str(PG_BIN / "postgres"),
                "-D",
                str(PGDATA),
                "-c",
                "listen_addresses=127.0.0.1",
                "-c",
                f"unix_socket_directories={SOCKET}",
                "-c",
                f"hba_file={hba}",
                "-c",
                "password_encryption=scram-sha-256",
            ],
            **identity("postgres"),
        )
        for _ in range(120):
            if stopping or processes["postgres"].poll() is not None:
                raise RuntimeError("Database stopped during startup")
            check = subprocess.run(
                [str(PG_BIN / "pg_isready"), "-h", str(SOCKET), "-U", "postgres"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
                **identity("postgres"),
            )
            if check.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Database readiness timed out")
        provision()
        if stopping:
            return
        processes["worker"] = subprocess.Popen(
            [sys.executable, "-m", "claire.worker"], env=environment(), **identity("claire")
        )
        processes["web"] = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "claire.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            ],
            env=environment(),
            **identity("claire"),
        )
        ready.write_text(json.dumps({name: process.pid for name, process in processes.items()}))
        ready.chmod(0o644)
        print("CLAIRE AIO started: web + private PostgreSQL + worker", flush=True)
        while not stopping:
            for name, process in processes.items():
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited unexpectedly; stopping the whole container")
            time.sleep(0.5)
    finally:
        ready.unlink(missing_ok=True)
        # Stop writers before the database. SIGINT requests PostgreSQL's clean fast shutdown.
        for name in ("web", "worker", "postgres"):
            process = processes.get(name)
            if process and process.poll() is None:
                process.send_signal(signal.SIGINT if name == "postgres" else signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description="CLAIRE all-in-one lifecycle")
    parser.add_argument("command", choices=["serve", "health", "create-user"], nargs="?", default="serve")
    args, rest = parser.parse_known_args()
    try:
        if args.command == "health":
            health()
        elif args.command == "create-user":
            if os.getuid() != 0:
                raise RuntimeError("Account provisioning is an operator-only command")
            health()
            raise SystemExit(
                subprocess.call(
                    [sys.executable, "-m", "claire.cli", *rest],
                    env=environment(admin=True),
                    **identity("postgres"),
                )
            )
        else:
            serve()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"CLAIRE AIO: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
