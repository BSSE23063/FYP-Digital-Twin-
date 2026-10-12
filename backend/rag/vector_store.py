"""
ChromaDB Vector Store wrapper with strict tenant isolation.
"""

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from backend.config import settings


class VectorStore:
    """
    Persistent ChromaDB vector store wrapper.
    Ensures every query and insert respects twin_id tenant boundary.
    """

    def __init__(self, storage_path: Optional[str] = None, collection_name: Optional[str] = None):
        self.storage_path = storage_path or settings.CHROMA_PERSIST_DIR
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME

        self.client = chromadb.PersistentClient(path=self.storage_path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(
        self,
        chunk_ids: List[str],
        twin_id: str,
        texts: List[str],
        doc_id: str,
        source_type: str = "upload",
        visibility: str = "public",
        chunk_indices: Optional[List[int]] = None,
        heading_paths: Optional[List[Optional[str]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ):
        """
        Upsert document chunks with strict metadata for tenant isolation.
        """
        if not chunk_ids:
            return

        metadatas: List[Dict[str, Any]] = []
        for idx, _ in enumerate(chunk_ids):
            chunk_idx = chunk_indices[idx] if chunk_indices else idx
            h_path = heading_paths[idx] if heading_paths and idx < len(heading_paths) else ""
            metadatas.append({
                "twin_id": str(twin_id),
                "doc_id": str(doc_id),
                "source_type": str(source_type),
                "visibility": str(visibility),
                "chunk_index": int(chunk_idx),
                "heading_path": str(h_path or ""),
            })

        upsert_kwargs: Dict[str, Any] = {
            "ids": chunk_ids,
            "documents": texts,
            "metadatas": metadatas,
        }
        if embeddings:
            upsert_kwargs["embeddings"] = embeddings

        self.collection.upsert(**upsert_kwargs)

    def search(
        self,
        twin_id: str,
        query_text: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        allowed_visibilities: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks strictly filtered by twin_id and allowed visibilities.
        """
        visibilities = allowed_visibilities or ["public"]

        # ChromaDB where filter
        if len(visibilities) == 1:
            where_filter = {
                "$and": [
                    {"twin_id": {"$eq": str(twin_id)}},
                    {"visibility": {"$eq": visibilities[0]}},
                ]
            }
        else:
            where_filter = {
                "$and": [
                    {"twin_id": {"$eq": str(twin_id)}},
                    {"visibility": {"$in": visibilities}},
                ]
            }

        query_kwargs: Dict[str, Any] = {
            "n_results": top_k,
            "where": where_filter,
        }

        if query_embedding:
            query_kwargs["query_embeddings"] = [query_embedding]
        elif query_text:
            query_kwargs["query_texts"] = [query_text]
        else:
            raise ValueError("Either query_text or query_embedding must be provided.")

        results = self.collection.query(**query_kwargs)

        formatted: List[Dict[str, Any]] = []
        if results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)
            metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)

            for c_id, text, dist, meta in zip(ids, docs, distances, metadatas):
                # Cosine distance to similarity: 1.0 - distance
                similarity = 1.0 - float(dist)
                formatted.append({
                    "chunk_id": c_id,
                    "content": text,
                    "similarity": round(similarity, 4),
                    "metadata": meta,
                })

        return formatted

    def delete_by_document(self, twin_id: str, doc_id: str):
        """Remove all chunks belonging to a document under a specific twin."""
        self.collection.delete(
            where={
                "$and": [
                    {"twin_id": {"$eq": str(twin_id)}},
                    {"doc_id": {"$eq": str(doc_id)}},
                ]
            }
        )

    def delete_by_twin(self, twin_id: str):
        """Remove all knowledge belonging to a twin."""
        self.collection.delete(
            where={"twin_id": {"$eq": str(twin_id)}}
        )


def get_vector_store() -> VectorStore:
    return VectorStore()