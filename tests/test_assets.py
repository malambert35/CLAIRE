import io
import json
from urllib.parse import quote
from zipfile import ZipFile

from claire.archive import checksum
from claire.assets import ASSET_LIMIT
from test_memories import household  # noqa: F401

PNG = bytes.fromhex("89504e470d0a1a0a") + b"synthetic image payload"


def upload(client, data=PNG, filename="photo.png", **changes):
    meta = {"filename": filename, "title": "Garden", "description": "Family flowers", "confirmed": True}
    meta.update(changes)
    return client.post(
        "/api/v1/assets",
        content=data,
        headers={"x-file-metadata": quote(json.dumps(meta)), "content-type": "application/octet-stream"},
    )


def test_files_private_share_revoke_delete_export_and_integrity(household):  # noqa: F811
    clients, settings = household
    alice, bob, outsider = (clients[n] for n in ("alice", "bob", "outsider"))
    response = upload(alice)
    assert response.status_code == 201, response.text
    item = response.json()
    path = "/api/v1/assets/" + item["id"]
    assert item["visibility"] == "private"
    assert item["sha256"] == checksum(PNG)
    assert alice.get(path + "/content").content == PNG
    partial = alice.get(path + "/content", headers={"Range": "bytes=2-5"})
    assert partial.status_code == 206 and partial.content == PNG[2:6]
    assert alice.get(path + "/content", headers={"Range": "bytes=9999-"}).status_code == 416
    for client in (bob, outsider):
        assert client.get("/api/v1/assets").json() == []
        assert client.get(path + "/content").status_code == 404
        assert client.get(path + "/export").status_code == 404
    assert alice.get("/api/v1/assets?q=flowers").json()[0]["id"] == item["id"]
    assert alice.patch(path, json={"expected_revision": 1, "visibility": "family"}).status_code == 422
    shared = alice.patch(path, json={"expected_revision": 1, "visibility": "family", "confirmed": True})
    assert shared.status_code == 200
    assert bob.get(path + "/content").content == PNG
    assert outsider.get(path + "/content").status_code == 404
    assert (
        bob.patch(path, json={"expected_revision": 2, "deleted": True, "confirmed": True}).status_code == 403
    )
    assert (
        alice.patch(path, json={"expected_revision": 1, "deleted": True, "confirmed": True}).status_code
        == 409
    )
    assert (
        alice.patch(
            path, json={"expected_revision": 2, "visibility": "private", "confirmed": True}
        ).status_code
        == 200
    )
    assert bob.get(path + "/content").status_code == 404
    assert (
        alice.patch(path, json={"expected_revision": 3, "deleted": True, "confirmed": True}).status_code
        == 200
    )
    assert alice.get("/api/v1/assets").json() == []
    assert len(alice.get("/api/v1/assets?deleted=true").json()) == 1
    assert (
        alice.patch(path, json={"expected_revision": 4, "deleted": False, "confirmed": True}).status_code
        == 200
    )
    with ZipFile(io.BytesIO(alice.get(path + "/export").content)) as package:
        assert package.read("original/photo.png") == PNG
        assert json.loads(package.read("metadata.json"))["revision"] == 5
    original = next((settings.data_dir / "files").rglob("original"))
    original.write_bytes(b"corrupt")
    assert alice.get(path + "/content").status_code == 503


def test_file_validation_and_pdf_download(household):  # noqa: F811
    clients, _ = household
    alice = clients["alice"]
    assert upload(clients["reader"]).status_code == 403
    assert upload(alice, confirmed=False).status_code == 422
    for filename, content in [
        ("bad.svg", b"<svg/>"),
        ("fake.png", b"<html>"),
        ("../photo.png", PNG),
        ("empty.png", b""),
    ]:
        assert upload(alice, content, filename).status_code == 422
    assert upload(alice, b"x" * (ASSET_LIMIT + 1)).status_code == 413
    pdf = b"%PDF-1.7\n% synthetic original\n%%EOF"
    response = upload(alice, pdf, "lettre.pdf")
    assert response.status_code == 201
    path = "/api/v1/assets/" + response.json()["id"] + "/content"
    result = alice.get(path)
    assert result.content == pdf
    assert result.headers["content-disposition"].startswith("attachment;")
    assert result.headers["x-content-type-options"] == "nosniff"
    assert alice.get("/api/v1/assets").json() == []
    assert len(alice.get("/api/v1/assets?kind=document").json()) == 1
