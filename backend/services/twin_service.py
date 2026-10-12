"""
Twin service for managing Digital Twins and access tiers.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.db.models import Twin, User, AccessTier
from backend.rag.vector_store import get_vector_store


class TwinService:
    def __init__(self, db: Session):
        self.db = db
        self.vector_store = get_vector_store()

    def get_or_create_default_user(self, email: str = "owner@digitaltwin.local") -> User:
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                hashed_password="mock_hashed_password",
                display_name="Twin Owner",
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def create_twin(
        self,
        name: str,
        owner_id: Optional[str] = None,
        description: Optional[str] = None,
        persona_prompt: Optional[str] = None,
    ) -> Twin:
        if not owner_id:
            user = self.get_or_create_default_user()
            owner_id = user.id

        twin = Twin(
            name=name,
            owner_id=owner_id,
            description=description,
            persona_prompt=persona_prompt,
        )
        self.db.add(twin)
        self.db.flush()

        # Seed default access tiers for this twin
        default_tiers = [
            AccessTier(
                twin_id=twin.id,
                tier_name="public",
                description="Public visitors (unrestricted public documents only)",
                allowed_visibilities="public",
            ),
            AccessTier(
                twin_id=twin.id,
                tier_name="friends",
                description="Trusted friends or colleagues",
                allowed_visibilities="public,friends",
            ),
            AccessTier(
                twin_id=twin.id,
                tier_name="private",
                description="Twin owner only (all personal documents)",
                allowed_visibilities="public,friends,private",
            ),
        ]
        self.db.add_all(default_tiers)
        self.db.commit()
        self.db.refresh(twin)
        return twin

    def get_twin(self, twin_id: str) -> Optional[Twin]:
        return self.db.query(Twin).filter(Twin.id == twin_id).first()

    def list_twins(self) -> List[Twin]:
        return self.db.query(Twin).order_by(Twin.created_at.desc()).all()

    def delete_twin(self, twin_id: str) -> bool:
        twin = self.get_twin(twin_id)
        if not twin:
            return False

        # Remove vector store data
        self.vector_store.delete_by_twin(twin_id)

        # Delete database records (cascades chunks, documents, conversations)
        self.db.delete(twin)
        self.db.commit()
        return True

