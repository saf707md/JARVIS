import pytest

from tools.browser import open_website
from tools.calculator import calculate
from tools.filesystem import _is_blocked, create_note
import tools.filesystem as filesystem


@pytest.mark.parametrize("expression, expected", [
    ("25 * 40", "1000"), ("(3 + 4) ** 2", "49"), ("10 / 4", "2.5"), ("-5 + 2", "-3"), ("17 % 5", "2"),
])
def test_calculator(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize("expression", ["__import__('os')", "open('x')", "2 ** 1000", "[1, 2]"])
def test_calculator_rejects_code(expression):
    with pytest.raises(Exception):
        calculate(expression)


@pytest.mark.parametrize("name", ["passwords.txt", ".env", "my_secret.md", "id_rsa", "credentials.json"])
def test_sensitive_files_blocked(name):
    assert _is_blocked(name)


def test_normal_file_not_blocked():
    assert not _is_blocked("module 2 notes.txt")


def test_website_validator_rejects_commands(monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    assert open_website("rm -rf /").startswith("Error")
    assert open_website("youtube") == "Opened https://www.youtube.com"


def test_note_cannot_escape_notes_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "NOTES_DIR", tmp_path)
    assert create_note("../../evil", "x").startswith("Note created")
    assert (tmp_path / "evil.txt").exists()
    assert create_note("bad|name", "x").startswith("Error")


def test_note_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "NOTES_DIR", tmp_path)
    create_note("plan", "first")
    assert create_note("plan", "second").startswith("Error")
    assert (tmp_path / "plan.txt").read_text() == "first"
