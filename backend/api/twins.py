"""
Twins API: create, list, get, update, delete, avatar upload.

owner_id comes from the authenticated caller (see backend/api/deps.py), not
from the request body — closes the gap flagged since session 7.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.config import settings
from backend.db.models import Twin, User
from backend.db.session import get_db
from backend.services.twin_service import TwinService

router = APIRouter(prefix="/twins", tags=["twins"])


class TwinCreateRequest(BaseModel):
    name: str
    domain: str
    slug: Optional[str] = None
    bio: Optional[str] = None
    persona_prompt: Optional[str] = None


class TwinUpdateRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    persona_prompt: Optional[str] = None
    domain: Optional[str] = None


class TwinResponse(BaseModel):
    id: str
    owner_id: str
    slug: str
    name: str
    domain: str
    bio: Optional[str] = None
    persona_prompt: Optional[str] = None
    avatar_url: Optional[str] = None
    has_voice_sample: bool = False
    is_active: bool


def _to_response(twin: Twin, db: Session) -> TwinResponse:
    # Built manually (not via response_model auto-conversion) since avatar_url
    # is derived from avatar_path + the static mount, not a plain column, and
    # has_voice_sample needs a MediaAsset lookup.
    return TwinResponse(
        id=twin.id,
        owner_id=twin.owner_id,
        slug=twin.slug,
        name=twin.name,
        domain=twin.domain,
        bio=twin.bio,
        persona_prompt=twin.persona_prompt,
        avatar_url=f"/media/avatars/{twin.avatar_path}" if twin.avatar_path else None,
        has_voice_sample=TwinService(db).get_voice_sample_path(twin.id) is not None,
        is_active=twin.is_active,
    )


@router.post("", response_model=TwinResponse)
def create_twin(
    payload: TwinCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    twin = TwinService(db).create_twin(
        owner_id=current_user.id,
        name=payload.name,
        domain=payload.domain,
        slug=payload.slug,
        bio=payload.bio,
        persona_prompt=payload.persona_prompt,
    )
    return _to_response(twin, db)


@router.get("", response_model=List[TwinResponse])
def list_my_twins(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_to_response(t, db) for t in TwinService(db).list_twins(current_user.id)]


@router.get("/public", response_model=List[TwinResponse])
def list_public_twins(db: Session = Depends(get_db)):
    """The visitor-facing discovery gallery — every active twin, browsable and
    clickable with no handle/ID required (session 14). Registered before
    /{twin_id} so "public" isn't swallowed as a twin_id path param, same
    pattern as /by-slug."""
    return [_to_response(t, db) for t in TwinService(db).list_public_twins()]


@router.get("/by-slug/{slug}", response_model=TwinResponse)
def get_twin_by_slug(slug: str, db: Session = Depends(get_db)):
    # Registered before /{twin_id} so "by-slug" isn't swallowed as a twin_id.
    twin = TwinService(db).get_twin_by_slug(slug)
    if not twin:
        raise HTTPException(status_code=404, detail="Twin not found")
    return _to_response(twin, db)


@router.get("/{twin_id}", response_model=TwinResponse)
def get_twin(twin_id: str, db: Session = Depends(get_db)):
    # Left unauthenticated on purpose: a twin's basic profile (name, bio,
    # persona, avatar) is what a visitor needs to see before deciding to chat
    # with it at all — not sensitive by itself.
    twin = TwinService(db).get_twin(twin_id)
    if not twin:
        raise HTTPException(status_code=404, detail="Twin not found")
    return _to_response(twin, db)


@router.patch("/{twin_id}", response_model=TwinResponse)
def update_twin(
    twin_id: str,
    payload: TwinUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    twin = TwinService(db).update_twin(
        twin_id,
        name=payload.name,
        bio=payload.bio,
        persona_prompt=payload.persona_prompt,
        domain=payload.domain,
    )
    return _to_response(twin, db)


@router.post("/{twin_id}/avatar", response_model=TwinResponse)
def upload_avatar(
    twin_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    if (file.content_type or "").split("/")[0] != "image":
        raise HTTPException(status_code=422, detail="File must be an image")
    twin = TwinService(db).set_avatar(twin_id, file.filename or "avatar.png", file.file)
    return _to_response(twin, db)


@router.post("/{twin_id}/voice-sample", response_model=TwinResponse)
def upload_voice_sample(
    twin_id: str,
    file: UploadFile = File(...),
    consent: bool = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The owner's own recording, used to clone this twin's TTS voice
    (backend/voice/tts.py resolves it via TwinService.get_voice_sample_path).
    `consent` must be explicitly true — the schema's own
    consent-before-'completed' constraint on media_assets is enforced here,
    not just declared."""
    require_owner(twin_id, current_user, db)
    if (file.content_type or "").split("/")[0] != "audio":
        raise HTTPException(status_code=422, detail="File must be an audio recording")
    if not consent:
        raise HTTPException(status_code=422, detail="Voice consent is required to clone a voice")
    asset = TwinService(db).set_voice_sample(twin_id, file.filename or "voice.wav", file.file, consent)
    if not asset:
        raise HTTPException(status_code=422, detail="Could not save voice sample")
    twin = TwinService(db).get_twin(twin_id)
    return _to_response(twin, db)


@router.delete("/{twin_id}")
def delete_twin(
    twin_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    TwinService(db).delete_twin(twin_id)
    return {"message": "Twin deleted"}
