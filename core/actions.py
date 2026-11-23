"""Action log: records what JARVIS did, so it can be undone, and what the user uses,
so JARVIS can spot habits and suggest routines.

Every user request is one "batch". "Undo that" reverses the latest batch that still has
something undoable: apps JARVIS opened are closed, notes it created are moved to a
recycle folder, and facts it remembered are removed. Websites and folders cannot be
closed reliably, so JARVIS says so instead of pretending.
"""
import json
import logging
import shutil
import subprocess
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

from memory.database import get_connection

logger = logging.getLogger("jarvis")

# Windows launch target -> process name, used to close apps JARVIS opened.
# File Explorer is left out on purpose: closing it would close the Windows desktop shell.
PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "msedge": "msedge.exe",
    "notepad": "notepad.exe",
    "calc": "CalculatorApp.exe",
    "mspaint": "mspaint.exe",
    "code": "Code.exe",
    "ms-settings:": "SystemSettings.exe",
}
USAGE_TOOLS = {"open_application", "open_website", "open_folder", "search_on_site"}
LOGGED_TOOLS = USAGE_TOOLS | {"create_note", "remember_fact", "run_routine", "set_reminder"}

_state = {"batch": uuid.uuid4().hex, "in_routine": 0}


def new_batch() -> None:
    """Called once per user request."""
    _state["batch"] = uuid.uuid4().hex


@contextmanager
def inside_routine():
    """Steps run by a routine are not counted as habits (the routine already covers them)."""
    _state["in_routine"] += 1
    try:
        yield
    finally:
        _state["in_routine"] -= 1


def _is_running(process_name: str) -> bool:
    try:
        import psutil
        wanted = process_name.lower()
        return any((p.info["name"] or "").lower() == wanted for p in psutil.process_iter(["name"]))
    except Exception:
        return True  # if unsure, assume it was running, so undo never closes the user's own window


def before(tool: str, args: dict) -> dict:
    """Collect facts needed for undo BEFORE the tool runs."""
    if tool == "open_application":
        from tools.applications import APPLICATIONS
        target = APPLICATIONS.get(str(args.get("app_name", "")).strip().lower())
        process = PROCESS_NAMES.get(target)
        if process:
            return {"process": process, "was_running": _is_running(process)}
    return {}


def _undo_info(tool: str, args: dict, result: str, context: dict):
    if tool == "open_application" and context.get("process") and not context.get("was_running"):
        return {"type": "close_app", "process": context["process"], "label": args.get("app_name")}
    if tool == "create_note" and result.startswith("Note created: "):
        return {"type": "recycle_note", "path": result[len("Note created: "):].strip()}
    if tool == "set_reminder" and result.startswith("Reminder #"):
        return {"type": "cancel_reminder", "id": int(result[len("Reminder #"):].split(" ", 1)[0]),
                "label": args.get("text", "")}
    if tool == "remember_fact" and result.startswith("Remembered: "):
        return {"type": "forget_fact", "fact": result[len("Remembered: "):].strip()}
    return None


def after(tool: str, args: dict, result: str, context: dict) -> None:
    """Record a successful action. Never raises."""
    if tool not in LOGGED_TOOLS or not isinstance(result, str):
        return
    if result.startswith("Error") or "declined" in result:
        return
    try:
        from tools.routines import to_step
        undo = _undo_info(tool, args, result, context)
        step = to_step(tool, args)
        with closing(get_connection()) as connection:
            connection.execute(
                "INSERT INTO action_log (batch, tool, args, undo) VALUES (?, ?, ?, ?)",
                (_state["batch"], tool, json.dumps(args), json.dumps(undo) if undo else None),
            )
            if step and not _state["in_routine"]:
                connection.execute("INSERT INTO usage_log (step) VALUES (?)", (step,))
            connection.commit()
    except Exception as error:
        logger.error("[UNDO] Could not record action: %s", error)


# ---------------- undo ----------------

