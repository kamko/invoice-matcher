"""Schemas for authentication endpoints."""

from typing import Optional

from pydantic import BaseModel


class AuthUserResponse(BaseModel):
    """Authenticated user profile returned to the frontend."""

    id: int
    email: str
    full_name: Optional[str] = None
    picture_url: Optional[str] = None


class AuthSessionResponse(BaseModel):
    """Current authentication/session state."""

    authenticated: bool
    csrf_token: Optional[str] = None
    user: Optional[AuthUserResponse] = None
