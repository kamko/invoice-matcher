"""Schemas for client-side encrypted secret payloads."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ClientEncryptedSecretPayload(BaseModel):
    """Opaque encrypted payload produced in the browser."""

    ciphertext: str = Field(..., min_length=1)
    nonce: str = Field(..., min_length=1)
    salt: str = Field(..., min_length=1)
    kdf: str = Field(..., min_length=1)
    kdf_params: dict[str, Any]


class ClientEncryptedSecretResponse(BaseModel):
    """Stored encrypted payload returned to the browser."""

    configured: bool
    ciphertext: str | None = None
    nonce: str | None = None
    salt: str | None = None
    kdf: str | None = None
    kdf_params: dict[str, Any] | None = None
    updated_at: datetime | None = None
