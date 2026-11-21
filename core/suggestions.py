"""Proactive suggestions: spot habits in the usage log and offer to turn them into routines.

The idea in plain words: if you open the same things at about the same hour on several
different days, JARVIS notices and asks "want me to make this a routine?".
Everything is simple counting in SQLite, so it costs almost nothing to run.
"""
import logging
from collections import defaultdict
from contextlib import closing
from datetime import datetime

from memory.database import get_connection

logger = logging.getLogger("jarvis")

LOOKBACK_DAYS = 14
MIN_DAYS = 3   # a step must appear on at least this many different days ...
MIN_STEPS = 2  # ... and at least this many steps must share the same hour


def _name_for_hour(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _key(steps) -> str:
    return "|".join(sorted(steps))


def find_suggestion():
    """Return {'name', 'hour', 'steps', 'key'} for the strongest new habit, or None."""
    from tools.routines import all_routines

    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT step, created_at FROM usage_log WHERE created_at >= datetime('now', 'localtime', ?)",
            (f"-{LOOKBACK_DAYS} days",),
        ).fetchall()
        dismissed = {r["key"] for r in connection.execute("SELECT key FROM dismissed_suggestions")}

    # hour -> step -> set of dates it happened on
    seen = defaultdict(lambda: defaultdict(set))
    first_seen = {}
    for row in rows:
        moment = datetime.fromisoformat(row["created_at"])
        seen[moment.hour][row["step"]].add(moment.date())
        first_seen.setdefault((moment.hour, row["step"]), moment.time())

    existing = [set(steps) for steps in all_routines().values()]
    best = None
    for hour, steps in seen.items():
        habit = [step for step, days in steps.items() if len(days) >= MIN_DAYS]
        if len(habit) < MIN_STEPS:
            continue
        habit.sort(key=lambda step: first_seen[(hour, step)])  # keep the usual order
        if any(set(habit) <= routine for routine in existing):
            continue
        if _key(habit) in dismissed:
            continue
        if best is None or len(habit) > len(best["steps"]):
            best = {"name": _name_for_hour(hour), "hour": hour, "steps": habit, "key": _key(habit)}
    return best


def describe(suggestion) -> str:
    hour = suggestion["hour"]
    when = f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
    return (
        f"I've noticed that around {when} you usually: " + "; ".join(suggestion["steps"])
        + f". Want me to save this as your '{suggestion['name']}' routine?"
    )


def accept(suggestion) -> str:
    from tools.routines import save_routine
    return save_routine(suggestion["name"], suggestion["steps"])


def dismiss(suggestion) -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO dismissed_suggestions (key) VALUES (?)", (suggestion["key"],)
        )
        connection.commit()
    logger.info("[SUGGEST] Suggestion dismissed")


def suggest_routines() -> str:
    """Check the user's habits and suggest a routine they could save.

    Use this when the user asks "any suggestions?", "what do I usually do?" or
    "can you make a routine from my habits?". If the user then agrees, save it with create_routine.
    """
    suggestion = find_suggestion()
    if suggestion is None:
        return "No clear habits yet. I need to see the same actions at about the same time on at least 3 days."
    return describe(suggestion)
