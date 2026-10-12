"""
Groq LLM Client initialization using LangChain ChatGroq.
"""

from typing import Optional
from backend.config import settings


def get_llm(
    temperature: float = 0.0,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """
    Returns an initialized ChatGroq LLM instance.
    """
    from langchain_groq import ChatGroq

    key = api_key or settings.GROQ_API_KEY
    model = model_name or settings.GROQ_MODEL

    return ChatGroq(
        model=model,
        temperature=temperature,
        groq_api_key=key if key else "dummy_key_for_offline_init",
    )