def _last_batch():
    """Rows of the most recent batch that still has something not undone."""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT batch FROM action_log WHERE undone = 0 AND tool != 'run_routine' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        return connection.execute(
            "SELECT id, tool, args, undo FROM action_log "
            "WHERE batch = ? AND undone = 0 AND tool != 'run_routine' ORDER BY id DESC",
            (row["batch"],),
        ).fetchall()


def _label(row) -> str:
    from tools.routines import to_step
    args = json.loads(row["args"])
    return to_step(row["tool"], args) or f"{row['tool'].replace('_', ' ')}"


def describe_undo() -> str:
    """Shown in the permission dialog before undoing."""
    rows = _last_batch()
    if not rows:
        return "undo my last action (there is nothing to undo)"
    can = [_label(r) for r in rows if r["undo"]]
    cannot = [_label(r) for r in rows if not r["undo"]]
    text = "undo my last request"
    if can:
        text += ": " + "; ".join(can)
    if cannot:
        text += " (I can't close these, you'll need to: " + "; ".join(cannot) + ")"
    return text


def _perform(undo: dict) -> str:
    kind = undo["type"]
    if kind == "close_app":
        result = subprocess.run(
            ["taskkill", "/IM", undo["process"]],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return f"closed {undo['label']}" if result.returncode == 0 else f"couldn't close {undo['label']}"
    if kind == "recycle_note":
        path = Path(undo["path"])
        if not path.exists():
            return f"note {path.name} was already gone"
        recycle = path.parent / "_recycled"
        recycle.mkdir(exist_ok=True)
        shutil.move(str(path), str(recycle / path.name))
        return f"moved note {path.name} to notes/_recycled"
    if kind == "forget_fact":
        with closing(get_connection()) as connection:
            connection.execute("DELETE FROM memories WHERE fact = ?", (undo["fact"],))
            connection.commit()
        return f"forgot '{undo['fact']}'"
    if kind == "cancel_reminder":
        from tools.reminders import delete_reminder
        delete_reminder(undo["id"])
        return f"cancelled the reminder '{undo['label']}'"
    return "skipped an unknown action"


def undo_last_action() -> str:
    """Undo the user's most recent request: close apps JARVIS opened, move notes it created
    to a recycle folder, remove facts it just remembered and cancel reminders it just set. The user must confirm first.

    Use this when the user says "undo", "undo that", "reverse that" or "take that back".
    """
    rows = _last_batch()
    if not rows:
        return "There is nothing to undo."

    done, manual = [], []
    with closing(get_connection()) as connection:
        for row in rows:
            if row["undo"]:
                try:
                    done.append(_perform(json.loads(row["undo"])))
                except Exception as error:
                    done.append(f"failed on {_label(row)} ({error})")
            else:
                manual.append(_label(row))
            connection.execute("UPDATE action_log SET undone = 1 WHERE id = ?", (row["id"],))
        connection.commit()

    logger.info("[UNDO] %s", "; ".join(done) or "nothing reversible")
    text = "Undo complete: " + ("; ".join(done) if done else "nothing could be reversed automatically")
    if manual:
        text += ". These can't be closed automatically: " + "; ".join(manual)
    return text


# ---------------- plans ----------------

def describe_plan(args: dict) -> str:
    steps = args.get("steps") or []
    listing = "\n".join(f"  {i}. {step}" for i, step in enumerate(steps, 1))
    return f"carry out this plan for \"{args.get('goal', 'your request')}\":\n{listing}\n"


def propose_plan(goal: str, steps: list[str]) -> str:
    """Show the user a step-by-step plan and wait for approval BEFORE acting.

    Call this first whenever a request needs two or more actions on the computer
    (opening apps, websites, folders, searches, notes, routines). Do not call it for
    simple questions or for a single action.

    Args:
        goal: The user's request in a few words, for example "set up my study session".
        steps: The planned steps in plain English, for example ["Open VS Code", "Open the notes folder"].
    """
    # The security layer has already asked the user. Reaching this line means they approved.
    return "The user APPROVED the plan. Carry out exactly these steps now, then summarise."
