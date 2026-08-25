"""Schemas for user-managed vehicles."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    registration: str = Field(min_length=1, max_length=16)


class VehicleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    registration: Optional[str] = Field(default=None, min_length=1, max_length=16)
    is_active: Optional[bool] = None


class VehicleResponse(BaseModel):
    id: int
    name: str
    registration: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
