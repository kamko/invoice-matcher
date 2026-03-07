"""Settings router for app configuration."""

from typing import Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from web.database.connection import get_db
from web.database.models import AppSettings


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_all_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get all settings as a key-value dict."""
    settings = db.query(AppSettings).all()
    return {s.key: s.value for s in settings}


@router.get("/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    """Get a single setting by key."""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    return {"key": key, "value": setting.value if setting else None}


@router.put("/{key}")
def set_setting(key: str, value: str = Query(...), db: Session = Depends(get_db)):
    """Set a setting value."""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = AppSettings(key=key, value=value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": value}


@router.delete("/{key}")
def delete_setting(key: str, db: Session = Depends(get_db)):
    """Delete a setting."""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting:
        db.delete(setting)
        db.commit()
    return {"success": True}
