"""
Constructs and compiles the self-corrective LangGraph state machine.

retrieve -> grade -> [conditional: rewrite once if plausibly-relevant-but-weak,
else go straight to generate] -> transform_query -> retrieve (loop, max once)
                                                   -> generate -> END
"""
from langgraph.graph import END, StateGraph

from backend.agent.nodes import (
    generate_node,
    grade_documents_node,
    retrieve_node,
    should_rewrite,
    transform_query_node,
)
from backend.agent.state import AgentState

workflow = StateGraph(AgentState)

workflow.add_node("retrieve", retrieve_node)
workflow.add_node("grade_documents", grade_documents_node)
workflow.add_node("transform_query", transform_query_node)
workflow.add_node("generate", generate_node)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    should_rewrite,
    {"transform_query": "transform_query", "generate": "generate"},
)
workflow.add_edge("transform_query", "retrieve")
workflow.add_edge("generate", END)

rag_app = workflow.compile()
