"""Live lexical retrieval over authorized, committed archive revisions."""

import re
import unicodedata
from uuid import UUID

from sqlalchemy import or_, select

from .archive import Archive
from .db import Memory

STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "what",
    "when",
    "where",
    "who",
    "how",
    "tell",
    "me",
    "about",
    "my",
    "our",
    "and",
    "of",
    "in",
    "to",
    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "de",
    "du",
    "est",
    "sont",
    "mon",
    "ma",
    "mes",
    "nos",
    "notre",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "ou",
    "quand",
    "qui",
    "comment",
    "raconte",
    "moi",
    "sur",
    "et",
    "en",
    "au",
    "souvenir",
    "souvenirs",
    "memory",
    "memories",
    "test",
}


def words(value):
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return set(re.findall(r"[a-z0-9]{2,}", value)) - STOP


def excerpt(content, terms):
    if len(content) <= 2400:
        return content
    blocks = [(start, content[start : start + 1100]) for start in range(0, len(content), 900)]
    selected = sorted(blocks, key=lambda item: len(terms & words(item[1])), reverse=True)[:2]
    return "\n[…]\n".join(text for _, text in sorted(selected))


def retrieve(db, user, settings, question):
    archive = Archive(settings.data_dir)
    terms = words(question)
    rows = db.scalars(
        select(Memory)
        .where(
            Memory.family_id == user.family_id,
            Memory.deleted.is_(False),
            or_(Memory.owner_id == user.id, Memory.visibility == "family"),
        )
        .order_by(Memory.updated_at.desc(), Memory.id)
        .limit(200)
    ).all()
    ranked = []
    for row in rows:
        metadata, content = archive.read(UUID(row.family_id), UUID(row.owner_id), UUID(row.id))
        if (metadata.revision, metadata.visibility, metadata.deleted) != (
            row.revision,
            row.visibility,
            row.deleted,
        ):
            raise ValueError("Archive catalogue needs reconciliation")
        if str(metadata.owner_id) != user.id and metadata.visibility != "family":
            continue
        score = len(terms & words(content)) + 3 * len(terms & words(metadata.title))
        if score or not terms:
            ranked.append((score, metadata, content))
    ranked.sort(key=lambda item: item[0], reverse=True)
    result = []
    for _, metadata, content in ranked[:3]:
        result.append(
            {
                "id": str(metadata.id),
                "title": metadata.title,
                "revision": metadata.revision,
                "verification": metadata.verification,
                "content": excerpt(content, terms),
            }
        )
    return result
