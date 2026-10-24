"""
Gap Analyst agent — the "collect" half of this project's multi-agent context-
collection feature (session 17), built on the user's explicit framing:
help collect and manage a twin's context, scoped specifically to the backlog
of questions real visitors already asked that the twin couldn't answer
(KnowledgeGap rows), not a fresh open-ended interview.

Reviews a twin's PENDING gaps and groups semantically similar ones into
clusters, so the owner addresses "what's your work background?" once instead
of three near-duplicate phrasings of it separately. Pure analysis: this agent
never writes to the database and never answers a question on the owner's
behalf — see curator.py for the agent that handles the owner's actual answer.

Bugfix (session 20), two layers, found on a real twin's real data:
1. **Root cause**: some pending gaps had a genuinely blank `question_text` —
   traced to a real conversation where three visitor messages were empty
   strings, each escalated and persisted with nothing to actually cluster
   (see conversation_service.py's matching fix, which now rejects blank
   messages at the source so this stops happening going forward). Asked to
   cluster gaps where some entries had no text at all, the model's live
   response was literally "I only have the IDs... could you provide the
   question content?" — not a hallucination, an accurate complaint about a
   nonsensical ask. Fixed at the root: blank-text gaps are filtered out
   before the LLM ever sees them and handled directly as their own
   "Blank messages" cluster (dismissible, not askable — there's nothing to
   answer).
2. **Defense in depth**: the same Groq model has also been observed
   outright refusing the forced structured-output tool call on a
   perfectly normal, non-blank prompt (`groq.BadRequestError: Tool choice
   is required, but model did not call a tool`) — plain nondeterminism, not
   caused by bad input. One retry clears most of these; if both attempts
   fail, this falls back to one cluster per (non-blank) gap rather than
   raising — a broken Analyst call should never block the owner from seeing
   or answering their pending questions at all.
"""
import logging
from typing import List

from pydantic import BaseModel, Field

from backend.agent.nodes import get_llm
from backend.db.models import KnowledgeGap

logger = logging.getLogger(__name__)


class GapCluster(BaseModel):
    theme: str = Field(description="A short (2-5 word) label for what this cluster of questions is about.")
    gap_ids: List[str] = Field(description="The knowledge_gaps.id values grouped into this cluster.")
    suggested_prompt: str = Field(
        description="One clear question to ask the twin's owner that would answer every gap in this cluster."
    )


class GapAnalysis(BaseModel):
    clusters: List[GapCluster]


def analyze_gaps(gaps: List[KnowledgeGap]) -> List[GapCluster]:
    """Clusters pending gaps by theme. Short-circuits for 0-1 gaps — there's
    nothing to merge, and it saves an LLM call on the common case of a twin
    with just one open question."""
    if not gaps:
        return []

    blank = [g for g in gaps if not g.question_text.strip()]
    real_gaps = [g for g in gaps if g.question_text.strip()]

    clusters: List[GapCluster] = []
    if blank:
        clusters.append(
            GapCluster(
                theme="Blank messages",
                gap_ids=[g.id for g in blank],
                suggested_prompt="These came in as empty messages — there's nothing to answer. Dismiss them.",
            )
        )

    if not real_gaps:
        return clusters
    if len(real_gaps) == 1:
        g = real_gaps[0]
        clusters.append(GapCluster(theme="Unanswered question", gap_ids=[g.id], suggested_prompt=g.question_text))
        return clusters

    listing = "\n".join(f"- id={g.id}: {g.question_text}" for g in real_gaps)
    prompt = (
        "Below are questions real visitors asked a person's AI digital twin that it "
        "could not answer. Group questions asking about the same underlying topic "
        "into clusters (e.g. three different phrasings of 'what do you do for work' "
        "belong in one cluster). Every gap id must appear in exactly one cluster — "
        "don't drop any, don't duplicate any. A cluster can have just one gap if "
        "nothing else relates to it. For each cluster, write one clear question "
        "that, if the owner answers it, would resolve every gap in that "
        "cluster.\n\n" + listing
    )
    structured_llm = get_llm().with_structured_output(GapAnalysis)
    result = None
    for attempt in range(2):
        try:
            result = structured_llm.invoke(prompt)
            break
        except Exception:
            logger.warning("Gap Analyst structured call failed (attempt %d/2)", attempt + 1, exc_info=True)

    if result is None:
        # Both attempts failed — degrade to one cluster per gap rather than
        # raising. The owner still sees and can answer every pending
        # question; they just don't get the clustering convenience this
        # round.
        clusters.extend(
            GapCluster(theme="Unanswered question", gap_ids=[g.id], suggested_prompt=g.question_text)
            for g in real_gaps
        )
        return clusters

    # Safety net: the prompt instructs full coverage, but structured LLM
    # output is never guaranteed to follow instructions exactly — any id it
    # dropped gets its own single-gap cluster instead of silently vanishing
    # from the owner's queue.
    seen = {gid for c in result.clusters for gid in c.gap_ids}
    by_id = {g.id: g for g in real_gaps}
    for gid, g in by_id.items():
        if gid not in seen:
            result.clusters.append(
                GapCluster(theme="Unanswered question", gap_ids=[gid], suggested_prompt=g.question_text)
            )
    clusters.extend(result.clusters)
    return clusters
