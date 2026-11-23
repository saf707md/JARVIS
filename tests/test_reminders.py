from datetime import datetime

import pytest

from core import actions
from tools.registry import run_tool
from tools.reminders import list_reminders, parse_when, pop_due_reminders

NOW = datetime(2026, 11, 23, 16, 44)  # Monday 4:44 pm


@pytest.mark.parametrize("when, expected", [
    ("in 20 minutes", datetime(2026, 11, 23, 17, 4)),
    ("in an hour", datetime(2026, 11, 23, 17, 44)),
    ("in 1 hour 30 minutes", datetime(2026, 11, 23, 18, 14)),
    ("in half an hour", datetime(2026, 11, 23, 17, 14)),
    ("in 2 days", datetime(2026, 11, 25, 16, 44)),
    ("6pm", datetime(2026, 11, 23, 18, 0)),
    ("6:30 PM", datetime(2026, 11, 23, 18, 30)),
    ("at 6", datetime(2026, 11, 23, 18, 0)),          # 6 am has passed, so 6 pm
    ("9am", datetime(2026, 11, 24, 9, 0)),            # passed today, so tomorrow
    ("tomorrow 9:30 am", datetime(2026, 11, 24, 9, 30)),
    ("tomorrow at noon", datetime(2026, 11, 24, 12, 0)),
    ("tonight at 10", datetime(2026, 11, 23, 22, 0)),
    ("midnight", datetime(2026, 11, 24, 0, 0)),
    ("2026-11-25 18:00", datetime(2026, 11, 25, 18, 0)),
    ("20:15", datetime(2026, 11, 23, 20, 15)),
])
def test_parse_when(when, expected):
    assert parse_when(when, NOW) == expected


@pytest.mark.parametrize("when", ["someday", "in a while", "25:00", "13pm", "2026-11-20 10:00"])
def test_parse_when_rejects(when):
    assert parse_when(when, NOW) is None


def test_set_list_and_fire_reminder():
    result = run_tool("set_reminder", {"text": "submit the HCI paper", "when": "in 10 minutes"})
    assert result.startswith("Reminder #1 set for")
    assert "submit the HCI paper" in list_reminders()
    assert pop_due_reminders() == []                                   # not due yet
    due = pop_due_reminders(datetime(2099, 1, 1))
    assert [(text, missed) for text, _, missed in due] == [("submit the HCI paper", True)]
    assert pop_due_reminders(datetime(2099, 1, 1)) == []               # announced only once
    assert list_reminders() == "You have no upcoming reminders."


def test_bad_time_is_reported():
    assert run_tool("set_reminder", {"text": "x", "when": "someday"}).startswith("Error")


def test_cancel_needs_confirmation_and_one_match():
    run_tool("set_reminder", {"text": "call mom", "when": "in 1 hour"})
    run_tool("set_reminder", {"text": "call the guide", "when": "in 2 hours"})
    assert "declined" in run_tool("cancel_reminder", {"keyword": "mom"}, confirm=lambda d: False)
    assert "several" in run_tool("cancel_reminder", {"keyword": "call"}, confirm=lambda d: True)
    assert run_tool("cancel_reminder", {"keyword": "mom"}, confirm=lambda d: True).startswith("Cancelled")
    assert "call mom" not in list_reminders()


def test_undo_cancels_reminder():
    actions.new_batch()
    run_tool("set_reminder", {"text": "drink water", "when": "in 5 minutes"})
    assert run_tool("undo_last_action", {}, confirm=lambda d: True).startswith("Undo complete")
    assert list_reminders() == "You have no upcoming reminders."
