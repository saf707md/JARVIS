import pytest

from tools.registry import run_tool
from tools.routines import parse_step, to_step


@pytest.mark.parametrize("step, tool", [
    ("app: vs code", "open_application"), ("site: youtube", "open_website"),
    ("folder: notes", "open_folder"), ("search: youtube | lofi music", "search_on_site"),
])
def test_step_parsing_round_trip(step, tool):
    parsed = parse_step(step)
    assert parsed[0] == tool
    assert to_step(*parsed) == step


@pytest.mark.parametrize("step", ["shell: del *", "app:", "search: youtube", "hello"])
def test_invalid_steps_rejected(step):
    assert parse_step(step) is None


def test_create_and_run_routine(fake_desktop):
    steps = ["app: vs code", "folder: notes", "search: youtube | lofi music"]
    assert "Saved the 'study'" in run_tool("create_routine", {"name": "Study routine", "steps": steps})
    result = run_tool("run_routine", {"name": "study"})
    assert result.startswith("Ran the 'study' routine")
    assert fake_desktop["opened"] == [("app", "vs code"), ("folder", "notes"), ("search", "youtube", "lofi music")]


def test_routine_rejects_unapproved_app():
    assert "not an approved application" in run_tool("create_routine", {"name": "x", "steps": ["app: hacker tool"]})


def test_routine_step_limit():
    steps = ["site: youtube"] * 11
    assert run_tool("create_routine", {"name": "big", "steps": steps}).startswith("Error")


def test_unknown_routine():
    assert run_tool("run_routine", {"name": "nothing"}).startswith("Error")


def test_save_recent_actions(fake_desktop):
    run_tool("open_application", {"app_name": "notepad"})
    run_tool("open_folder", {"folder_name": "notes"})
    assert "app: notepad; folder: notes" in run_tool("save_recent_actions_as_routine", {"name": "quick"})


def test_delete_routine_needs_confirmation():
    run_tool("create_routine", {"name": "temp", "steps": ["site: github"]})
    assert "declined" in run_tool("delete_routine", {"name": "temp"}, confirm=lambda d: False)
    assert "Deleted" in run_tool("delete_routine", {"name": "temp"}, confirm=lambda d: True)
