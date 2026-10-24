"""
Executable nodes for the self-corrective LangGraph workflow.

Flow (see graph.py): retrieve -> grade -> (maybe one query rewrite + re-retrieve)
-> generate.

The fix for the bug found in session 7 (the agent ignored visible conversation
history even for trivial meta-questions, because the old prompt said "answer
using ONLY the retrieved context") lives in the shared system prompt below: it
explicitly separates "conversational continuity" (free to use history) from
"factual claims about the twin" (must be grounded).

Two generation paths, both built from the same prompt (session 22):
- generate_node: blocking, structured output (a self-reported `grounded`
  boolean) — used by backend/voice/pipeline.py, which needs the full text
  before it can synthesize speech, so streaming buys it nothing.
- generate_stream: a plain token-by-token generator for the text chat
  endpoint — streaming and structured tool-call output don't mix cleanly on
  Groq, so grounding here is self-reported via a tiny leading marker
  (NEEDS_FOLLOWUP) in the plain text instead of a JSON field, detected from
  only the first ~20 characters of the stream and stripped before anything
  reaches the client. Avoids a second LLM call to classify groundedness
  separately, which matters on this project's tight 8,000 TPM Groq limit
  (CLAUDE.md session 20).
"""
from functools import lru_cache
from typing import Iterator, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from backend.config import settings
from backend.agent.state import AgentState
from backend.rag.embeddings import embed_texts
from backend.rag.retriever import search_twin_knowledge, search_visitor_memory


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    # Lazy: importing this module must not crash just because GROQ_API_KEY
    # isn't set yet (e.g. during test collection).
    return ChatGroq(model=settings.GROQ_MODEL, temperature=0.2, groq_api_key=settings.GROQ_API_KEY)


def retrieve_node(state: AgentState):
    """Embeds the search query (a rewritten one if transform_query_node ran,
    otherwise the visitor's latest message), then fetches knowledge (always)
    and this visitor's memory (only if identified) from Qdrant."""
    query_text = state.get("search_query_override") or state["messages"][-1].content
    twin_id = state["twin_id"]
    visitor_id = state.get("visitor_id")
    visibilities = state["allowed_visibilities"]

    query_vector = embed_texts([query_text])[0]

    knowledge = search_twin_knowledge(
        twin_id=twin_id, query_vector=query_vector, allowed_visibilities=visibilities, top_k=5,
    )
    top_score = max((d.get("score") or 0.0 for d in knowledge), default=0.0)

    memory = (
        search_visitor_memory(twin_id=twin_id, visitor_id=visitor_id, query_vector=query_vector, top_k=3)
        if visitor_id
        else []
    )

    return {"context_documents": knowledge, "memory_documents": memory, "raw_top_score": top_score}


def grade_documents_node(state: AgentState):
    """Drops knowledge chunks that scored below the relevance bar. Memory is
    left untouched — it's a handful of small, self-reported facts about this
    visitor, not a ranked semantic-search result set to filter the same way."""
    docs = state.get("context_documents", [])
    graded = [d for d in docs if (d.get("score") or 0.0) >= settings.RETRIEVAL_MIN_SCORE]
    return {"context_documents": graded}


def should_rewrite(state: AgentState) -> Literal["transform_query", "generate"]:
    """Only rewrite if something plausibly relevant was found but didn't quite
    clear the bar. A plain greeting or meta-question will never score well
    against the knowledge base at all — rewriting that would just waste a
    retrieval round-trip, not fix anything."""
    if state.get("rewrite_count", 0) > 0:
        return "generate"  # already rewritten once this turn; never loop forever
    if state.get("context_documents"):
        return "generate"  # something already cleared the bar
    top_score = state.get("raw_top_score", 0.0)
    if settings.RETRIEVAL_REWRITE_SCORE <= top_score < settings.RETRIEVAL_MIN_SCORE:
        return "transform_query"
    return "generate"


_QUERY_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You rewrite a visitor's question into a clearer, more specific search "
        "query for finding relevant facts in someone's personal/professional "
        "knowledge base. Reply with ONLY the rewritten query, nothing else.",
    ),
    ("human", "Original question: {question}\n\nRewritten search query:"),
])


def transform_query_node(state: AgentState):
    """Reformulates the query once to improve retrieval, then the graph loops
    back to retrieve_node. Only changes what's used for the Qdrant search —
    never alters the visitor-facing conversation itself."""
    original = state["messages"][-1].content
    chain = _QUERY_REWRITE_PROMPT | get_llm()
    rewritten = chain.invoke({"question": original}).content.strip()
    return {
        "search_query_override": rewritten,
        "rewrite_count": state.get("rewrite_count", 0) + 1,
    }


