from pathlib import Path

import chromadb
from chromadb.config import Settings

PROJECT_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_DIR / "knowledge"
CHROMA_DIR = PROJECT_DIR / "data" / "chroma"
COLLECTION_NAME = "jarvis_knowledge"

_client = None


def get_collection():
    """Open (or create) the vector collection stored on disk."""
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False)
        )
    # No embedding function given, so Chroma uses its built-in local model
    return _client.get_or_create_collection(COLLECTION_NAME)
