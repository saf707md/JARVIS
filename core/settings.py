"""Reads and writes JARVIS's own settings in the .env file (used by the Settings window).

Only keys that start with JARVIS_ can be changed here, so the Settings window can never
touch the Gemini API key or anything else in .env. Other lines and comments are kept.
"""
import os
import re
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def read_settings(path: Path = None) -> dict:
    """Return the JARVIS_ settings currently in .env (as written there)."""
    path = path or ENV_PATH
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _LINE.match(line)
            if match and match.group(1).startswith("JARVIS_"):
                values[match.group(1)] = match.group(2).strip("\"'")
    return values


def save_settings(updates: dict, path: Path = None) -> None:
    """Write JARVIS_ settings into .env and apply them to this running process."""
    path = path or ENV_PATH
    for key, value in updates.items():
        if not key.startswith("JARVIS_"):
            raise ValueError(f"{key} cannot be changed from the Settings window")
        if "\n" in str(value) or "\r" in str(value):
            raise ValueError(f"{key} must be a single line")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    for index, line in enumerate(lines):
        match = _LINE.match(line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            lines[index] = f"{key}={remaining.pop(key)}"
    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for key, value in updates.items():
        os.environ[key] = str(value)
