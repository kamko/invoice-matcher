"""Helpers for server-side encryption of provider credentials."""

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from web.config import settings


def _get_fernet() -> Fernet:
    secret_source = settings.encryption_key or settings.secret_key
    digest = hashlib.sha256(secret_source.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_json(value: dict[str, Any]) -> str:
    """Encrypt a JSON-serializable dictionary."""
    payload = json.dumps(value).encode("utf-8")
    return _get_fernet().encrypt(payload).decode("utf-8")


def decrypt_json(value: str) -> dict[str, Any]:
    """Decrypt a JSON payload."""
    decrypted = _get_fernet().decrypt(value.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))
