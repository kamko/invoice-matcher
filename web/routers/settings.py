"""Settings router for app configuration."""

from email.utils import parseaddr
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database.connection import get_db
from web.database.models import User, UserSetting
from web.services.email_service import get_mailjet_sender_status


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_all_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get all settings as a key-value dict."""
    settings = db.query(UserSetting).filter(UserSetting.user_id == user.id).all()
    return {s.key: s.value for s in settings}


@router.get("/mailjet-sender-status")
def get_sender_status(
    email: str = Query(...),
    user: User = Depends(get_current_user),
):
    """Check an exact sender and its domain against active Mailjet senders."""
    normalized = email.strip().lower()
    _, parsed = parseaddr(normalized)
    if parsed != normalized or "@" not in parsed:
        raise HTTPException(status_code=400, detail="Invalid sender email address")

    try:
        return get_mailjet_sender_status(normalized)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{key}")
def get_setting(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single setting by key."""
    setting = db.query(UserSetting).filter(
        UserSetting.user_id == user.id,
        UserSetting.key == key,
    ).first()
    return {"key": key, "value": setting.value if setting else None}


@router.put("/{key}")
def set_setting(
    key: str,
    value: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set a setting value."""
    setting = db.query(UserSetting).filter(
        UserSetting.user_id == user.id,
        UserSetting.key == key,
    ).first()
    if setting:
        setting.value = value
    else:
        setting = UserSetting(user_id=user.id, key=key, value=value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": value}


@router.delete("/{key}")
def delete_setting(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a setting."""
    setting = db.query(UserSetting).filter(
        UserSetting.user_id == user.id,
        UserSetting.key == key,
    ).first()
    if setting:
        db.delete(setting)
        db.commit()
    return {"success": True}
