import logging

from security.permissions import check_permission
from tools.applications import open_application
from tools.browser import open_website
from tools.calculator import calculate
from tools.filesystem import create_note, open_folder, read_text_file, search_files
from memory.memory_manager import recall_memories, remember_fact
from rag.retriever import read_knowledge_document, reindex_documents, search_documents
from tools.screenshot import take_screenshot
from tools.system import get_current_datetime, get_system_info
from tools.weather import get_weather
from tools.web_search import news_search, web_search

logger = logging.getLogger("jarvis")

# name -> (function, permission level). Add new tools here later.
_TOOLS = {
    "calculate": (calculate, 1),
    "open_website": (open_website, 1),
    "open_application": (open_application, 1),
    "get_system_info": (get_system_info, 1),
    "get_current_datetime": (get_current_datetime, 1),
    "get_weather": (get_weather, 1),
    "web_search": (web_search, 1),
    "news_search": (news_search, 1),
    "search_files": (search_files, 1),
    "read_text_file": (read_text_file, 1),
    "open_folder": (open_folder, 1),
    "search_documents": (search_documents, 1),
    "read_knowledge_document": (read_knowledge_document, 1),
    "reindex_documents": (reindex_documents, 1),
    "remember_fact": (remember_fact, 1),
    "recall_memories": (recall_memories, 1),
    "take_screenshot": (take_screenshot, 1),
    "create_note": (create_note, 2),  # Level 2: needs confirmation
}

# How to describe Level 2 actions to the user when asking permission
_DESCRIPTIONS = {
    "create_note": lambda a: f"create a note called '{a.get('filename', 'untitled')}'",
}


def _describe(name: str, args: dict) -> str:
    maker = _DESCRIPTIONS.get(name)
    return maker(args) if maker else f"perform the action '{name}'"


def get_tool_functions():
    """The functions the AI is allowed to ask for."""
    return [function for function, _level in _TOOLS.values()]


def run_tool(name: str, args: dict, confirm=None) -> str:
    """Run an approved tool after the security check. Never raises.

    confirm: a function that takes a description and returns True/False.
    """
    if name not in _TOOLS:
        logger.warning("[SECURITY] Unknown tool requested: %s", name)
        return "Error: that tool does not exist."

    function, level = _TOOLS[name]
    decision = check_permission(name, level)
    logger.info("[SECURITY] %s -> level %s -> %s", name, level, decision)

    if decision == "deny":
        return "Error: this action is restricted and cannot be performed."

    if decision == "confirm":
        description = _describe(name, args)
        logger.info("[SECURITY] Asking the user to confirm: %s", description)
        if confirm is None or not confirm(description):
            logger.info("[SECURITY] User declined")
            return "The user declined, so the action was not performed."
        logger.info("[SECURITY] User approved")

    try:
        logger.info("[TOOL] Executing %s", name)
        return function(**args)
    except Exception as error:
        logger.error("[TOOL] %s failed: %s", name, error)
        return f"Error: the tool failed ({error})."



