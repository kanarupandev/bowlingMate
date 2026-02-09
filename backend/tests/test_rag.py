from rag import init_rag_index, retrieve_knowledge

def test_rag_initialization_and_retrieval(monkeypatch):
    # Mock FAISS and Embeddings to avoid real API calls or issues
    # But since we have a 'try-except' block in init_rag_index, we can test the fallback or success.

    # Setup: Ensure _vector_store starts None
    import rag
    rag._vector_store = None
    
    # Case 1: Without API Key (should fail gracefully/print warning and stay None)
    init_rag_index()
    # If no key, it might fail.
    
    # Checking behavior: retrieve_knowledge should return empty string if store is None
    assert retrieve_knowledge("test") == ""

    # Mocking the vector store for a "success" case test
    class MockStore:
        def similarity_search(self, query, k):
            from langchain_core.documents import Document
            return [
                Document(page_content="Tip 1", metadata={"lang": "en"}),
                Document(page_content="Tip 2", metadata={"lang": "ta"}),
                Document(page_content="Tip 3", metadata={"lang": "en"})
            ]

    rag._vector_store = MockStore()
    
    # Test Language Filtering
    results_en = retrieve_knowledge("query", language="en", k=2)
    assert "Tip 1" in results_en
    assert "Tip 3" in results_en
    assert "Tip 2" not in results_en
    
    results_ta = retrieve_knowledge("query", language="ta", k=1)
    assert "Tip 2" in results_ta
