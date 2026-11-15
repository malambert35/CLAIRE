"""Exercise the installed runtime as non-root, with only /tmp writable."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psycopg
from claire.identity import passwords

assert os.getuid() == 10001 and os.getgid() == 10001
assert psycopg.pq.version() > 0
assert passwords.verify("synthetic-runtime-check", passwords.hash("synthetic-runtime-check"))

with tempfile.TemporaryDirectory() as directory:
    env = {**os.environ, "CLAIRE_DATABASE_URL": f"sqlite:///{directory}/smoke.db",
           "CLAIRE_DATA_DIR": directory, "CLAIRE_STATIC_DIR": "/app/static"}
    env.pop("CLAIRE_DATABASE_URL_FILE", None)
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "claire.main:create_app", "--factory",
                               "--host", "127.0.0.1", "--port", "8000"], env=env)
    try:
        for attempt in range(50):
            try:
                with urlopen("http://127.0.0.1:8000/readyz", timeout=1) as response:
                    assert response.status == 200
                break
            except URLError:
                if server.poll() is not None:
                    raise RuntimeError("Server exited before readiness") from None
                time.sleep(0.2)
        else:
            raise RuntimeError("Server did not become ready")
        with urlopen("http://127.0.0.1:8000/", timeout=2) as response:
            assert b'<div id="root">' in response.read()
    finally:
        server.terminate()
        server.wait(timeout=10)
    log = Path(directory) / "worker.log"
    with log.open("w") as output:
        worker = subprocess.Popen([sys.executable, "-m", "claire.worker"], env=env,
                                  stdout=output, stderr=output)
        try:
            for attempt in range(50):
                if "worker heartbeat" in log.read_text():
                    break
                if worker.poll() is not None:
                    raise RuntimeError("Worker exited before heartbeat")
                time.sleep(0.2)
            else:
                raise RuntimeError("Worker did not connect to the database")
        finally:
            worker.terminate()
            worker.wait(timeout=10)
        assert worker.returncode == 0
print("Non-root runtime, SQLite migrations, Argon2, psycopg, web readiness, static UI and worker: OK")
