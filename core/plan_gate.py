"""The plan rule, enforced in code rather than left to the AI.

A plan must be approved before running when a single request leads to:
  - three or more actions on the computer, or
  - two or more actions where at least one changes something (a note, routine, memory or reminder).

The AI is asked to call propose_plan itself. If it skips that, the orchestrator builds the
plan from the tool calls the AI requested and asks the user before any of them run.
"""
ACTION_TOOLS = {
    "open_application", "open_website", "open_folder", "search_on_site", "run_routine",
    "create_note", "create_routine", "save_recent_actions_as_routine", "delete_routine",
    "remember_fact", "forget_memory", "set_reminder", "cancel_reminder",
}
CHANGE_TOOLS = {
    "create_note", "create_routine", "save_recent_actions_as_routine", "delete_routine",
    "remember_fact", "forget_memory", "set_reminder", "cancel_reminder",
}


def needs_plan(done_actions: int, done_change: bool, pending: list) -> bool:
    """pending: list of (tool name, args) the AI wants to run now."""
    names = [name for name, _ in pending if name in ACTION_TOOLS]
    if not names:
        return False
    total = done_actions + len(names)
    changes = done_change or any(name in CHANGE_TOOLS for name in names)
    return total >= 3 or (total >= 2 and changes)


def describe_call(name: str, args: dict) -> str:
    """One plain-English plan step for a tool call."""
    a = {k: str(v) for k, v in (args or {}).items()}
    steps = {
        "open_application": lambda: f"Open {a.get('app_name', 'an app').title()}",
        "open_website": lambda: f"Open {a.get('site', 'a website')}",
        "open_folder": lambda: f"Open the {a.get('folder_name', '')} folder",
        "search_on_site": lambda: f"Search {a.get('site', '')} for “{a.get('query', '')}”",
        "run_routine": lambda: f"Run the “{a.get('name', '')}” routine",
        "create_note": lambda: f"Create a note called “{a.get('filename', '')}”",
        "create_routine": lambda: f"Save a routine called “{a.get('name', '')}”",
        "save_recent_actions_as_routine": lambda: f"Save what you just did as the “{a.get('name', '')}” routine",
        "delete_routine": lambda: f"Delete the “{a.get('name', '')}” routine",
        "remember_fact": lambda: f"Remember: {a.get('fact', '')}",
        "forget_memory": lambda: f"Forget memories about “{a.get('keyword', '')}”",
        "set_reminder": lambda: f"Remind you to {a.get('text', '')} ({a.get('when', '')})",
        "cancel_reminder": lambda: f"Cancel the reminder “{a.get('keyword', '')}”",
    }
    return steps[name]() if name in steps else name.replace("_", " ").capitalize()
