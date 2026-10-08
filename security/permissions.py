"""JARVIS permission levels.

Level 1 - Safe: runs automatically.
Level 2 - Needs the user's confirmation first.
Level 3 - Restricted: never runs automatically.
"""


def check_permission(tool_name: str, level: int) -> str:
    """Return 'allow', 'confirm' or 'deny' for a tool."""
    if level == 1:
        return "allow"
    if level == 2:
        return "confirm"
    return "deny"
