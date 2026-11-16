"""Docker integration check using a unique disposable volume; no real account/data."""

import argparse
import http.cookiejar
import json
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


def docker(*args, input=None, check=True):
    result = subprocess.run(
        ["docker", *args],
        input=input.encode() if input is not None else None,
        capture_output=True,
        check=False,
        timeout=180,
    )
    if check and result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout.decode(errors="replace").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="claire:aio-test")
    parser.add_argument("--port", default="8013")
    args = parser.parse_args()
    name = "claire-aio-test-" + uuid4().hex[:10]
    volume = name + "-data"
    origin = f"http://127.0.0.1:{args.port}"

    def launch(container=name, publish=True):
        options = [
            "run",
            "-d",
            "--name",
            container,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "--tmpfs",
            "/run:rw,noexec,nosuid,size=32m",
            "--mount",
            f"type=volume,src={volume},dst=/data",
            "-e",
            f"CLAIRE_ORIGIN={origin}",
            "-e",
            "CLAIRE_SECURE_COOKIES=false",
        ]
        for capability in ("CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID", "KILL"):
            options += ["--cap-add", capability]
        if publish:
            options += ["-p", f"127.0.0.1:{args.port}:8000"]
        docker(*options, args.image)

    def wait_ready():
        for _ in range(180):
            if docker("inspect", name, "--format", "{{.State.Running}}") != "true":
                raise RuntimeError(docker("logs", name))
            try:
                with build_opener().open(origin + "/readyz", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(0.5)
        raise RuntimeError("AIO did not become ready")

    def client(email):
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        headers = {"Origin": origin, "Content-Type": "application/json"}

        def request(path, body=None, extra=None, raw=False):
            data = body if isinstance(body, bytes) else None if body is None else json.dumps(body).encode()
            with opener.open(
                Request(origin + path, data=data, headers={**headers, **(extra or {})}), timeout=10
            ) as response:
                payload = response.read()
                return payload if raw else json.loads(payload)

        result = request("/api/v1/auth/login", {"email": email, "password": "synthetic-aio-password"})
        headers["X-CSRF-Token"] = result["csrf_token"]
        return request

    try:
        # Reject a previous major version without attempting initdb or migrations.
        docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "--mount",
            f"type=volume,src={volume},dst=/data",
            args.image,
            "-c",
            "from pathlib import Path; p=Path('/data/postgres'); p.mkdir(); "
            "(p/'PG_VERSION').write_text('17\\n')",
        )
        launch()
        assert docker("wait", name) == "1"
        docker("rm", name)
        docker("volume", "rm", volume)
        launch()
        wait_ready()
        for email in ("alice@example.test", "outsider@example.test"):
            docker(
                "exec",
                "-i",
                name,
                "python",
                "-m",
                "claire.aio",
                "create-user",
                email,
                "--family-name",
                "Synthetic family",
                "--role",
                "family_admin",
                input="synthetic-aio-password\nsynthetic-aio-password\n",
            )
        request = client("alice@example.test")
        saved = request(
            "/api/v1/memories",
            {"title": "Persistent AIO memory", "content": "Original text.", "confirmed": True},
        )
        path = f"/api/v1/memories/{saved['id']}"
        pdf = b"%PDF-1.7\n% synthetic original\n%%EOF"
        asset = request(
            "/api/v1/assets",
            pdf,
            {
                "Content-Type": "application/octet-stream",
                "X-File-Metadata": quote(
                    json.dumps({"filename": "letter.pdf", "title": "Persistent PDF", "confirmed": True})
                ),
            },
        )
        asset_path = f"/api/v1/assets/{asset['id']}/content"
        assert request(asset_path, raw=True) == pdf
        try:
            client("outsider@example.test")(asset_path, raw=True)
            raise AssertionError("Other family could read private original")
        except HTTPError as error:
            assert error.code == 404
        try:
            client("outsider@example.test")(path)
            raise AssertionError("Other family could read private memory")
        except HTTPError as error:
            assert error.code == 404
        flags = docker(
            "exec",
            "-u",
            "postgres",
            name,
            "/usr/libexec/postgresql18/psql",
            "-h",
            "/run/postgresql",
            "-d",
            "claire",
            "-Atc",
            "SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname='claire_runtime'",
        )
        assert flags == "f|f|f"
        docker(
            "exec",
            "-u",
            "10001:10001",
            name,
            "python",
            "-c",
            "import os; assert not os.access('/data/secrets/runtime-password',os.R_OK); "
            "assert not os.access('/data/postgres/PG_VERSION',os.R_OK)",
        )
        docker(
            "exec",
            name,
            "python",
            "-c",
            "import json; from pathlib import Path; "
            "p=json.loads(Path('/run/claire/services.json').read_text()); "
            "assert all('Uid:\\t10001\\t10001' in Path('/proc/'+str(p[n])+'/status').read_text() "
            "for n in ['web','worker'])",
        )
        assert (
            docker(
                "exec",
                "-u",
                "postgres",
                name,
                "/usr/libexec/postgresql18/psql",
                "-h",
                "/run/postgresql",
                "-d",
                "claire",
                "-Atc",
                "SELECT count(*) FROM pg_extension WHERE extname='vector'",
            )
            == "1"
        )
        # A second coordinator cannot use the same files concurrently.
        launch(name + "-duplicate", publish=False)
        assert docker("wait", name + "-duplicate") == "1"
        assert request(path)["content"] == "Original text."
        assert request(asset_path, raw=True) == pdf
        docker("stop", "--time", "120", name)
        assert docker("inspect", name, "--format", "{{.State.ExitCode}}") == "0"
        docker("rm", name)
        launch()
        wait_ready()
        assert client("alice@example.test")(path)["content"] == "Original text."
        # An unclean container interruption must still preserve committed data.
        docker("kill", name)
        docker("start", name)
        wait_ready()
        assert client("alice@example.test")(path)["content"] == "Original text."
        # Losing any long-lived process must take down the entire container.
        docker(
            "exec",
            name,
            "python",
            "-c",
            "import json,os,signal; from pathlib import Path; "
            "os.kill(json.loads(Path('/run/claire/services.json').read_text())['worker'],signal.SIGKILL)",
        )
        assert docker("wait", name) == "1"
        docker("start", name)
        wait_ready()
        assert client("alice@example.test")(path)["content"] == "Original text."
        print(
            "AIO initialization, private access, restricted role, pgvector, restart, crash recovery and fail-fast: OK"
        )
    finally:
        docker("rm", "-f", name + "-duplicate", check=False)
        docker("stop", "--time", "120", name, check=False)
        docker("rm", "-f", name, check=False)
        docker("volume", "rm", volume, check=False)


if __name__ == "__main__":
    main()
