"""
LangGraph Self-Corrective RAG Pipeline for Personal AI Digital Twin.

Orchestrates:
1. Retrieve: tenant-isolated ChromaDB query
2. Grade Documents: filters relevant chunks
3. Generate / Transform Query: grounded persona generation or search reformulation
4. Hallucination Check: ensures factual fidelity before delivering response
"""

import time
from typing import List, Dict, Any, Literal, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END

from backend.rag.vector_store import get_vector_store
from backend.llm.client import get_llm
from backend.llm.prompts import (
    DEFAULT_TWIN_PERSONA,
    DOC_GRADER_PROMPT,
    HALLUCINATION_GRADER_PROMPT,
    ANSWER_GRADER_PROMPT,
    QUERY_REWRITE_PROMPT,
)


# ── State Definition ──────────────────────────────────────────

class TwinRAGState(TypedDict):
    question: str
    original_question: str
    twin_id: str
    twin_name: str
    persona_prompt: str
    allowed_visibilities: List[str]
    documents: List[Dict[str, Any]]
    generation: str
    policy_decision: str  # "answer", "decline", "escalate"
    confidence_score: float
    sources: List[Dict[str, Any]]
    retry_count: int
    latency_ms: int
    start_time: float


# ── Structured Output Models ─────────────────────────────────

class GradeDecision(BaseModel):
    binary_score: Literal["yes", "no"] = Field(
        description="Relevance or grounding evaluation result: 'yes' or 'no'"
    )


# ── Graph Builder ─────────────────────────────────────────────

