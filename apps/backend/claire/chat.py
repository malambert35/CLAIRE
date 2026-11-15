"""Private chat with bounded local inference and persisted completion status."""

import asyncio
import json
from datetime import timedelta
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .db import Audit, Conversation, Message, now
from .identity import authenticate
from .providers import Ollama, ProviderUnavailable

SYSTEM_PROMPT = (
    "You are CLAIRE, a local family assistant. Reply in the user's language. "
    "This conversation contains only messages, not retrieved family archives. "
    "Distinguish general knowledge from unverified user testimony. Do not invent family facts or citations. "
    "You have no tools and cannot save or edit memories, send messages, or execute actions. "
    "Never claim a memory was saved. Direct users to the Family Memories editor to preserve a memory."
)


class NewConversation(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    model: str = Field(min_length=1, max_length=200)


def context(db, owner_id, family_id):
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text(
                "SELECT set_config('claire.user_id', :owner, true), "
                "set_config('claire.family_id', :family, true)"
            ),
            {"owner": owner_id, "family": family_id},
        )


def serialize(message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "model": message.model,
        "created_at": message.created_at.isoformat(),
    }


def event(kind, payload):
    return f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def chat_router(engine, settings, provider=None):
    router = APIRouter(prefix="/api/v1", tags=["chat"])
    provider = provider or Ollama(settings)

    def identity(request, db):
        user, _ = authenticate(request, db)
        context(db, user.id, user.family_id)
        return user

    def owned(db, user, conversation_id):
        row = db.scalar(
            select(Conversation).where(
                Conversation.id == str(conversation_id),
                Conversation.owner_id == user.id,
                Conversation.family_id == user.family_id,
            )
        )
        if not row:
            raise HTTPException(404, "Conversation not found")
        return row

    @router.get("/ai/models")
    def models(request: Request):
        with Session(engine) as db:
            authenticate(request, db)
        try:
            names = provider.models()
            return {
                "provider": "ollama",
                "local": True,
                "models": names,
                "default_model": settings.llm_model if settings.llm_model in names else next(iter(names), ""),
                "archive_context": False,
            }
        except ProviderUnavailable as error:
            raise HTTPException(503, str(error)) from None

    @router.get("/conversations")
    def conversations(request: Request, offset: int = Query(default=0, ge=0)):
        with Session(engine) as db:
            user = identity(request, db)
            rows = db.scalars(
                select(Conversation)
                .where(Conversation.owner_id == user.id, Conversation.family_id == user.family_id)
                .order_by(Conversation.created_at.desc(), Conversation.id)
                .offset(offset)
                .limit(50)
            ).all()
            return [
                {"id": row.id, "title": row.title, "created_at": row.created_at.isoformat()} for row in rows
            ]

    @router.post("/conversations", status_code=201)
    def create(body: NewConversation, request: Request):
        with Session(engine) as db:
            user = identity(request, db)
            if user.role not in {"family_admin", "member"}:
                raise HTTPException(403, "This account cannot create conversations")
            row = Conversation(owner_id=user.id, family_id=user.family_id, title=body.title)
            db.add(row)
            db.flush()
            output = {"id": row.id, "title": row.title}
            db.commit()
            return output

    @router.get("/conversations/{conversation_id}")
    def history(conversation_id: UUID, request: Request, before: int = Query(default=0, ge=0)):
        with Session(engine) as db:
            user = identity(request, db)
            row = owned(db, user, conversation_id)
            messages = db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == row.id,
                    Message.owner_id == user.id,
                    Message.family_id == user.family_id,
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .offset(before)
                .limit(100)
            ).all()
            return {
                "id": row.id,
                "title": row.title,
                "messages": [serialize(msg) for msg in reversed(messages)],
                "has_older": len(messages) == 100,
            }

    def finish(owner_id, family_id, conversation_id, run_id, model, content, status):
        with Session(engine) as db:
            context(db, owner_id, family_id)
            result = db.execute(
                update(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.owner_id == owner_id,
                    Conversation.active_run == run_id,
                )
                .values(active_run=None, active_until=None)
            )
            if result.rowcount != 1:
                raise ValueError("Generation lease no longer belongs to this request")
            message = Message(
                conversation_id=conversation_id,
                owner_id=owner_id,
                family_id=family_id,
                role="assistant",
                content=content,
                status=status,
                model=model,
            )
            db.add(message)
            db.add(Audit(actor_id=owner_id, action=f"chat.{status}:{conversation_id}"))
            db.flush()
            output = serialize(message)
            db.commit()
            return output

    @router.post("/conversations/{conversation_id}/messages")
    def send(conversation_id: UUID, body: ChatInput, request: Request):
        with Session(engine) as db:
            user = identity(request, db)
            row = owned(db, user, conversation_id)
            if user.role not in {"family_admin", "member"}:
                raise HTTPException(403, "This account cannot send messages")
            try:
                provider.validate_model(body.model)
            except (ProviderUnavailable, ValueError) as error:
                raise HTTPException(503, str(error)) from None
            owner_id, family_id, cid, run_id = user.id, user.family_id, row.id, str(uuid4())
            claimed = db.execute(
                update(Conversation)
                .where(
                    Conversation.id == cid,
                    Conversation.owner_id == owner_id,
                    or_(Conversation.active_until.is_(None), Conversation.active_until < now()),
                )
                .values(
                    active_run=run_id,
                    active_until=now() + timedelta(seconds=settings.llm_timeout_seconds + 30),
                )
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount != 1:
                raise HTTPException(409, "A response is already being generated for this conversation")
            previous = db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == cid, Message.owner_id == owner_id, Message.status == "complete"
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(20)
            ).all()
            selected, size = [], len(body.content)
            for message in previous:
                if size + len(message.content) > 16000:
                    break
                selected.append({"role": message.role, "content": message.content})
                size += len(message.content)
            prompt = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *reversed(selected),
                {"role": "user", "content": body.content},
            ]
            user_message = Message(
                conversation_id=cid,
                owner_id=owner_id,
                family_id=family_id,
                role="user",
                content=body.content,
                status="complete",
                model=None,
            )
            db.add(user_message)
            db.flush()
            sent = serialize(user_message)
            db.commit()

        async def stream():
            chunks, status, saved = [], "failed", None
            try:
                yield event("start", {"message": sent, "provider": "ollama", "local": True})
                length = 0
                async for delta in provider.stream(body.model, prompt):
                    if await request.is_disconnected():
                        raise asyncio.CancelledError
                    length += len(delta)
                    if length > 40000:
                        raise ProviderUnavailable("Response exceeded the configured limit")
                    chunks.append(delta)
                    yield event("token", {"text": delta})
                if not chunks:
                    raise ProviderUnavailable("The model returned no text")
                status = "complete"
            except asyncio.CancelledError:
                status = "cancelled"
                raise
            except (httpx.HTTPError, ProviderUnavailable, ValueError, TimeoutError):
                status = "failed"
            finally:
                with anyio.CancelScope(shield=True):
                    try:
                        saved = await run_in_threadpool(
                            finish, owner_id, family_id, cid, run_id, body.model, "".join(chunks), status
                        )
                    except (SQLAlchemyError, ValueError):
                        saved = None
            if saved and status == "complete":
                yield event("done", {"message": saved})
            else:
                yield event(
                    "error",
                    {
                        "detail": "Generation interrupted or could not be saved. Reload the conversation.",
                        "partial_saved": saved is not None,
                    },
                )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    return router
