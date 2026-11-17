"""Compatibility check against the real barryw image and a synthetic Immich API."""

import argparse
import subprocess
from uuid import uuid4

MCP_IMAGE = "ghcr.io/barryw/immichmcp@sha256:45acbcd7fb7ab766e1edad00cb5d3a2b849f1f6ecbadeb14771d1413bb241187"
MOCK = """
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, value):
        payload = json.dumps(value).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        assert self.headers.get('x-api-key') == 'synthetic-key'
        if self.path == '/api/server/about': self.send({'version': '2.5.0'})
        elif self.path == '/api/albums': self.send([{'id':'11111111-1111-4111-8111-111111111111','albumName':'Synthetic album','createdAt':'2026-01-01T00:00:00Z','updatedAt':'2026-01-01T00:00:00Z','assetCount':1}])
        elif self.path.startswith('/api/people?'): self.send({'people':[{'id':'22222222-2222-4222-8222-222222222222','name':'Synthetic Person','isHidden':False}], 'total':1, 'hidden':0, 'hasNextPage':False})
        else: self.send_error(404)
    def do_POST(self):
        assert self.headers.get('x-api-key') == 'synthetic-key'
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        if body.get('personIds'): assert body['personIds'] == ['22222222-2222-4222-8222-222222222222']
        if self.path == '/api/search/metadata': self.send({'assets':{'items':[{'id':'11111111-1111-4111-8111-111111111111','type':'IMAGE','originalFileName':'synthetic.jpg','fileCreatedAt':'2026-01-01T00:00:00Z','localDateTime':'2026-01-01T00:00:00Z'}],'total':1,'count':1,'nextPage':None}})
        else: self.send_error(405)
HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
"""
CHECK = """
import time
from claire.immich_mcp import ImmichMCP, MCPError
for attempt in range(3):
    try:
        with ImmichMCP('http://mcp:5000/mcp') as client:
            assert client.call('immich_ping', {})['connected']
            assert client.call('immich_assets_list', {'size':25})[0]['originalFileName']=='synthetic.jpg'
            assert client.call('immich_albums_list', {})[0]['albumName']=='Synthetic album'
            assert client.call('immich_search_metadata', {'originalFileName':'synthetic','size':25})[0]['originalFileName']=='synthetic.jpg'
            assert client.call('immich_people_list', {'withHidden':False,'page':1,'size':100})['people'][0]['name']=='Synthetic Person'
            assert client.call('immich_people_assets', {'personId':'22222222-2222-4222-8222-222222222222','page':1,'size':25})[0]['originalFileName']=='synthetic.jpg'
            try: client.call('immich_assets_delete', {'ids':[]})
            except MCPError: pass
            else: raise AssertionError('Write tool allowed')
        print('Real ImmichMCP compatibility: initialization, discovery, ping, assets, albums, search, read-only policy OK')
        break
    except MCPError as error:
        print(str(error), flush=True)
        if attempt == 2: raise
        time.sleep(1)
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="claire:immich-test")
    args = parser.parse_args()
    name = "claire-immich-test-" + uuid4().hex[:10]

    def docker(*command, check=True):
        result = subprocess.run(["docker", *command], capture_output=True, text=True, timeout=180, check=False)
        if check and result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return (result.stdout + result.stderr).strip()

    docker("network", "create", name)
    try:
        docker(
            "run",
            "-d",
            "--name",
            name + "-api",
            "--network",
            name,
            "--network-alias",
            "synthetic-immich",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--entrypoint",
            "python",
            args.image,
            "-c",
            MOCK,
        )
        for mode in ("static", "gateway"):
            docker(
                "run",
                "-d",
                "--name",
                name + "-mcp",
                "--network",
                name,
                "--network-alias",
                "mcp",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,nosuid,size=64m",
                "--cap-drop",
                "ALL",
                "-e",
                "IMMICH_BASE_URL=http://synthetic-immich:8080",
                "-e",
                "IMMICH_API_KEY=synthetic-key",
                "-e",
                "IMMICH_TOOL_MODE=" + mode,
                MCP_IMAGE,
            )
            try:
                print(
                    mode
                    + ": "
                    + docker(
                        "run",
                        "--rm",
                        "--network",
                        name,
                        "--read-only",
                        "--cap-drop",
                        "ALL",
                        "--entrypoint",
                        "python",
                        args.image,
                        "-c",
                        CHECK,
                    )
                )
            except Exception:
                print(docker("logs", name + "-api", check=False), flush=True)
                print(docker("logs", name + "-mcp", check=False), flush=True)
                raise
            finally:
                docker("rm", "-f", name + "-mcp", check=False)
    finally:
        docker("rm", "-f", name + "-api", check=False)
        docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
