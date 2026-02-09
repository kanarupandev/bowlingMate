from typing import List
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Hardcoded knowledge base for the MVP
DOCS = [
    # English
    {"content": "Run-up: Keep it rhythmic and consistent. Build momentum gradually.", "metadata": {"lang": "en", "topic": "run_up"}},
    {"content": "Loading/Coil: Turn your body side-on. Front arm should be high.", "metadata": {"lang": "en", "topic": "loading"}},
    {"content": "Release: Keep your arm straight. Release at the highest point. Snap your wrist.", "metadata": {"lang": "en", "topic": "release"}},
    {"content": "Follow-through: Follow your arm across your body. Don't stop abruptly.", "metadata": {"lang": "en", "topic": "follow_through"}},
    {"content": "Head/Eyes: Fix your eyes on the target. Don't drop your head.", "metadata": {"lang": "en", "topic": "head_eyes"}},

    # Tamil (Transliterated/Translated approximations for demo)
    {"content": "ஓடுவழி (Run-up): சீரான வேகத்தில் ஓடி வரவும். உடலின் வேகத்தை அதிகரிக்கவும்.", "metadata": {"lang": "ta", "topic": "run_up"}},
    {"content": "சுருள் (Loading): உடலை பக்கவாட்டில் திருப்பவும். முன் கையை உயர்த்தி பிடிக்கவும்.", "metadata": {"lang": "ta", "topic": "loading"}},
    {"content": "வெளியீடு (Release): கையை நேராக வைக்கவும். உயரமான இடத்தில் பந்தை வெளியிடவும். மணிக்கட்டை சுழற்றவும்.", "metadata": {"lang": "ta", "topic": "release"}},
    {"content": "தொடர் இயக்கம் (Follow-through): வீசிய கையை உடலின் குறுக்கே கொண்டு செல்லவும். திடீரென நிற்க வேண்டாம்.", "metadata": {"lang": "ta", "topic": "follow_through"}},
    {"content": "தலை/கண்கள் (Head/Eyes): இலக்கை உற்று நோக்கவும். தலையை கீழே சாய்க்க வேண்டாம்.", "metadata": {"lang": "ta", "topic": "head_eyes"}},
]

import logging

logger = logging.getLogger("wellBowled.rag")

_vector_store = None

def init_rag_index():
    global _vector_store
    if _vector_store is not None:
        return

    logger.debug("Initializing RAG Index...")
    documents = [Document(page_content=d["content"], metadata=d["metadata"]) for d in DOCS]
    
    # Using a placeholder implementation if no API key is present during init (for testing)
    # in real usage, GoogleGenerativeAIEmbeddings expects GOOGLE_API_KEY env var
    from config import get_settings
    settings = get_settings()
    if not settings.ENABLE_RAG:
        logger.warning("RAG DISABLED by config. Skipping index init.")
        return

    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY
        )
        _vector_store = FAISS.from_documents(documents, embeddings)
        logger.info(f"RAG Index initialized with {len(documents)} documents.")
    except Exception as e:
        logger.warning(f"RAG initialization failed (likely no API key): {e}")
        _vector_store = None

def retrieve_knowledge(query: str, language: str = "en", k: int = 3) -> str:
    logger.debug(f"Retrieving knowledge for query: '{query}' [lang={language}]")
    if _vector_store is None:
        logger.warning("Vector store is not initialized. Returning empty.")
        return ""
    
    # Filter by language if possible
    # FAISS in langchain doesn't support metadata filtering easily in the search method 
    # without specific vector store kwargs, or post-filtering. 
    # For MVP, we'll just search and let the LLM filter, or retrieve more docs.
    results = _vector_store.similarity_search(query, k=k*2) # over-fetch
    
    filtered = [doc.page_content for doc in results if doc.metadata.get("lang") == language]
    logger.debug(f"Found {len(results)} raw matches, filtered to {len(filtered)} by language.")
    
    return "\n".join(filtered[:k])
