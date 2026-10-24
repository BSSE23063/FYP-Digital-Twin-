"""
Shared FastAPI dependencies: extracting the authenticated user from a Bearer
token, and the "is this caller the twin's owner" check every owner-only route
needs.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.db.models import Twin, User
from backend.db.session import get_db
from backend.services.auth_service import decode_token
from backend.services.twin_service import TwinService


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """For chat: a visitor MAY be authenticated (to get named access/memory)
    or may be a fully anonymous public visitor (no header at all) — both are
    valid, so this never raises, just returns None when there's no caller."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization, db)
    except HTTPException:
        return None


def require_owner(twin_id: str, current_user: User, db: Session) -> Twin:
    """Every owner-only route (delete a twin, manage its sources/grants/
    knowledge gaps) needs exactly this check — centralized so it can't drift."""
    twin = TwinService(db).get_twin(twin_id)
    if not twin:
        raise HTTPException(status_code=404, detail="Twin not found")
    if twin.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this twin")
    return twin
