"""
Defines the state schema for the LangGraph Agent.
"""
import operator
from typing import Annotated, List, Optional, Sequence, TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # 'operator.add' ensures messages are appended to the list, creating conversational memory
    messages: Annotated[Sequence[BaseMessage], operator.add]
    twin_id: str
    visitor_id: Optional[str]  # None for an anonymous/public visitor: no memory lookup happens
    allowed_visibilities: List[str]
    persona_prompt: str
    domain: str  # the one topic this twin's knowledge is scoped to (session 21)
    context_documents: List[dict]
    memory_documents: List[dict]
    # Everything below is optional on the initial call — nodes read these with
    # state.get(key, default), so existing callers don't need to supply them.
    raw_top_score: float  # top knowledge-retrieval score BEFORE grading filters it out
    rewrite_count: int  # caps the query-rewrite loop at one retry
    search_query_override: Optional[str]  # set by transform_query_node, read by retrieve_node
    policy_decision: str  # "answer" | "escalate" — set by generate_node
    confidence_score: float  # top knowledge score actually used in the answer
