from core import actions
from tools.registry import run_tool


def test_plan_shows_steps_and_can_be_declined():
    seen = []
    result = run_tool("propose_plan", {"goal": "study setup", "steps": ["Open VS Code", "Open notes"]},
                      confirm=lambda d: seen.append(d) or False)
    assert "declined" in result
    assert "1. Open VS Code" in seen[0] and "2. Open notes" in seen[0]


def test_plan_approved():
    assert "APPROVED" in run_tool("propose_plan", {"goal": "g", "steps": ["a", "b"]}, confirm=lambda d: True)


def test_undo_closes_only_what_jarvis_opened(fake_desktop):
    actions.new_batch()
    run_tool("open_application", {"app_name": "calculator"})
    run_tool("open_website", {"site": "github.com"})
    description = actions.describe_undo()
    assert "app: calculator" in description and "can't close" in description
    result = run_tool("undo_last_action", {}, confirm=lambda d: True)
    assert result.startswith("Undo complete")
    assert fake_desktop["performed"] == [{"type": "close_app", "process": "CalculatorApp.exe", "label": "calculator"}]


def test_undo_skips_apps_that_were_already_open(fake_desktop, monkeypatch):
    monkeypatch.setattr(actions, "_is_running", lambda process: True)
    actions.new_batch()
    run_tool("open_application", {"app_name": "notepad"})
    run_tool("undo_last_action", {}, confirm=lambda d: True)
    assert fake_desktop["performed"] == []


def test_undo_reverses_whole_routine(fake_desktop):
    run_tool("create_routine", {"name": "work", "steps": ["app: vs code", "app: notepad"]})
    actions.new_batch()
    run_tool("run_routine", {"name": "work"})
    run_tool("undo_last_action", {}, confirm=lambda d: True)
    assert len(fake_desktop["performed"]) == 2


def test_undo_remembered_fact():
    actions.new_batch()
    run_tool("remember_fact", {"fact": "Prefers dark mode."})
    run_tool("undo_last_action", {}, confirm=lambda d: True)
    from memory.memory_manager import recall_memories
    assert "dark mode" not in recall_memories("dark mode").split(":", 1)[-1]


def test_undo_needs_confirmation(fake_desktop):
    actions.new_batch()
    run_tool("open_application", {"app_name": "paint"})
    assert "declined" in run_tool("undo_last_action", {}, confirm=lambda d: False)
    assert fake_desktop["performed"] == []


def test_nothing_to_undo():
    assert run_tool("undo_last_action", {}, confirm=lambda d: True) == "There is nothing to undo."
