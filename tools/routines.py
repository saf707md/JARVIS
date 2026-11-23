"""Routines: named lists of safe actions that JARVIS can run with one command.

A routine step is a short line of text:
    app: vs code
    site: youtube
    folder: notes
    search: youtube | lofi music
Only these four kinds exist, and every step still goes through the security layer.
"""
import json
import logging
import re
from contextlib import closing

from memory.database import get_connection

logger = logging.getLogger("jarvis")

MAX_STEPS = 10

# step kind -> the tool it runs
STEP_TOOLS = {
    "app": "open_application",
    "site": "open_website",
    "folder": "open_folder",
    "search": "search_on_site",
}
TOOL_KINDS = {tool: kind for kind, tool in STEP_TOOLS.items()}


def parse_step(step: str):
    """Turn 'app: vs code' into ('open_application', {'app_name': 'vs code'}). Returns None if invalid."""
    match = re.match(r"^\s*(app|site|folder|search)\s*:\s*(.+?)\s*$", step, re.IGNORECASE)
    if not match:
        return None
    kind, value = match.group(1).lower(), match.group(2)
    if kind == "app":
        return "open_application", {"app_name": value}
    if kind == "site":
        return "open_website", {"site": value}
    if kind == "folder":
        return "open_folder", {"folder_name": value}
    site, _, query = value.partition("|")
    if not site.strip() or not query.strip():
        return None
    return "search_on_site", {"site": site.strip(), "query": query.strip()}


def to_step(tool: str, args: dict):
    """The reverse of parse_step. Returns None for tools that cannot be routine steps."""
    kind = TOOL_KINDS.get(tool)
    if kind == "app":
        return f"app: {args.get('app_name', '').strip().lower()}"
    if kind == "site":
        return f"site: {args.get('site', '').strip().lower()}"
    if kind == "folder":
        return f"folder: {args.get('folder_name', '').strip().lower()}"
    if kind == "search":
        return f"search: {args.get('site', '').strip().lower()} | {args.get('query', '').strip()}"
    return None


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\broutine\b", "", name.lower())).strip()


def _validate(steps):
    from tools.applications import APPLICATIONS

    cleaned = []
    for step in steps:
        parsed = parse_step(step)
        if parsed is None:
            return None, f"'{step}' is not a valid step. Use app:, site:, folder: or search: site | words."
        tool, args = parsed
        if tool == "open_application" and args["app_name"].lower() not in APPLICATIONS:
            return None, f"'{args['app_name']}' is not an approved application."
        cleaned.append(to_step(tool, args))
    return cleaned, ""


def save_routine(name: str, steps: list) -> str:
    """Store a routine (shared by the AI tool and by accepted suggestions)."""
    name = _clean_name(name)
    if not name:
        return "Error: the routine needs a name."
    if not steps:
        return "Error: a routine needs at least one step."
    if len(steps) > MAX_STEPS:
        return f"Error: a routine can have at most {MAX_STEPS} steps."
    cleaned, problem = _validate(steps)
    if cleaned is None:
        return "Error: " + problem

    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT INTO routines (name, steps) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET steps = excluded.steps",
            (name, json.dumps(cleaned)),
        )
        connection.commit()
    logger.info("[ROUTINE] Saved '%s' with %d steps", name, len(cleaned))
    return f"Saved the '{name}' routine: " + "; ".join(cleaned)


def get_routine(name: str):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT steps FROM routines WHERE name = ?", (_clean_name(name),)
        ).fetchone()
    return json.loads(row["steps"]) if row else None


def all_routines():
    """Return {name: [steps]} for every saved routine."""
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT name, steps FROM routines ORDER BY name").fetchall()
    return {row["name"]: json.loads(row["steps"]) for row in rows}


# ---------------- tools the AI can call ----------------

def create_routine(name: str, steps: list[str]) -> str:
    """Create or replace a named routine: a list of actions JARVIS runs together.

    Use this when the user describes a routine, for example "make a study routine that
    opens VS Code, my notes folder and lofi music on YouTube".

    Args:
        name: Short routine name, for example "study" or "morning".
        steps: Each step is one line: "app: <approved app>", "site: <site>",
            "folder: <approved folder>", or "search: <site> | <words>".
            Example: ["app: vs code", "folder: notes", "search: youtube | lofi music"].
    """
    return save_routine(name, steps)


def save_recent_actions_as_routine(name: str, minutes: int = 30) -> str:
    """Save the apps, websites, folders and searches the user opened recently as a routine.

    Use this when the user says "save what I just did as a routine" or "remember this as my X routine".

    Args:
        name: Short routine name, for example "study".
        minutes: How far back to look, default 30 minutes.
    """
    minutes = max(1, min(int(minutes), 240))
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT tool, args FROM action_log "
            "WHERE created_at >= datetime('now', 'localtime', ?) AND undone = 0 ORDER BY id",
            (f"-{minutes} minutes",),
        ).fetchall()

    steps = []
    for row in rows:
        step = to_step(row["tool"], json.loads(row["args"]))
        if step and step not in steps:
            steps.append(step)
    if not steps:
        return f"Error: I haven't opened any apps, sites or folders in the last {minutes} minutes."
    return save_routine(name, steps[:MAX_STEPS])


def run_routine(name: str) -> str:
    """Run a saved routine, performing each of its steps in order.

    Args:
        name: The routine name, for example "study".
    """
    steps = get_routine(name)
    if steps is None:
        names = ", ".join(all_routines()) or "none yet"
        return f"Error: there is no routine called '{name}'. Saved routines: {names}."

    from core import actions
    from tools.registry import run_tool  # imported here to avoid a circular import

    results = []
    with actions.inside_routine():
        for step in steps:
            parsed = parse_step(step)
            if parsed is None:
                results.append(f"{step}: skipped (invalid)")
                continue
            tool, args = parsed
            results.append(f"{step}: {run_tool(tool, args)}")
    logger.info("[ROUTINE] Ran '%s'", _clean_name(name))
    return f"Ran the '{_clean_name(name)}' routine:\n" + "\n".join(results)


def list_routines() -> str:
    """List all saved routines and their steps."""
    routines = all_routines()
    if not routines:
        return "There are no saved routines yet."
    return "\n".join(f"- {name}: " + "; ".join(steps) for name, steps in routines.items())


def delete_routine(name: str) -> str:
    """Delete a saved routine. The user must confirm first.

    Args:
        name: The routine name.
    """
    with closing(get_connection()) as connection:
        deleted = connection.execute(
            "DELETE FROM routines WHERE name = ?", (_clean_name(name),)
        ).rowcount
        connection.commit()
    if not deleted:
        return f"There is no routine called '{name}'."
    return f"Deleted the '{_clean_name(name)}' routine."