def prepare_retrieval(state: AgentState) -> AgentState:
    """Runs retrieve -> grade -> (maybe one rewrite + re-retrieve) as plain
    function calls instead of through the compiled graph. The streaming chat
    path (generate_stream) needs this same retrieval prep but can't use
    graph.invoke() for the final step, since that blocks until generate_node
    finishes — so it calls this directly, then streams the generation step
    itself. graph.py's StateGraph still uses the individual node functions
    this wraps, unchanged."""
    state = {**state, **retrieve_node(state)}
    state = {**state, **grade_documents_node(state)}
    if should_rewrite(state) == "transform_query":
        state = {**state, **transform_query_node(state)}
        state = {**state, **retrieve_node(state)}
        state = {**state, **grade_documents_node(state)}
    return state


def _build_system_instruction(
    persona: str, domain: str, formatted_memory: str, formatted_context: str, *, marker_mode: bool
) -> str:
    """The one prompt both generation paths share. marker_mode=True swaps the
    structured-output `grounded` field instruction for a plain-text leading
    marker (see generate_stream) since streaming can't easily carry a
    separate JSON field alongside the token stream."""
    grounding_instruction = (
        """- If — and only if — the visitor asks a SPECIFIC FACTUAL QUESTION on a
  topic clearly different from this twin's declared domain ({domain}), and
  the retrieved knowledge/memory doesn't cover it either, your ENTIRE reply
  must start with the exact literal text NEEDS_FOLLOWUP on its own line
  (nothing before it), followed by a blank line, then your warm, honest
  explanation that it's outside what you cover (for example: "That's
  outside what I can help with here — I focus on {domain}"). Also use this
  marker for any other factual claim the retrieved knowledge/memory simply
  doesn't cover, domain-related or not. NEVER use this marker for: a
  greeting, small talk, thanks, a question about yourself as a twin (your
  name, what you can help with, how you work), a conversational follow-up,
  or anything already covered by the retrieved knowledge/memory — all of
  those are always fine to answer directly, with no marker, regardless of
  domain. When genuinely unsure whether something counts as off-domain or
  just ordinary conversation, treat it as ordinary conversation and answer
  normally — the marker is for real gaps, not a default."""
        if marker_mode
        else """- If a factual question isn't covered by the retrieved knowledge or memory,
  say so naturally and warmly (for example: "I don't have that on hand, but
  I'll make a note to follow up") instead of a blunt refusal — and report
  grounded=False.
- If — and only if — the visitor asks a SPECIFIC FACTUAL QUESTION on a topic
  clearly different from this twin's declared domain ({domain}), and it
  isn't covered by the retrieved knowledge or memory either, say plainly
  that it's outside what this twin covers (for example: "That's outside
  what I can help with here — I focus on {domain}") and report
  grounded=False. Never do this for a greeting, small talk, thanks, a
  question about yourself as a twin, or a conversational follow-up — those
  are always fine to answer directly regardless of domain. When genuinely
  unsure whether something counts as off-domain or just ordinary
  conversation, treat it as ordinary conversation and answer normally."""
    ).format(domain=domain)

    return f"""You are a digital twin, speaking as the person described below.
Persona: {persona}

This twin's declared domain is: {domain or "general knowledge"}. This scoping
is about substantive, topical FACTUAL questions only — it does not restrict
ordinary conversation. Always feel free to greet the visitor, make small
talk, answer questions about yourself as a twin (your name, what you can
help with, how you work), and build on anything already said in this
conversation, with zero regard for the domain — none of that needs to be
"in scope" to answer normally.

What you remember about this specific visitor:
{formatted_memory}

Retrieved knowledge relevant to the current question:
{formatted_context}

How to answer:
- Keep replies short when you reasonably can — often a sentence or two is
  enough — but this is a preference, not a hard limit: never cut out
  information the visitor actually asked for just to stay brief, and never
  refuse or deflect a question only to keep the reply short. If the
  question calls for more (steps, a list, real detail, or the visitor asks
  for depth), give the fuller answer.
- For conversational things — greetings, small talk, clarifications, or
  referring back to anything already said earlier in this conversation
  (including by the visitor themselves) — just use the conversation history
  naturally. That is not a fact that needs grounding in the retrieved
  knowledge, and it is never out of scope.
- For a specific factual claim about the twin's background, work, or
  preferences, only state what is actually present in the retrieved
  knowledge or visitor memory above. Never invent a fact that isn't there,
  even a plausible-sounding one.
{grounding_instruction}
"""


class TwinReply(BaseModel):
    answer: str = Field(description="The reply to show the visitor, written in the twin's persona.")
    grounded: bool = Field(
        description=(
            "True if every factual claim in the answer is supported by the retrieved "
            "context, the visitor memory, or something already said earlier in this "
            "conversation. False if the visitor asked for a specific fact that isn't "
            "available in any of those, and the answer honestly says so rather than "
            "guessing."
        )
    )


