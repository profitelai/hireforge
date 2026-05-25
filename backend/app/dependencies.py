"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
from app.models import Profile, User
from app.services.settings import NO_API_KEY_PROVIDERS, get_llm_config, provider_from_model

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header. Raises 401 if missing/invalid."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    email = decode_access_token(credentials.credentials)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def get_profile_or_404(profile_id: int, db: Session = Depends(get_db)) -> Profile:
    profile = db.query(Profile).filter_by(id=profile_id).first()
    if not profile:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found.", "code": "PROFILE_NOT_FOUND"},
        )
    return profile


def require_llm_config(db: Session = Depends(get_db)) -> tuple[str, str]:
    provider, api_key = get_llm_config(db)
    if not provider:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "LLM not configured. Set provider and API key in Settings.",
                "code": "API_KEY_NOT_CONFIGURED",
            },
        )
    provider_family = provider_from_model(provider)
    needs_key = provider_family not in NO_API_KEY_PROVIDERS
    if needs_key and not api_key:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "LLM not configured. Set provider and API key in Settings.",
                "code": "API_KEY_NOT_CONFIGURED",
            },
        )
    return provider, api_key


def get_user_profile_ids(user: User, db: Session) -> list[int]:
    """Return all profile IDs owned by the current user."""
    from app.models import Profile
    rows = db.query(Profile.id).filter_by(user_id=user.id).all()
    return [r[0] for r in rows]


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allow only user_id=1 (the first registered owner/admin)."""
    if current_user.id != 1:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
