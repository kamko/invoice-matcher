"""Router for client-side encrypted secret storage."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.database.models import User, UserSecret
from web.schemas.secrets import ClientEncryptedSecretPayload, ClientEncryptedSecretResponse

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


@router.get("/fio", response_model=ClientEncryptedSecretResponse)
def get_fio_secret(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the stored client-side encrypted Fio token payload."""
    secret = db.query(UserSecret).filter(
        UserSecret.user_id == user.id,
        UserSecret.secret_type == "fio_token",
    ).first()

    if not secret:
        return ClientEncryptedSecretResponse(configured=False)

    return ClientEncryptedSecretResponse(
        configured=True,
        ciphertext=secret.ciphertext,
        nonce=secret.nonce,
        salt=secret.salt,
        kdf=secret.kdf,
        kdf_params=secret.kdf_params,
        updated_at=secret.updated_at,
    )


@router.put("/fio", response_model=ClientEncryptedSecretResponse)
def save_fio_secret(
    payload: ClientEncryptedSecretPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save the client-side encrypted Fio token payload."""
    secret = db.query(UserSecret).filter(
        UserSecret.user_id == user.id,
        UserSecret.secret_type == "fio_token",
    ).first()

    if not secret:
        secret = UserSecret(user_id=user.id, secret_type="fio_token")
        db.add(secret)

    secret.ciphertext = payload.ciphertext
    secret.nonce = payload.nonce
    secret.salt = payload.salt
    secret.kdf = payload.kdf
    secret.kdf_params = payload.kdf_params

    db.commit()
    db.refresh(secret)

    return ClientEncryptedSecretResponse(
        configured=True,
        ciphertext=secret.ciphertext,
        nonce=secret.nonce,
        salt=secret.salt,
        kdf=secret.kdf,
        kdf_params=secret.kdf_params,
        updated_at=secret.updated_at,
    )


@router.delete("/fio")
def delete_fio_secret(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete the stored encrypted Fio token payload."""
    secret = db.query(UserSecret).filter(
        UserSecret.user_id == user.id,
        UserSecret.secret_type == "fio_token",
    ).first()
    if secret:
        db.delete(secret)
        db.commit()
    return {"success": True}