class TwinRAGGraph:
    def __init__(self):
        self.vector_store = get_vector_store()

    def _get_llm(self):
        return get_llm(temperature=0.1)

    # ── Nodes ─────────────────────────────────────────────────

    def retrieve(self, state: TwinRAGState) -> Dict[str, Any]:
        """Fetch chunks strictly scoped by twin_id and allowed visibilities."""
        question = state["question"]
        twin_id = state["twin_id"]
        visibilities = state.get("allowed_visibilities") or ["public"]

        results = self.vector_store.search(
            twin_id=twin_id,
            query_text=question,
            allowed_visibilities=visibilities,
            top_k=5,
        )

        top_similarity = results[0]["similarity"] if results else 0.0

        return {
            "documents": results,
            "confidence_score": top_similarity,
        }

    def grade_documents(self, state: TwinRAGState) -> Dict[str, Any]:
        """Filter out irrelevant chunks."""
        docs = state.get("documents", [])
        question = state["question"]

        if not docs:
            return {"documents": []}

        # Fast heuristic: if similarity score is below minimum threshold, drop it
        filtered = [d for d in docs if d.get("similarity", 0.0) >= 0.25]

        # If LLM key is configured, perform LLM grading
        try:
            llm = self._get_llm()
            structured_grader = llm.with_structured_output(GradeDecision)
            chain = DOC_GRADER_PROMPT | structured_grader

            llm_graded = []
            for doc in filtered:
                res = chain.invoke({"document": doc["content"], "question": question})
                if res.binary_score == "yes":
                    llm_graded.append(doc)

            # Use LLM-graded if at least one passed; else fallback to similarity filtered
            if llm_graded:
                filtered = llm_graded
        except Exception:
            # Fallback gracefully if Groq API is not reachable or offline
            pass

        return {"documents": filtered}

    def generate(self, state: TwinRAGState) -> Dict[str, Any]:
        """Generate response as the persona using retrieved context."""
        question = state.get("original_question") or state["question"]
        docs = state.get("documents", [])
        twin_name = state.get("twin_name", "Twin")
        persona_style = state.get("persona_prompt") or "Be helpful, friendly, and precise."
        retries = state.get("retry_count", 0)

        if docs:
            context_texts = [f"[{i+1}] {d['content']}" for i, d in enumerate(docs)]
            context_str = "\n\n".join(context_texts)
            human_msg = "Context information:\n{context}\n\nVisitor Question: {question}\n\nPlease provide a grounded answer:"
        else:
            context_str = "No specific document chunks retrieved."
            human_msg = (
                "Visitor Question: {question}\n\n"
                "Instructions: Answer naturally using your persona details above if this is a greeting, introduction, or persona preference. "
                "If the visitor asks for specific external facts, credentials, dates, or documents not mentioned in your persona, "
                "decline politely stating you do not have that verified information in your records."
            )

        system_instruction = DEFAULT_TWIN_PERSONA.format(
            twin_name=twin_name,
            persona_prompt=persona_style,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_instruction),
            ("human", human_msg),
        ])

        try:
            llm = self._get_llm()
            chain = prompt | llm | StrOutputParser()
            generation = chain.invoke({"context": context_str, "question": question})
            
            # Classify decision
            lower_gen = generation.lower()
            if any(p in lower_gen for p in ["don't have", "do not have", "not recorded", "cannot verify"]):
                decision = "decline"
            else:
                decision = "answer"
        except Exception as e:
            generation = f"I am currently having trouble accessing my thinking model: {str(e)}"
            decision = "escalate"

        # Prepare source references
        sources = [
            {
                "chunk_id": d["chunk_id"],
                "similarity": d.get("similarity", 0.0),
                "snippet": d["content"][:160] + "...",
            }
            for d in docs
        ]

        return {
            "generation": generation,
            "policy_decision": decision,
            "sources": sources,
            "retry_count": retries + 1,
        }

    def transform_query(self, state: TwinRAGState) -> Dict[str, Any]:
        """Reformulate query to improve search recall."""
        question = state["question"]
        retries = state.get("retry_count", 0)

        try:
            llm = self._get_llm()
            chain = QUERY_REWRITE_PROMPT | llm | StrOutputParser()
            new_question = chain.invoke({"question": question})
        except Exception:
            new_question = question

        return {
            "question": new_question,
            "retry_count": retries + 1,
        }

    def abstain_or_escalate(self, state: TwinRAGState) -> Dict[str, Any]:
        """Polite abstention when context is absent or ungrounded."""
        twin_name = state.get("twin_name", "I")
        question = state["question"]

        msg = (
            f"I don't have enough verified information about that right now. "
            f"I have noted your question (\"{question}\") and will let {twin_name} know so they can follow up."
        )

        return {
            "generation": msg,
            "policy_decision": "decline",
            "sources": [],
        }

    # ── Conditional Edges ─────────────────────────────────────

    def decide_retrieval_action(self, state: TwinRAGState) -> Literal["generate", "transform_query", "abstain"]:
        docs = state.get("documents", [])
        retries = state.get("retry_count", 0)

        if docs:
            return "generate"
        if retries < 1:
            return "transform_query"
        # If still no docs after 1 query reformulation, proceed to generate with persona fallback
        return "generate"

    def verify_groundedness(self, state: TwinRAGState) -> Literal["accept", "regenerate", "abstain"]:
        retries = state.get("retry_count", 0)
        docs = state.get("documents", [])
        generation = state.get("generation", "")

        if not docs:
            # When answering purely from persona or declining, accept the answer directly
            return "accept"
        if retries >= 3:
            return "accept"

        # Hallucination check against retrieved document facts
        try:
            llm = self._get_llm()
            structured_grader = llm.with_structured_output(GradeDecision)
            context_str = "\n\n".join([d["content"] for d in docs])
            chain = HALLUCINATION_GRADER_PROMPT | structured_grader
            res = chain.invoke({"context": context_str, "generation": generation})

            if res.binary_score == "yes":
                return "accept"
            else:
                return "regenerate"
        except Exception:
            return "accept"

    # ── Build & Compile ───────────────────────────────────────

    def build(self):
        workflow = StateGraph(TwinRAGState)

        # Nodes
        workflow.add_node("retrieve", self.retrieve)
        workflow.add_node("grade_documents", self.grade_documents)
        workflow.add_node("generate", self.generate)
        workflow.add_node("transform_query", self.transform_query)
        workflow.add_node("abstain", self.abstain_or_escalate)

        # Edges
        workflow.add_edge(START, "retrieve")
        workflow.add_edge("retrieve", "grade_documents")
        workflow.add_edge("transform_query", "retrieve")
        workflow.add_edge("abstain", END)

        workflow.add_conditional_edges(
            "grade_documents",
            self.decide_retrieval_action,
            {
                "generate": "generate",
                "transform_query": "transform_query",
                "abstain": "abstain",
            },
        )

        workflow.add_conditional_edges(
            "generate",
            self.verify_groundedness,
            {
                "accept": END,
                "regenerate": "generate",
                "abstain": "abstain",
            },
        )

        return workflow.compile()


_graph_instance = None


def get_rag_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = TwinRAGGraph().build()
    return _graph_instance

