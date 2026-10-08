import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("jarvis")

PROJECT_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_DIR / "knowledge"
NOTES_DIR = PROJECT_DIR / "notes"
HOME = Path.home()

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py"}
SKIP_DIRS = {"venv", ".venv", ".git", "__pycache__", "node_modules", "AppData", "site-packages"}
# Files with these words in their name are never listed or read
BLOCKED_WORDS = ("password", "passwd", "secret", "credential", ".env", "private_key", "id_rsa")


def _search_roots():
    """Folders JARVIS is allowed to look in (only the ones that exist)."""
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    candidates = [
        KNOWLEDGE_DIR,
        NOTES_DIR,
        HOME / "Documents",
        HOME / "Desktop",
        HOME / "Downloads",
        HOME / "OneDrive" / "Documents",
        HOME / "OneDrive" / "Desktop",
    ]
    return [path.resolve() for path in candidates if path.exists()]


def _is_blocked(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in BLOCKED_WORDS)


def _is_allowed(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in _search_roots())


def _normalize(text: str) -> str:
    return re.sub(r"[\s_\-\\/]+", " ", text.lower())


def search_files(name_query: str) -> str:
    """Find files by name in the user's Documents, Desktop, Downloads and JARVIS knowledge folders.

    Args:
        name_query: Words from the file name or folder, for example "cryptography module 2".
    """
    words = [word for word in _normalize(name_query).split() if word]
    if not words:
        return "Error: please tell me part of the file name."

    found = []
    visited = 0
    for root in _search_roots():
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                visited += 1
                if visited > 60000 or len(found) >= 10:
                    break
                if _is_blocked(name):
                    continue
                relative = str(Path(folder, name).relative_to(root))
                haystack = _normalize(relative)
                if all(word in haystack for word in words):
                    found.append(str(Path(folder, name)))
            if visited > 60000 or len(found) >= 10:
                break
        if visited > 60000 or len(found) >= 10:
            break

    if not found:
        return f"No files found matching '{name_query}'."
    return "Found these files:\n" + "\n".join(found)


def read_text_file(path: str) -> str:
    """Read the contents of a plain text file (.txt, .md, .csv, .json, .py).

    Args:
        path: The full path of the file, as returned by search_files.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return "Error: that is not a valid file path."

    if _is_blocked(resolved.name):
        return "Error: that file is restricted."
    if not _is_allowed(resolved):
        return "Error: I may only read files in your Documents, Desktop, Downloads, or JARVIS folders."
    if not resolved.is_file():
        return "Error: I couldn't find that file."
    if resolved.suffix.lower() not in TEXT_EXTENSIONS:
        return "Error: for now I can only read .txt, .md, .csv, .json and .py files."

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) > 8000:
        text = text[:8000] + "\n[...file truncated]"
    return text or "The file is empty."


def create_note(filename: str, content: str) -> str:
    """Create a new text note in JARVIS's notes folder. The user must confirm first.

    Args:
        filename: The note name, for example "revision plan" or "ideas.md".
        content: The text to write into the note.
    """
    name = Path(filename).name  # drop any folder parts for safety
    if not re.match(r"^[\w\- ]{1,60}(\.(txt|md))?$", name):
        return "Error: that is not a valid note name."
    if "." not in name:
        name += ".txt"

    NOTES_DIR.mkdir(exist_ok=True)
    target = NOTES_DIR / name
    if target.exists():
        return "Error: a note with that name already exists, so I did not overwrite it."

    target.write_text(content, encoding="utf-8")
    logger.info("[TOOL] Note created: %s", target)
    return f"Note created: {target}"


def open_folder(folder_name: str) -> str:
    """Open an approved folder in File Explorer.

    Approved folders: documents, downloads, desktop, project (the JARVIS folder), knowledge, notes.

    Args:
        folder_name: One of the approved folder names.
    """
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    NOTES_DIR.mkdir(exist_ok=True)

    def first_existing(*paths):
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    folders = {
        "documents": first_existing(HOME / "Documents", HOME / "OneDrive" / "Documents"),
        "downloads": HOME / "Downloads",
        "desktop": first_existing(HOME / "Desktop", HOME / "OneDrive" / "Desktop"),
        "project": PROJECT_DIR,
        "jarvis": PROJECT_DIR,
        "knowledge": KNOWLEDGE_DIR,
        "notes": NOTES_DIR,
    }
    key = folder_name.strip().lower()
    target = folders.get(key)
    if target is None:
        return f"Error: I can only open these folders: {', '.join(sorted(folders))}."
    if not target.exists():
        return f"Error: the {key} folder doesn't exist."

    os.startfile(str(target))
    return f"Opened the {key} folder."
