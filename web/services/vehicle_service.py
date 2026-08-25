"""Shared vehicle validation helpers."""

import re
from typing import Optional


VEHICLE_REGISTRATION_PATTERN = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$")


def normalize_vehicle_registration(value: Optional[str]) -> Optional[str]:
    """Return a compact uppercase vehicle registration or None."""
    if not value or not value.strip():
        return None
    normalized = re.sub(r"[\s-]+", "", value).upper()
    if not VEHICLE_REGISTRATION_PATTERN.fullmatch(normalized):
        raise ValueError("Vehicle registration must use the format KE885HH")
    return normalized
