from backend.rag.vector_store import VectorStore

if __name__ == "__main__":
    print("Initializing ChromaDB VectorStore...")
    store = VectorStore()

    print("Adding sample chunk...")
    store.add_chunk(
        chunk_id="chunk_1",
        twin_id="twin_A",
        text="Sample text about AI twins and digital avatars.",
        doc_id="cv.pdf"
    )

    print("Searching knowledge base...")
    res = store.search_twin_knowledge("twin_A", "AI twins")
    
    print("\n--- Search Results ---")
    print(res)