import os

import pytest

from core.settings import read_settings, save_settings


def test_updates_keep_other_lines(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# my keys\nGEMINI_API_KEY=secret123\nJARVIS_VOICE=en-GB-RyanNeural\n", encoding="utf-8")
    monkeypatch.delenv("JARVIS_VOICE", raising=False)
    save_settings({"JARVIS_VOICE": "en-IN-PrabhatNeural", "JARVIS_WAKE_THRESHOLD": "0.4"}, env)
    text = env.read_text(encoding="utf-8")
    assert "# my keys" in text and "GEMINI_API_KEY=secret123" in text
    assert "JARVIS_VOICE=en-IN-PrabhatNeural" in text and "en-GB-RyanNeural" not in text
    assert text.count("JARVIS_VOICE=") == 1
    assert read_settings(env) == {"JARVIS_VOICE": "en-IN-PrabhatNeural", "JARVIS_WAKE_THRESHOLD": "0.4"}
    assert os.environ["JARVIS_VOICE"] == "en-IN-PrabhatNeural"   # applies without a restart


def test_api_key_can_never_be_changed(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=secret123\n", encoding="utf-8")
    with pytest.raises(ValueError):
        save_settings({"GEMINI_API_KEY": "stolen"}, env)
    assert env.read_text(encoding="utf-8") == "GEMINI_API_KEY=secret123\n"


def test_rejects_multi_line_values(tmp_path):
    with pytest.raises(ValueError):
        save_settings({"JARVIS_TRANSLATE_TO": "English\nGEMINI_API_KEY=x"}, tmp_path / ".env")


def test_creates_file_and_reads_quotes(tmp_path):
    env = tmp_path / ".env"
    save_settings({"JARVIS_HOTKEY": "ctrl+shift+j"}, env)
    assert read_settings(env) == {"JARVIS_HOTKEY": "ctrl+shift+j"}
    env.write_text('JARVIS_TRANSLATE_TO="Hindi"\n', encoding="utf-8")
    assert read_settings(env) == {"JARVIS_TRANSLATE_TO": "Hindi"}
