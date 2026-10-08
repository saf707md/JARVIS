import logging
from pathlib import Path

logger = logging.getLogger("jarvis")

SUPPORTED = {".pdf", ".pptx", ".docx", ".txt", ".md"}


def _read_pdf(path):
    from pypdf import PdfReader

    sections = []
    for number, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            sections.append((f"page {number}", text))
    return sections


def _read_pptx(path):
    from pptx import Presentation

    sections = []
    for number, slide in enumerate(Presentation(str(path)).slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
        if slide.has_notes_slide:
            parts.append(slide.notes_slide.notes_text_frame.text)
        text = "\n".join(part for part in parts if part.strip())
        if text.strip():
            sections.append((f"slide {number}", text))
    return sections


def _read_docx(path):
    from docx import Document

    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    text = "\n".join(part for part in parts if part.strip())
    return [("document", text)] if text.strip() else []


def _read_text(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return [("text", text)] if text.strip() else []


def load_document(path):
    """Extract text from a file. Returns a list of (location, text) pairs.

    Returns an empty list if the file can't be read, so one bad file never crashes JARVIS.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf(path)
        if suffix == ".pptx":
            return _read_pptx(path)
        if suffix == ".docx":
            return _read_docx(path)
        if suffix in (".txt", ".md"):
            return _read_text(path)
    except Exception as error:
        logger.error("[RAG] Could not read %s: %s", path.name, error)
    return []
