"""Router for user-managed vehicles."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.database.models import User, Vehicle
from web.schemas.vehicles import VehicleCreate, VehicleResponse, VehicleUpdate
from web.services.vehicle_service import normalize_vehicle_registration


router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _registration_or_400(value: str) -> str:
    try:
        normalized = normalize_vehicle_registration(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not normalized:
        raise HTTPException(status_code=400, detail="Vehicle registration is required")
    return normalized


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(
    active_only: bool = Query(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Vehicle).filter(Vehicle.user_id == user.id)
    if active_only:
        query = query.filter(Vehicle.is_active.is_(True))
    return query.order_by(Vehicle.name.asc(), Vehicle.registration.asc()).all()


@router.post("", response_model=VehicleResponse, status_code=201)
def create_vehicle(
    payload: VehicleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Vehicle name is required")

    vehicle = Vehicle(
        user_id=user.id,
        name=name,
        registration=_registration_or_400(payload.registration),
        is_active=True,
    )
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vehicle with this registration already exists",
        ) from exc
    db.refresh(vehicle)
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.user_id == user.id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise HTTPException(status_code=400, detail="Vehicle name is required")
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise HTTPException(status_code=400, detail="Vehicle name is required")
    if "registration" in changes:
        if changes["registration"] is None:
            raise HTTPException(status_code=400, detail="Vehicle registration is required")
        changes["registration"] = _registration_or_400(changes["registration"])
    if changes.get("is_active") is None and "is_active" in changes:
        raise HTTPException(status_code=400, detail="Vehicle status is required")
    for key, value in changes.items():
        setattr(vehicle, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vehicle with this registration already exists",
        ) from exc
    db.refresh(vehicle)
    return vehicle
