import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("jarvis")

# The ONLY programs JARVIS may open: friendly name -> Windows launch target.
APPLICATIONS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "file explorer": "explorer",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "settings": "ms-settings:",
}


def find_vscode():
    """Return the path of Code.exe, or None.

    The 'code' command is a .cmd script, and starting it opens a Command Prompt window.
    Launching Code.exe directly avoids that window.
    """
    candidates = []
    script = shutil.which("code")
    if script:
        candidates.append(Path(script).resolve().parent.parent / "Code.exe")  # ...\VS Code\bin\code.cmd
    for variable, folder in (("LOCALAPPDATA", "Programs/Microsoft VS Code"),   # per-user install (most common)
                             ("ProgramFiles", "Microsoft VS Code"),            # system-wide install
                             ("ProgramFiles(x86)", "Microsoft VS Code")):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / folder / "Code.exe")
    for path in candidates:
        if path.is_file():
            return path
    return None


def open_application(app_name: str) -> str:
    """Open an approved application on the user's computer.

    Approved applications: chrome, edge, notepad, calculator, paint,
    file explorer, vs code, settings.

    Args:
        app_name: The name of the application to open, for example "chrome".
    """
    key = app_name.strip().lower()
    target = APPLICATIONS.get(key)

    if target is None:
        approved = ", ".join(sorted(APPLICATIONS))
        return f"Error: '{app_name}' is not on my approved list. Approved: {approved}."

    if target == "code":
        exe = find_vscode()
        if exe is not None:
            logger.info("[TOOL] Launching application %s", exe)
            subprocess.Popen([str(exe)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened {app_name}."

    try:
        logger.info("[TOOL] Launching application %s", target)
        result = subprocess.run(
            ["cmd", "/c", "start", "", target],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return f"Error: I couldn't open {app_name}. It may not be installed."
        return f"Opened {app_name}."
    except Exception as error:
        logger.error("[TOOL] Failed to open %s: %s", app_name, error)
        return f"Error: I couldn't open {app_name}."
