"""
Twins API endpoints for creating, listing, getting, and deleting digital twins.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.twin_service import TwinService

router = APIRouter(prefix="/twins", tags=["twins"])


class TwinCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    persona_prompt: Optional[str] = None


class AccessTierResponse(BaseModel):
    id: str
    tier_name: str
    description: Optional[str] = None
    allowed_visibilities: str


class TwinResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    persona_prompt: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


@router.post("", response_model=TwinResponse)
def create_twin(payload: TwinCreateRequest, db: Session = Depends(get_db)):
    service = TwinService(db)
    twin = service.create_twin(
        name=payload.name,
        description=payload.description,
        persona_prompt=payload.persona_prompt,
    )
    return twin


@router.get("", response_model=List[TwinResponse])
def list_twins(db: Session = Depends(get_db)):
    service = TwinService(db)
    return service.list_twins()


@router.get("/{twin_id}", response_model=TwinResponse)
def get_twin(twin_id: str, db: Session = Depends(get_db)):
    service = TwinService(db)
    twin = service.get_twin(twin_id)
    if not twin:
        raise HTTPException(status_code=404, detail="Twin not found")
    return twin


@router.delete("/{twin_id}")
def delete_twin(twin_id: str, db: Session = Depends(get_db)):
    service = TwinService(db)
    success = service.delete_twin(twin_id)
    if not success:
        raise HTTPException(status_code=404, detail="Twin not found")
    return {"message": "Twin deleted successfully"}

