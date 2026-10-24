"""
Access grants API: the owner naming who may see their twin's non-public
material. Owner-only — a visitor never gets to decide their own tier.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.db.models import AccessGrant, User
from backend.db.session import get_db
from backend.services.access_service import AccessService

router = APIRouter(prefix="/twins/{twin_id}/grants", tags=["grants"])


class GrantCreateRequest(BaseModel):
    visitor_email: str
    tier_name: str = "friends"
    expires_at: Optional[datetime] = None


class GrantResponse(BaseModel):
    id: str
    twin_id: str
    visitor_id: Optional[str] = None
    visitor_email: Optional[str] = None
    tier_name: str
    granted_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


def _to_response(grant: AccessGrant) -> GrantResponse:
    # Built manually rather than via response_model auto-conversion, since
    # visitor_email comes from the related User row (grant.visitor.email),
    # not a plain column on AccessGrant itself.
    return GrantResponse(
        id=grant.id,
        twin_id=grant.twin_id,
        visitor_id=grant.visitor_id,
        visitor_email=grant.visitor.email if grant.visitor else None,
        tier_name=grant.tier_name,
        granted_at=grant.granted_at,
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
    )


@router.post("", response_model=GrantResponse)
def create_grant(
    twin_id: str,
    payload: GrantCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    grant = AccessService(db).grant_access(
        twin_id=twin_id,
        granted_by=current_user.id,
        visitor_email=payload.visitor_email,
        tier_name=payload.tier_name,
        expires_at=payload.expires_at,
    )
    return _to_response(grant)


@router.get("", response_model=List[GrantResponse])
def list_grants(
    twin_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    return [_to_response(g) for g in AccessService(db).list_grants(twin_id)]


@router.delete("/{visitor_id}")
def revoke_grant(
    twin_id: str,
    visitor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    if not AccessService(db).revoke_access(twin_id, visitor_id):
        raise HTTPException(status_code=404, detail="No active grant found for this visitor")
    return {"message": "Access revoked"}
