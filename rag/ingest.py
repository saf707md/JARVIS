import logging

from rag.chunking import chunk_text
from rag.document_loader import SUPPORTED, load_document
from rag.vector_store import KNOWLEDGE_DIR, get_collection

logger = logging.getLogger("jarvis")


def ingest_folder() -> str:
    """Read every supported file in the knowledge folder and store it in the vector database."""
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    collection = get_collection()
    files = [p for p in KNOWLEDGE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED]

    total_chunks = 0
    indexed_files = 0
    for path in files:
        source = path.relative_to(KNOWLEDGE_DIR).as_posix()
        sections = load_document(path)
        if not sections:
            logger.warning("[RAG] No readable text in %s", source)
            continue

        ids, documents, metadatas = [], [], []
        for location, text in sections:
            for number, chunk in enumerate(chunk_text(text)):
                ids.append(f"{source}::{location}::{number}")
                documents.append(chunk)
                metadatas.append({"source": source, "location": location})
        if not documents:
            continue

        # Remove old chunks of this file first, so re-running never duplicates
        collection.delete(where={"source": source})
        for start in range(0, len(documents), 100):
            collection.upsert(
                ids=ids[start:start + 100],
                documents=documents[start:start + 100],
                metadatas=metadatas[start:start + 100],
            )
        total_chunks += len(documents)
        indexed_files += 1
        logger.info("[RAG] Indexed %s (%d chunks)", source, len(documents))

    return f"Indexed {indexed_files} files, {total_chunks} chunks."


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Reading documents and building embeddings (first run downloads a small model)...")
    print(ingest_folder())
