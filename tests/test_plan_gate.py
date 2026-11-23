"""The plan rule is enforced by the orchestrator even when the AI ignores it."""
from types import SimpleNamespace

import pytest

import core.orchestrator as orchestrator_module
from core.plan_gate import describe_call, needs_plan


def call(name, **args):
    return SimpleNamespace(name=name, args=args)


class FakeLLM:
    """Replays a scripted list of responses; each is a list of tool calls or a final text."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        step = self.script.pop(0)
        if isinstance(step, str):
            return SimpleNamespace(function_calls=None, text=step)
        return SimpleNamespace(function_calls=step, text=None)


def make(script, answers, fake_desktop):
    asked = []

    def confirm(description):
        asked.append(description)
        return answers.pop(0) if answers else False

    orch = orchestrator_module.Orchestrator.__new__(orchestrator_module.Orchestrator)
    orch.confirm = confirm
    orch.llm = FakeLLM(script)
    return orch, asked


OPEN3 = [call("open_application", app_name="notepad"), call("open_application", app_name="paint"),
         call("open_application", app_name="calculator")]


def test_three_actions_in_one_round_need_approval(fake_desktop):
    orch, asked = make([OPEN3, "Opened them, Sir."], [True], fake_desktop)
    assert orch.ask("open notepad, paint and calculator") == "Opened them, Sir."
    assert len(asked) == 1
    assert "1. Open Notepad" in asked[0] and "3. Open Calculator" in asked[0]
    assert [a for _, a in fake_desktop["opened"]] == ["notepad", "paint", "calculator"]


def test_declined_plan_runs_nothing(fake_desktop):
    orch, asked = make([OPEN3, "Cancelled, Sir."], [False], fake_desktop)
    orch.ask("open notepad, paint and calculator")
    assert fake_desktop["opened"] == []
    results = orch.llm.sent[1]
    assert all("declined the plan" in part.function_response.response["result"] for part in results)


def test_one_at_a_time_still_caught(fake_desktop):
    script = [[OPEN3[0]], [OPEN3[1]], [OPEN3[2]], "Done."]
    orch, asked = make(script, [False], fake_desktop)
    orch.ask("open notepad, paint and calculator")
    assert len(asked) == 1 and "(already done)" in asked[0]
    assert [a for _, a in fake_desktop["opened"]] == ["notepad", "paint"]  # the third waited and was refused


def test_two_opens_need_no_plan(fake_desktop):
    orch, asked = make([OPEN3[:2], "Done."], [], fake_desktop)
    orch.ask("open notepad and paint")
    assert asked == [] and len(fake_desktop["opened"]) == 2


def test_open_plus_change_needs_plan(fake_desktop):
    calls = [call("open_application", app_name="notepad"), call("set_reminder", text="stretch", when="in 1 hour")]
    orch, asked = make([calls, "Done."], [True], fake_desktop)
    orch.ask("open notepad and remind me to stretch in an hour")
    assert len(asked) == 1 and "Remind you to stretch" in asked[0]


def test_ai_proposed_plan_is_not_asked_twice(fake_desktop):
    script = [[call("propose_plan", goal="g", steps=["a", "b", "c"])], OPEN3, "Done."]
    orch, asked = make(script, [True], fake_desktop)
    orch.ask("set up my desk")
    assert len(asked) == 1 and len(fake_desktop["opened"]) == 3


def test_approved_level_two_step_not_asked_again(fake_desktop, tmp_path, monkeypatch):
    import tools.filesystem as filesystem
    monkeypatch.setattr(filesystem, "NOTES_DIR", tmp_path)
    calls = [call("open_application", app_name="notepad"), call("create_note", filename="plan", content="x")]
    orch, asked = make([calls, "Done."], [True], fake_desktop)
    orch.ask("open notepad and make a note")
    assert len(asked) == 1 and (tmp_path / "plan.txt").exists()


@pytest.mark.parametrize("done, changed, names, expected", [
    (0, False, ["open_application"] * 3, True),
    (0, False, ["open_application"] * 2, False),
    (2, False, ["open_application"], True),
    (0, False, ["set_reminder"], False),
    (1, True, ["open_website"], True),
    (0, False, ["calculate", "web_search", "get_weather"], False),
])
def test_needs_plan(done, changed, names, expected):
    assert needs_plan(done, changed, [(n, {}) for n in names]) is expected


def test_describe_call():
    assert describe_call("search_on_site", {"site": "youtube", "query": "lofi"}) == "Search youtube for “lofi”"
