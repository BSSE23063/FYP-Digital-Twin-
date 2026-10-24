"""
Text chunking and embedding generation using FastEmbed and LangChain.

The model and splitter are built lazily (not at import time): importing this
module should never require the embedding model to already be downloaded, and
a test can override settings before the first real call.
"""
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from fastembed import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> TextEmbedding:
    # FastEmbed downloads and caches this model locally on first use.
    return TextEmbedding(model_name=settings.EMBEDDING_MODEL)


def get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
        # Attaches metadata["start_index"] to each produced Document — the
        # splitter computes this itself while walking the text, so it's exact,
        # not a best-effort post-hoc string search for where the chunk came from.
        add_start_index=True,
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embeds in fixed-size batches (INGEST_BATCH_SIZE) so memory use stays
    flat regardless of how many chunks a document produces — no GPU here
    (see CLAUDE.md §9.2), so a single huge batch is a real way to stall."""
    if not texts:
        return []
    embedder = get_embedder()
    vectors: List[List[float]] = []
    batch_size = settings.INGEST_BATCH_SIZE
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors.extend(vector.tolist() for vector in embedder.embed(batch))
    return vectors


def chunk_text(text: str) -> List[Tuple[str, int, int]]:
    """Splits text into (chunk_text, char_start, char_end) triples."""
    docs = get_splitter().create_documents([text])
    return [
        (doc.page_content, doc.metadata["start_index"], doc.metadata["start_index"] + len(doc.page_content))
        for doc in docs
    ]


def process_document(text: str) -> Dict[str, Any]:
    """
    Splits raw text into chunks (with exact char offsets) and embeds them.
    Deliberately knows nothing about twin_id/source_id/visibility — that
    tenant/knowledge metadata is attached by the caller when it upserts
    (backend/vectordb/operations.py), keeping this module a pure chunk+embed
    step reusable for memory text too.
    """
    triples = chunk_text(text)
    chunks = [t[0] for t in triples]
    offsets = [(t[1], t[2]) for t in triples]
    return {"chunks": chunks, "offsets": offsets, "embeddings": embed_texts(chunks)}