def _format_context_and_memory(state: AgentState) -> tuple[str, str]:
    context = state.get("context_documents", [])
    memory = state.get("memory_documents", [])
    formatted_context = "\n\n".join(
        f"Source ({d['source_id']}): {d['content']}" for d in context
    ) or "None found for this question."
    formatted_memory = "\n".join(f"- {m['content']}" for m in memory) or "Nothing remembered yet."
    return formatted_context, formatted_memory


def generate_node(state: AgentState):
    """Generates a reply using structured output (answer + a self-reported
    `grounded` flag) instead of freeform text, so policy_decision comes from
    an explicit field rather than pattern-matching phrases in prose. Used by
    the voice path (backend/voice/pipeline.py), which needs the complete
    answer before TTS can run — streaming wouldn't help it, so it keeps the
    original blocking/structured-output shape generate_stream can't use."""
    persona = state["persona_prompt"]
    domain = state.get("domain", "")
    context = state.get("context_documents", [])
    formatted_context, formatted_memory = _format_context_and_memory(state)

    system_instruction = _build_system_instruction(
        persona, domain, formatted_memory, formatted_context, marker_mode=False
    )
    messages = [SystemMessage(content=system_instruction)] + list(state["messages"])

    structured_llm = get_llm().with_structured_output(TwinReply)
    reply = structured_llm.invoke(messages)

    confidence = max((d.get("score") or 0.0 for d in context), default=0.0)

    return {
        "messages": [AIMessage(content=reply.answer)],
        "policy_decision": "answer" if reply.grounded else "escalate",
        "confidence_score": confidence,
    }


def generate_stream(state: AgentState) -> Iterator[str | dict]:
    """Streams the reply token-by-token for the text chat endpoint instead of
    blocking for the full answer. Yields plain str chunks as they arrive,
    then exactly one final dict (distinguishable by isinstance) carrying the
    full answer text, policy_decision, and confidence_score once the stream
    ends — callers must consume the whole iterator to get that final dict.

    Grounding can't come from a structured-output field here (Groq's
    streaming tool-call deltas aren't worth parsing incrementally just for
    one boolean), so the model is instead asked to prefix an ungrounded
    answer with a short literal marker (NEEDS_FOLLOWUP) as the very first
    thing it writes. Only the first ~20 characters are buffered to check for
    it — once it's confirmed present or absent, every subsequent token is
    yielded immediately with no added buffering, so the stream stays live."""
    persona = state["persona_prompt"]
    domain = state.get("domain", "")
    context = state.get("context_documents", [])
    formatted_context, formatted_memory = _format_context_and_memory(state)

    system_instruction = _build_system_instruction(
        persona, domain, formatted_memory, formatted_context, marker_mode=True
    )
    messages = [SystemMessage(content=system_instruction)] + list(state["messages"])

    MARKER = "NEEDS_FOLLOWUP"
    buffer = ""
    marker_resolved = False
    is_escalate = False
    # True right after the marker is stripped until the first non-newline
    # token arrives — the blank line the prompt asks the model to put after
    # the marker can land as its own separate token, which plain per-token
    # pass-through wouldn't catch (only the text still sitting in `buffer`
    # at the moment the marker resolves gets .lstrip("\n")'d below).
    suppress_leading_newlines = False
    full_text_parts: list[str] = []

    for piece in get_llm().stream(messages):
        token = piece.content or ""
        if not token:
            continue
        if marker_resolved:
            if suppress_leading_newlines:
                token = token.lstrip("\n")
                if not token:
                    continue
                suppress_leading_newlines = False
            full_text_parts.append(token)
            yield token
            continue

        buffer += token
        stripped = buffer.lstrip()
        if len(stripped) < len(MARKER):
            # Not enough text yet to confirm or rule out the marker — keep buffering.
            if MARKER.startswith(stripped):
                continue
            # Already diverges from the marker; no need to wait further.
        marker_resolved = True
        if stripped.startswith(MARKER):
            is_escalate = True
            remainder = stripped[len(MARKER):].lstrip("\n")
            suppress_leading_newlines = not remainder
        else:
            remainder = buffer
        if remainder:
            full_text_parts.append(remainder)
            yield remainder

    if not marker_resolved and buffer:
        # The whole stream ended while still a strict prefix of the marker
        # (e.g. a reply shorter than 14 chars) — it was never actually the
        # marker, so flush it as ordinary text instead of swallowing it.
        full_text_parts.append(buffer)
        yield buffer

    full_answer = "".join(full_text_parts).strip()
    confidence = max((d.get("score") or 0.0 for d in context), default=0.0)
    yield {
        "answer": full_answer,
        "policy_decision": "escalate" if is_escalate else "answer",
        "confidence_score": confidence,
    }
