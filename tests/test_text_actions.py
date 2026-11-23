import pytest

from core.text_actions import ACTIONS, MAX_CHARS, build_request, clean_selection, preview
from ui.hotkey import parse_hotkey


@pytest.mark.parametrize("action", list(ACTIONS))
def test_every_action_builds_a_request(action):
    request = build_request(action, "The HCI paper is due on Friday.")
    assert "The HCI paper is due on Friday." in request
    assert "<<<SELECTED TEXT" in request and "SELECTED TEXT>>>" in request
    assert "not instructions" in request


def test_only_save_to_memory_may_use_tools():
    assert "Do not use any tools" in build_request("summarise", "x")
    assert "remember_fact" in build_request("remember", "x")
    assert "Do not use any tools" not in build_request("remember", "x")


def test_translate_language_setting(monkeypatch):
    assert "into English" in build_request("translate", "hola")
    monkeypatch.setenv("JARVIS_TRANSLATE_TO", "Hindi")
    assert "into Hindi" in build_request("translate", "hello")


def test_long_selection_is_cut_and_flagged():
    request = build_request("summarise", "a" * (MAX_CHARS + 500))
    assert "a" * MAX_CHARS in request and "a" * (MAX_CHARS + 1) not in request
    assert "only its beginning" in request


def test_empty_or_unknown_rejected():
    with pytest.raises(ValueError):
        build_request("summarise", "   \n ")
    with pytest.raises(ValueError):
        build_request("delete_everything", "text")


def test_clean_selection_tidies_windows_text():
    text, cut = clean_selection("line one  \r\n\r\n\r\n\r\nline two\r\n")
    assert text == "line one\n\nline two" and not cut


def test_preview_is_one_short_line():
    assert preview("a\nb   c") == "a b c"
    assert len(preview("word " * 50, 30)) == 30


@pytest.mark.parametrize("text, expected", [
    ("ctrl+shift+j", (0x0006, ord("J"), "Ctrl+Shift+J")),
    ("Alt + F9", (0x0001, 0x78, "Alt+F9")),
    ("ctrl+alt+1", (0x0003, ord("1"), "Ctrl+Alt+1")),
])
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["j", "ctrl+", "hyper+j", "ctrl+enter", "ctrl+f13"])
def test_parse_hotkey_rejects(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)
