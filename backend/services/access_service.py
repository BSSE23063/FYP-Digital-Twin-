"""
Access grant service: an owner naming a specific person who may see their
twin's non-public material (CLAUDE.md §8's access_grants design).

Simplification, stated plainly: this always find-or-creates the visitor's
User row immediately and resolves straight to visitor_id. The model also
supports a pending invited_email (someone not yet registered at all), but
building the later "claim this invite when you eventually log in with that
email" flow is its own separate piece of work — not needed to make granting
access actually function end to end today.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.db.models import AccessGrant, User


class AccessService:
    def __init__(self, db: Session):
        self.db = db

    def grant_access(
        self,
        twin_id: str,
        granted_by: str,
        visitor_email: str,
        tier_name: str = "friends",
        expires_at: Optional[datetime] = None,
    ) -> AccessGrant:
        visitor = self.db.query(User).filter(User.email == visitor_email).first()
        if not visitor:
            visitor = User(email=visitor_email, password_hash=None, display_name=visitor_email.split("@")[0])
            self.db.add(visitor)
            self.db.flush()

        # The partial unique index only allows one ACTIVE grant per visitor —
        # revoke any existing one first so re-granting (e.g. a tier change)
        # doesn't just fail on that constraint.
        existing = (
            self.db.query(AccessGrant)
            .filter(
                AccessGrant.twin_id == twin_id,
                AccessGrant.visitor_id == visitor.id,
                AccessGrant.revoked_at.is_(None),
            )
            .first()
        )
        if existing:
            existing.revoked_at = datetime.now(timezone.utc)
            self.db.flush()

        grant = AccessGrant(
            twin_id=twin_id,
            visitor_id=visitor.id,
            tier_name=tier_name,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        self.db.add(grant)
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def revoke_access(self, twin_id: str, visitor_id: str) -> bool:
        grant = (
            self.db.query(AccessGrant)
            .filter(
                AccessGrant.twin_id == twin_id,
                AccessGrant.visitor_id == visitor_id,
                AccessGrant.revoked_at.is_(None),
            )
            .first()
        )
        if not grant:
            return False
        grant.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def list_grants(self, twin_id: str) -> List[AccessGrant]:
        return (
            self.db.query(AccessGrant)
            .filter(AccessGrant.twin_id == twin_id)
            .order_by(AccessGrant.granted_at.desc())
            .all()
        )
