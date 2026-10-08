import logging
import re

from rag.document_loader import SUPPORTED, load_document
from rag.ingest import ingest_folder
from rag.vector_store import KNOWLEDGE_DIR, get_collection

logger = logging.getLogger("jarvis")

MAX_DOCUMENT_CHARS = 12000


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def search_documents(query: str) -> str:
    """Search the user's own documents (lecture notes, slides, PDFs in the knowledge folder).

    Use this whenever the user asks about their notes, modules, courses, subjects,
    or says "from my notes" / "from my documents". Answer using only the passages returned.

    Args:
        query: The topic or question to look for, for example "Playfair cipher rules".
    """
    try:
        collection = get_collection()
        if collection.count() == 0:
            return "The knowledge base is empty. The documents need to be indexed first."
        results = collection.query(query_texts=[query], n_results=5)
    except Exception as error:
        logger.error("[RAG] Search failed: %s", error)
        return "Error: I couldn't search the documents right now."

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    if not documents:
        return "No relevant passages were found in the documents."

    logger.info("[RAG] Retrieved %d passages", len(documents))
    parts = [
        f"[Source: {meta['source']}, {meta['location']}]\n{text}"
        for text, meta in zip(documents, metadatas)
    ]
    return "\n\n".join(parts)


def read_knowledge_document(name: str) -> str:
    """Read an entire document from the user's knowledge folder, sampled across all its parts.

    Use this when the user wants an overview, the important topics, a summary,
    or a revision plan for a whole document or module.

    Args:
        name: Words from the document's file name, for example "cryptography module 2".
    """
    words = _normalize(name).split()
    if not words:
        return "Error: please tell me which document."

    matches = [
        path for path in KNOWLEDGE_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED
        and all(word in _normalize(path.relative_to(KNOWLEDGE_DIR).as_posix()) for word in words)
    ]
    if not matches:
        return f"No document in the knowledge folder matches '{name}'."

    path = matches[0]
    sections = load_document(path)
    if not sections:
        return f"I couldn't read any text from {path.name}."

    # Take a slice of every section so the whole document is covered
    budget = max(200, MAX_DOCUMENT_CHARS // len(sections))
    pieces = [f"[{location}]\n{text[:budget]}" for location, text in sections]
    content = "\n\n".join(pieces)[:MAX_DOCUMENT_CHARS]

    logger.info("[RAG] Read document %s (%d sections)", path.name, len(sections))
    note = ""
    if len(matches) > 1:
        others = ", ".join(p.name for p in matches[1:4])
        note = f"\n(Other matching files not read: {others})"
    return f"Document: {path.name}\n\n{content}{note}"


def reindex_documents() -> str:
    """Re-scan the knowledge folder and update the searchable index.

    Use this after the user says they added or changed documents.
    """
    try:
        return ingest_folder()
    except Exception as error:
        logger.error("[RAG] Indexing failed: %s", error)
        return "Error: I couldn't index the documents right now."
