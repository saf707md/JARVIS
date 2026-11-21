from contextlib import closing
from datetime import datetime, timedelta

from core import suggestions
from memory.database import get_connection
from tools.registry import run_tool

HABIT = ["app: vs code", "folder: notes", "search: youtube | lofi music"]


def _seed(days, steps=HABIT, hour=9):
    with closing(get_connection()) as connection:
        for days_ago in range(1, days + 1):
            day = datetime.now() - timedelta(days=days_ago)
            for minute, step in enumerate(steps):
                stamp = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                connection.execute("INSERT INTO usage_log (step, created_at) VALUES (?, ?)",
                                   (step, stamp.strftime("%Y-%m-%d %H:%M:%S")))
        connection.commit()


def test_habit_detected_after_three_days():
    _seed(3)
    found = suggestions.find_suggestion()
    assert found["steps"] == HABIT and found["name"] == "morning" and found["hour"] == 9


def test_two_days_is_not_a_habit():
    _seed(2)
    assert suggestions.find_suggestion() is None


def test_single_action_is_not_a_routine():
    _seed(5, steps=["app: notepad"])
    assert suggestions.find_suggestion() is None


def test_dismissed_suggestion_not_repeated():
    _seed(4)
    suggestions.dismiss(suggestions.find_suggestion())
    assert suggestions.find_suggestion() is None


def test_accepted_suggestion_becomes_routine():
    _seed(4)
    assert "Saved the 'morning'" in suggestions.accept(suggestions.find_suggestion())
    assert suggestions.find_suggestion() is None


def test_routine_steps_do_not_count_as_habits(fake_desktop):
    run_tool("create_routine", {"name": "x", "steps": HABIT})
    run_tool("run_routine", {"name": "x"})
    with closing(get_connection()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0] == 0


def test_suggest_tool_message():
    assert "No clear habits" in run_tool("suggest_routines", {})
