"""Integration secrets: authenticated encryption, separate persistent key, no plaintext API."""

import os

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from .archive import sync_directory


def cipher(settings, create=False):
    directory = settings.data_dir / ".secrets"
    path = directory / "integrations.key"
    try:
        if create:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(Fernet.generate_key())
                    handle.flush()
                    os.fsync(handle.fileno())
                sync_directory(directory)
        return Fernet(path.read_bytes())
    except (OSError, ValueError):
        raise HTTPException(
            503, "Integration encryption key unavailable; restore the key or replace the token"
        ) from None


def encrypt(settings, value):
    return cipher(settings, create=True).encrypt(value.encode()).decode()


def decrypt(settings, value):
    if not value:
        return ""
    try:
        return cipher(settings).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(503, "Integration token cannot be decrypted; replace it in settings") from None
