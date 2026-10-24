"""
Twin service: creating/reading/updating/deleting digital twins, their avatar
image and voice sample, public discovery, and seeding their default access
tiers.
"""
import re
import shutil
import tempfile
import uuid as uuid_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, List, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import AccessTier, MediaAsset, MediaAssetType, SourceStatus, Twin
from backend.vectordb.collections import delete_twin_collection
from backend.voice.audio_utils import load_audio_as_float32, save_wav

# Longest reference clip ever handed to the cloning model, enforced at upload
# time by keeping only the first N seconds — NOT a soft guideline. Session 11
# (CLAUDE.md §9.5) found a long, unedited recording reproducibly made the
# model emit near-silent garbage (a 47s clip -> 0.7s of output); trimming to
# 12s fixed it. Session 14 hit the exact same failure again from a fresh 44s
# upload taken through this endpoint, which was saving the raw upload
# untouched instead of enforcing any limit — this constant plus the trim
# below is that fix, not a new precaution.
MAX_VOICE_SAMPLE_SECONDS = 25


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "twin"
    return f"{base}-{uuid_lib.uuid4().hex[:6]}"


class TwinService:
    def __init__(self, db: Session):
        self.db = db

    def create_twin(
        self,
        owner_id: str,
        name: str,
        domain: str,
        slug: Optional[str] = None,
        bio: Optional[str] = None,
        persona_prompt: Optional[str] = None,
    ) -> Twin:
        twin = Twin(
            owner_id=owner_id,
            slug=slug or _slugify(name),
            name=name,
            domain=domain,
            bio=bio,
            persona_prompt=persona_prompt,
        )
        self.db.add(twin)
        self.db.flush()  # assigns twin.id without ending the transaction

        # Seed the default tiers every twin needs: WHAT each tier may see.
        # WHO holds a tier is a separate concern (AccessGrant).
        default_tiers = [
            AccessTier(twin_id=twin.id, tier_name="public", allowed_visibilities="public"),
            AccessTier(twin_id=twin.id, tier_name="friends", allowed_visibilities="public,friends"),
            AccessTier(twin_id=twin.id, tier_name="private", allowed_visibilities="public,friends,private"),
        ]
        self.db.add_all(default_tiers)
        self.db.commit()
        self.db.refresh(twin)
        return twin

    def get_twin(self, twin_id: str) -> Optional[Twin]:
        return self.db.query(Twin).filter(Twin.id == twin_id).first()

    def update_twin(
        self,
        twin_id: str,
        name: Optional[str] = None,
        bio: Optional[str] = None,
        persona_prompt: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Optional[Twin]:
        twin = self.get_twin(twin_id)
        if not twin:
            return None
        if name is not None:
            twin.name = name
        if bio is not None:
            twin.bio = bio
        if persona_prompt is not None:
            twin.persona_prompt = persona_prompt
        if domain is not None:
            twin.domain = domain
        self.db.commit()
        self.db.refresh(twin)
        return twin

    def set_avatar(self, twin_id: str, filename: str, file_obj: IO[bytes]) -> Optional[Twin]:
        twin = self.get_twin(twin_id)
        if not twin:
            return None
        avatar_dir = Path(settings.AVATAR_DIR)
        avatar_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix.lower() or ".png"
        relative_path = f"{twin_id}{ext}"
        with open(avatar_dir / relative_path, "wb") as f:
            shutil.copyfileobj(file_obj, f)
        twin.avatar_path = relative_path
        self.db.commit()
        self.db.refresh(twin)
        return twin

    def get_twin_by_slug(self, slug: str) -> Optional[Twin]:
        """Slugs exist for exactly this — a human-readable, shareable handle
        for an invite link — but had no lookup route until the frontend
        actually needed one (session 12)."""
        return self.db.query(Twin).filter(Twin.slug == slug).first()

    def list_twins(self, owner_id: str) -> List[Twin]:
        return (
            self.db.query(Twin)
            .filter(Twin.owner_id == owner_id)
            .order_by(Twin.created_at.desc())
            .all()
        )

    def list_public_twins(self) -> List[Twin]:
        """Every active twin, for the visitor-facing discovery gallery — click
        a card, start talking, no handle/ID needed (session 14). No separate
        "discoverable" flag exists on Twin; a twin's own knowledge is still
        gated by its per-source visibility tiers regardless of whether the
        twin itself is listed here, so this is safe to keep simple."""
        return self.db.query(Twin).filter(Twin.is_active.is_(True)).order_by(Twin.created_at.desc()).all()

    def set_voice_sample(
        self, twin_id: str, filename: str, file_obj: IO[bytes], consent: bool
    ) -> Optional[MediaAsset]:
        """Saves the owner's own recording as this twin's cloning reference.
        `consent` must be explicit and true — mirrors the schema's own
        consent-before-ready constraint (CLAUDE.md §8: media_assets), now
        actually enforced by a caller instead of just existing in the DB.

        The upload is decoded (reusing the same robust soundfile->PyAV
        fallback the ASR path already relies on, so webm/ogg/opus/whatever a
        browser or phone produces all work) and re-saved as a clean 16-bit
        WAV capped to MAX_VOICE_SAMPLE_SECONDS — NOT a pass-through copy like
        this used to be. See the module-level MAX_VOICE_SAMPLE_SECONDS
        docstring for why: an untrimmed raw upload reproducibly makes the
        cloning model emit near-silent garbage instead of real speech."""
        twin = self.get_twin(twin_id)
        if not twin:
            return None

        # Decode via a temp file first — load_audio_as_float32 takes a path,
        # and the upload's own extension can't be trusted as the true format
        # (a browser recording claims .webm but the MediaRecorder's actual
        # container can vary by browser/codec support).
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".bin", delete=False) as tmp:
            shutil.copyfileobj(file_obj, tmp)
            tmp_path = tmp.name
        try:
            samples, sample_rate = load_audio_as_float32(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        max_samples = MAX_VOICE_SAMPLE_SECONDS * sample_rate
        if len(samples) > max_samples:
            samples = samples[:max_samples]
        duration_seconds = len(samples) / sample_rate if sample_rate else 0.0

        voice_dir = Path(settings.VOICE_SAMPLES_DIR)
        voice_dir.mkdir(parents=True, exist_ok=True)
        relative_path = f"{twin_id}.wav"
        save_wav(voice_dir / relative_path, samples, sample_rate)

        # Replace any prior voice sample for this twin rather than accumulating
        # one row per re-recording — only the latest is ever used.
        existing = (
            self.db.query(MediaAsset)
            .filter(MediaAsset.twin_id == twin_id, MediaAsset.asset_type == MediaAssetType.VOICE_SAMPLE.value)
            .first()
        )
        if existing:
            self.db.delete(existing)
            self.db.flush()

        asset = MediaAsset(
            twin_id=twin_id,
            asset_type=MediaAssetType.VOICE_SAMPLE.value,
            storage_path=relative_path,
            duration_seconds=duration_seconds,
            format="wav",
            status=SourceStatus.COMPLETED.value if consent else SourceStatus.FAILED.value,
            consent_confirmed_at=datetime.now(timezone.utc) if consent else None,
            error_message=None if consent else "Upload rejected: voice consent was not confirmed",
        )
        self.db.add(asset)
        self.db.commit()
        if not consent:
            # Constraint "status <> 'completed' OR consent_confirmed_at IS NOT NULL"
            # means an unconsented recording can exist, just never as 'completed' —
            # it is kept as a failed row for audit, not silently discarded.
            return None
        self.db.refresh(asset)
        return asset

    def get_voice_sample_path(self, twin_id: str) -> Optional[str]:
        """Absolute path to this twin's own cloned-voice reference clip, or
        None if it hasn't uploaded one yet — callers fall back to the global
        catalog/default voice in that case (backend/voice/tts.py)."""
        asset = (
            self.db.query(MediaAsset)
            .filter(
                MediaAsset.twin_id == twin_id,
                MediaAsset.asset_type == MediaAssetType.VOICE_SAMPLE.value,
                MediaAsset.status == SourceStatus.COMPLETED.value,
            )
            .first()
        )
        if not asset:
            return None
        path = Path(settings.VOICE_SAMPLES_DIR) / asset.storage_path
        return str(path) if path.exists() else None

    def delete_twin(self, twin_id: str) -> bool:
        twin = self.get_twin(twin_id)
        if not twin:
            return False
        # Drop the twin's entire Qdrant collection first (silo model, §8:
        # physical isolation makes "delete everything for this twin" a single
        # collection drop, not a filtered bulk-delete).
        delete_twin_collection(twin_id)
        self.db.delete(twin)  # cascades to sources/grants/conversations/etc. in Postgres
        self.db.commit()
        return True
