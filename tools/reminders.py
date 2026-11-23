"""Reminders: "remind me to submit the HCI paper at 6pm".

Reminders are stored in SQLite, so they survive restarts. The desktop interface checks
for due reminders every 15 seconds and announces them with a Windows notification and
speech. A reminder that fell due while JARVIS was closed is announced as missed at start-up.
"""
import logging
import re
from contextlib import closing
from datetime import datetime, timedelta

from memory.database import get_connection

logger = logging.getLogger("jarvis")

FMT = "%Y-%m-%d %H:%M:%S"
UNIT_MINUTES = {"min": 1, "minute": 1, "hr": 60, "hour": 60, "day": 1440}
WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "five": 5, "ten": 10,
                "fifteen": 15, "twenty": 20, "thirty": 30, "half an": 0.5, "half a": 0.5}


def _table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            due_at TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )


def parse_when(when: str, now: datetime = None):
    """Turn 'in 20 minutes', '6pm', 'tomorrow 9:30 am' or '2026-11-25 18:00' into a datetime.
    Returns None if the text cannot be understood."""
    now = (now or datetime.now()).replace(microsecond=0)
    text = when.strip().lower().replace(".", "")

    # relative: "in 20 minutes", "in an hour", "in 1 hour 30 minutes", "in half an hour"
    if text.startswith("in "):
        total = 0.0
        pattern = r"(\d+(?:\.\d+)?|half an|half a|an|a|one|two|three|five|ten|fifteen|twenty|thirty)\s*(min|minute|hr|hour|day)s?\b"
        for amount, unit in re.findall(pattern, text):
            value = WORD_NUMBERS.get(amount)
            total += (float(amount) if value is None else value) * UNIT_MINUTES[unit]
        return now + timedelta(minutes=total) if total > 0 else None

    # absolute date: "2026-11-25 18:00"
    day = now.date()
    explicit_day = False
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        day = datetime(*map(int, match.groups())).date()
        explicit_day = True
        text = text.replace(match.group(0), " ")
    if "tomorrow" in text:
        day = now.date() + timedelta(days=1)
        explicit_day = True
    elif "tonight" in text and not re.search(r"\b(am|pm)\b", text):
        text += " pm"

    if "noon" in text:
        hour, minute, meridiem = 12, 0, None
    elif "midnight" in text:
        hour, minute, meridiem = 0, 0, None
        if not explicit_day:
            day = now.date() + timedelta(days=1)
            explicit_day = True
    else:
        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
        if not match:
            return None
        hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
        if hour > 23 or minute > 59 or (meridiem and not 1 <= hour <= 12):
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

    due = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    if not explicit_day and due <= now:
        # "at 6" said at 4:44 pm means 6 pm, not 6 am tomorrow
        if meridiem is None and hour < 12 and due + timedelta(hours=12) > now:
            due += timedelta(hours=12)
        else:
            due += timedelta(days=1)
    return due if due > now else None


def _say_time(due: datetime, now: datetime = None) -> str:
    now = now or datetime.now()
    clock = due.strftime("%I:%M %p").lstrip("0").lower()
    if due.date() == now.date():
        return f"today at {clock}"
    if due.date() == now.date() + timedelta(days=1):
        return f"tomorrow at {clock}"
    return due.strftime("%a %d %b at ") + clock


# ---------------- tools the AI can call ----------------

def set_reminder(text: str, when: str) -> str:
    """Set a reminder that JARVIS will announce at the given time.

    Args:
        text: What to remind the user about, for example "submit the HCI paper".
        when: When to remind, in the user's words: "in 20 minutes", "in 2 hours", "6pm",
            "tomorrow 9:30 am", "noon", or a date and time such as "2026-11-25 18:00".
    """
    text = text.strip()
    if not text:
        return "Error: the reminder needs some text."
    due = parse_when(when)
    if due is None:
        return f"Error: I couldn't understand the time '{when}'. Try '6pm', 'in 20 minutes' or 'tomorrow 9am'."
    with closing(get_connection()) as connection:
        _table(connection)
        reminder_id = connection.execute(
            "INSERT INTO reminders (text, due_at) VALUES (?, ?)", (text, due.strftime(FMT))
        ).lastrowid
        connection.commit()
    logger.info("[REMINDER] #%d set for %s: %s", reminder_id, due.strftime(FMT), text)
    return f"Reminder #{reminder_id} set for {_say_time(due)}: {text}"


def list_reminders() -> str:
    """List the user's upcoming reminders."""
    with closing(get_connection()) as connection:
        _table(connection)
        rows = connection.execute(
            "SELECT id, text, due_at FROM reminders WHERE done = 0 ORDER BY due_at"
        ).fetchall()
    if not rows:
        return "You have no upcoming reminders."
    return "Upcoming reminders:\n" + "\n".join(
        f"- #{row['id']} {_say_time(datetime.strptime(row['due_at'], FMT))}: {row['text']}" for row in rows
    )


def _matching(keyword: str):
    keyword = keyword.strip().lower().lstrip("#")
    with closing(get_connection()) as connection:
        _table(connection)
        rows = connection.execute("SELECT id, text, due_at FROM reminders WHERE done = 0").fetchall()
    if keyword.isdigit():
        return [r for r in rows if r["id"] == int(keyword)]
    return [r for r in rows if keyword and keyword in r["text"].lower()]


def describe_cancel(keyword: str) -> str:
    matches = _matching(keyword)
    if len(matches) != 1:
        return f"cancel the reminder about '{keyword}' ({len(matches)} matches, so nothing will be cancelled)"
    return f"cancel reminder #{matches[0]['id']}: '{matches[0]['text']}'"


def cancel_reminder(keyword: str) -> str:
    """Cancel an upcoming reminder. The user must confirm first.

    Args:
        keyword: The reminder number (for example "3") or a word from its text (for example "HCI").
    """
    matches = _matching(keyword)
    if not matches:
        return f"There is no upcoming reminder matching '{keyword}'."
    if len(matches) > 1:
        listing = "; ".join(f"#{m['id']} {m['text']}" for m in matches)
        return f"Error: '{keyword}' matches several reminders ({listing}). Ask the user which one."
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM reminders WHERE id = ?", (matches[0]["id"],))
        connection.commit()
    return f"Cancelled reminder #{matches[0]['id']}: {matches[0]['text']}"


# ---------------- used by the interface ----------------

def pop_due_reminders(now: datetime = None):
    """Return reminders that are due, as (text, due_at, missed), and mark them done.
    'missed' is True when the reminder fell due more than 2 minutes ago."""
    now = now or datetime.now()
    with closing(get_connection()) as connection:
        _table(connection)
        rows = connection.execute(
            "SELECT id, text, due_at FROM reminders WHERE done = 0 AND due_at <= ? ORDER BY due_at",
            (now.strftime(FMT),),
        ).fetchall()
        connection.executemany("UPDATE reminders SET done = 1 WHERE id = ?", [(r["id"],) for r in rows])
        connection.commit()
    result = []
    for row in rows:
        due = datetime.strptime(row["due_at"], FMT)
        result.append((row["text"], due, now - due > timedelta(minutes=2)))
    return result


def delete_reminder(reminder_id: int) -> None:
    """Used by undo."""
    with closing(get_connection()) as connection:
        _table(connection)
        connection.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        connection.commit()
