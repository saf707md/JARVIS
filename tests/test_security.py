from security.permissions import check_permission
from tools.registry import _TOOLS, run_tool


def test_permission_levels():
    assert check_permission("x", 1) == "allow"
    assert check_permission("x", 2) == "confirm"
    assert check_permission("x", 3) == "deny"


def test_unknown_tool_is_rejected():
    assert run_tool("delete_everything", {}).startswith("Error")


def test_level_two_needs_approval():
    result = run_tool("create_note", {"filename": "t", "content": "x"}, confirm=lambda d: False)
    assert "declined" in result


def test_level_two_without_confirm_function_is_refused():
    assert "declined" in run_tool("forget_memory", {"keyword": "abc"}, confirm=None)


def test_no_shell_or_delete_tools_are_exposed():
    banned = ("shell", "cmd", "powershell", "delete_file", "install", "password")
    assert not [name for name in _TOOLS if any(word in name for word in banned)]


def test_tool_errors_never_crash_the_agent():
    assert run_tool("calculate", {"expression": "import os"}).startswith("Error")
