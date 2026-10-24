"""
Curator agent — the "manage" half of this project's multi-agent context-
collection feature (session 17). Takes the owner's raw answer to a (possibly
clustered) knowledge gap and turns it into clean, well-written knowledge text
plus a suggested visibility tier — flagging content that reads as personal or
sensitive instead of defaulting everything to public.

Drafts only, never publishes: the owner reviews and can edit both the text
and the visibility in the UI before anything is actually saved
(KnowledgeGapService.confirm_cluster_answer does the actual write). An agent
writing something into a person's own knowledge base in their own voice
without them seeing it first would be a real trust problem for exactly the
kind of platform this is — consistent with this project's existing consent
requirements elsewhere (voice cloning, §8's media_assets).

Bugfix (session 20): hardened the same way gap_analyst.py was after a real
structured-output failure was observed on this project's Groq model (see
that file's docstring) — one retry, then a safe fallback instead of raising.
Here the fallback is the owner's own raw answer, verbatim, defaulted to
'public' visibility with a reasoning note saying the cleanup step failed —
the owner can still save it (or pick a different tier) rather than being
blocked entirely by an agent hiccup.
"""
import logging
from typing import Literal

from pydantic import BaseModel, Field

from backend.agent.nodes import get_llm

logger = logging.getLogger(__name__)


class CuratedDraft(BaseModel):
    text: str = Field(
        description="The answer rewritten as clear, well-formed text suitable for a knowledge-base "
        "entry — fix fragments and typos, keep every fact stated, add nothing that wasn't said."
    )
    suggested_visibility: Literal["public", "friends", "private"] = Field(
        description="'public' by default; suggest 'private' if the content reads as personal or "
        "sensitive (health, finances, relationships, home address, and similar); suggest 'friends' "
        "for content that's fine for people the owner has granted access to but not the general public."
    )
    reasoning: str = Field(description="One short sentence explaining the visibility suggestion.")


def curate_answer(question_context: str, raw_answer: str) -> CuratedDraft:
    prompt = (
        "A person is answering a question that was asked of their AI digital twin, "
        "so this text becomes part of the twin's permanent knowledge base.\n\n"
        f"Question(s) being answered: {question_context}\n\n"
        f"Their raw answer:\n{raw_answer}\n\n"
        "Rewrite this as clear, well-formed text for a knowledge-base entry, then suggest "
        "a visibility tier for it."
    )
    structured_llm = get_llm().with_structured_output(CuratedDraft)
    for attempt in range(2):
        try:
            return structured_llm.invoke(prompt)
        except Exception:
            logger.warning("Curator structured call failed (attempt %d/2)", attempt + 1, exc_info=True)

    return CuratedDraft(
        text=raw_answer,
        suggested_visibility="public",
        reasoning="AI cleanup failed, so this is your answer exactly as typed — review it before saving.",
    )
