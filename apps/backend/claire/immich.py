"""Admin-only saved Immich connection and explicit read-only operations."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .chat import context
from .db import Audit, ImmichConnection
from .identity import authenticate
from .immich_mcp import READ_TOOLS, ImmichMCP, MCPError, endpoint_url
from .secrets import decrypt, encrypt


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(max_length=1000)
    enabled: bool = False
    token: str | None = Field(default=None, max_length=4096)
    expected_revision: int = Field(ge=0)
    confirmed: bool = False

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value):
        return endpoint_url(value.strip())

    @field_validator("token")
    @classmethod
    def valid_token(cls, value):
        if value and any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError("Token must contain visible ASCII characters only")
        return value


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["test", "recent", "albums", "search"]
    query: str = Field(default="", max_length=200)


def immich_router(engine, settings, client_factory=ImmichMCP):
    router = APIRouter(prefix="/api/v1/integrations/immich", tags=["integrations"])

    def admin(request, db):
        user, _ = authenticate(request, db)
        if user.role != "family_admin":
            raise HTTPException(403, "Only family administrators can configure or use this integration")
        context(db, user.id, user.family_id)
        return user

    def find(db, user, lock=False):
        query = select(ImmichConnection).where(
            ImmichConnection.owner_id == user.id, ImmichConnection.family_id == user.family_id
        )
        return db.scalar(query.with_for_update() if lock else query)

    def public(row):
        return {
            "endpoint": row.endpoint if row else "",
            "enabled": row.enabled if row else False,
            "has_token": bool(row and row.token_cipher),
            "revision": row.revision if row else 0,
            "transport": "streamable-http",
            "access": "configuring_admin_only",
        }

    @router.get("")
    def get(request: Request):
        with Session(engine) as db:
            user = admin(request, db)
            return public(find(db, user))

    @router.put("")
    def save(body: ConnectionInput, request: Request):
        with Session(engine) as db:
            user = admin(request, db)
            if not body.confirmed:
                raise HTTPException(422, "Confirm the MCP server and its library access before saving")
            row = find(db, user, True)
            if body.expected_revision != (row.revision if row else 0):
                raise HTTPException(409, "Configuration changed; reload before saving")
            if row and row.endpoint != body.endpoint and row.token_cipher and body.token is None:
                raise HTTPException(422, "Changing server requires replacing or removing the saved token")
            if row is None:
                row = ImmichConnection(owner_id=user.id, family_id=user.family_id, revision=0)
            row.endpoint, row.enabled = body.endpoint, body.enabled
            if body.token is not None:
                row.token_cipher = encrypt(settings, body.token) if body.token else None
            row.revision += 1
            db.add(row)
            db.add(Audit(actor_id=user.id, action="immich.configured"))
            try:
                db.commit()
            except IntegrityError:
                raise HTTPException(409, "Configuration changed; reload before saving") from None
            context(db, user.id, user.family_id)
            return public(row)

    @router.delete("", status_code=204)
    def remove(request: Request):
        with Session(engine) as db:
            user = admin(request, db)
            row = find(db, user, True)
            if row:
                db.delete(row)
                db.add(Audit(actor_id=user.id, action="immich.disconnected"))
                db.commit()

    @router.post("/read")
    def read(body: ReadInput, request: Request):
        with Session(engine) as db:
            user = admin(request, db)
            row = find(db, user)
            if row is None:
                raise HTTPException(409, "Save an Immich MCP connection first")
            if not row.enabled and body.action != "test":
                raise HTTPException(409, "Immich integration is disabled")
            endpoint, token, revision = row.endpoint, decrypt(settings, row.token_cipher), row.revision
            owner, family = user.id, user.family_id
        try:
            with client_factory(endpoint, token) as client:
                if body.action == "test":
                    result = client.call("immich_ping", {})
                    if not isinstance(result, dict) or result.get("connected") is not True:
                        raise MCPError("MCP responded, but did not confirm a working Immich connection")
                    output = {
                        "connected": True,
                        "server": client.server,
                        "tools": sorted(READ_TOOLS.intersection(client.tools)),
                    }
                else:
                    tool, arguments = {
                        "recent": ("immich_assets_list", {"size": 25}),
                        "albums": ("immich_albums_list", {}),
                        "search": ("immich_search_metadata", {"originalFileName": body.query, "size": 25}),
                    }[body.action]
                    raw = client.call(tool, arguments)
                    if not isinstance(raw, list):
                        raise MCPError("This Immich server returned an unsupported list format")
                    # No raw upstream URLs, embedded images, headers or tool instructions reach the UI.
                    items = []
                    for item in raw[:50]:
                        if not isinstance(item, dict):
                            continue

                        def field(*names, item=item):
                            return next(
                                (
                                    str(item[name])[:300]
                                    for name in names
                                    if isinstance(item.get(name), (str, int))
                                ),
                                "",
                            )

                        items.append(
                            {
                                "id": field("id"),
                                "title": field(
                                    "original_file_name",
                                    "originalFileName",
                                    "album_name",
                                    "albumName",
                                    "name",
                                ),
                                "type": field("type"),
                                "date": field("file_created_at", "fileCreatedAt", "created_at", "createdAt"),
                            }
                        )
                    output = {"items": items, "limited": len(raw) > 50}
        except MCPError as error:
            raise HTTPException(502, str(error)) from None
        except (ValueError, TypeError, AttributeError, KeyError):
            # Do not reflect credentials, upstream bodies or returned tool descriptions.
            raise HTTPException(
                502,
                "Immich MCP connection failed or is incompatible. Check /mcp, proxy token, transport and server logs.",
            ) from None
        # Recheck session, role and configuration after network I/O; disconnect/revocation fail closed.
        with Session(engine) as db:
            user = admin(request, db)
            current = find(db, user)
            if (
                user.id != owner
                or user.family_id != family
                or current is None
                or current.revision != revision
            ):
                raise HTTPException(409, "Configuration changed while reading; retry")
            db.add(Audit(actor_id=user.id, action=f"immich.{body.action}"))
            db.commit()
        return output

    return router
