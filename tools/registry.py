import logging

from security.permissions import check_permission
from tools.applications import open_application
from tools.browser import open_website
from tools.calculator import calculate
from tools.filesystem import create_note, open_folder, read_text_file, search_files
from memory.memory_manager import describe_forget, forget_memory, recall_memories, remember_fact
from rag.retriever import read_knowledge_document, reindex_documents, search_documents
from tools.screenshot import take_screenshot
from tools.site_search import search_on_site
from tools.vision import analyze_screen
from tools.system import get_current_datetime, get_system_info
from tools.weather import get_weather
from tools.routines import (
    create_routine, delete_routine, list_routines, run_routine, save_recent_actions_as_routine,
)
from core import actions
from core.actions import describe_plan, describe_undo, propose_plan, undo_last_action
from core.suggestions import suggest_routines
from tools.reminders import cancel_reminder, describe_cancel, list_reminders, set_reminder
from tools.web_search import news_search, web_search

logger = logging.getLogger("jarvis")

# name -> (function, permission level). Add new tools here later.
_TOOLS = {
    "calculate": (calculate, 1),
    "open_website": (open_website, 1),
    "search_on_site": (search_on_site, 1),
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
    "analyze_screen": (analyze_screen, 2),
    "forget_memory": (forget_memory, 2),
    "create_note": (create_note, 2),  # Level 2: needs confirmation
    # Routines and habits
    "create_routine": (create_routine, 1),
    "save_recent_actions_as_routine": (save_recent_actions_as_routine, 1),
    "run_routine": (run_routine, 1),
    "list_routines": (list_routines, 1),
    "suggest_routines": (suggest_routines, 1),
    "delete_routine": (delete_routine, 2),
    # Plan-and-approve and undo
    "propose_plan": (propose_plan, 2),
    "undo_last_action": (undo_last_action, 2),
    # Reminders
    "set_reminder": (set_reminder, 1),
    "list_reminders": (list_reminders, 1),
    "cancel_reminder": (cancel_reminder, 2),
}

# How to describe Level 2 actions to the user when asking permission
_DESCRIPTIONS = {
    "forget_memory": lambda a: describe_forget(a.get('keyword', '')),
    "analyze_screen": lambda a: f"take a screenshot of your screen and send it to Google Gemini to answer: '{a.get('question', '')}' (after you click Yes, you will have 4 seconds to bring the window you want me to see to the front)",
    "create_note": lambda a: f"create a note called '{a.get('filename', 'untitled')}'",
    "delete_routine": lambda a: f"delete the '{a.get('name', '')}' routine",
    "propose_plan": describe_plan,
    "undo_last_action": lambda a: describe_undo(),
    "cancel_reminder": lambda a: describe_cancel(a.get("keyword", "")),
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
        context = actions.before(name, args)
        result = function(**args)
        actions.after(name, args, result, context)  # for undo and habit suggestions
        return result
    except Exception as error:
        logger.error("[TOOL] %s failed: %s", name, error)
        return f"Error: the tool failed ({error})."






