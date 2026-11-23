"""Global hotkey (works in any app) and copying the user's selected text, on Windows.

Uses only the Windows API through ctypes, so no extra library is needed:
- RegisterHotKey listens for Ctrl+Shift+J in a background thread.
- After the hotkey, we wait until the keys are released, then send Ctrl+C to the app
  in front so its selected text lands on the clipboard. The interface reads it and
  puts the user's previous clipboard back.

Setting in .env (optional):
    JARVIS_HOTKEY=ctrl+shift+j
"""
import ctypes
import logging
import os
import threading
import time

logger = logging.getLogger("jarvis")

MODIFIERS = {"ctrl": 0x0002, "control": 0x0002, "shift": 0x0004, "alt": 0x0001, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
VK_CONTROL, VK_SHIFT, VK_MENU, VK_LWIN = 0x11, 0x10, 0x12, 0x5B
KEYEVENTF_KEYUP = 0x0002
HOTKEY_ID = 0x4A52  # any number unique to this app


def parse_hotkey(text: str):
    """'ctrl+shift+j' -> (modifier flags, virtual-key code, pretty name). Raises ValueError."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("a hotkey needs at least one modifier and one key, for example ctrl+shift+j")
    *mods, key = parts
    flags = 0
    for mod in mods:
        if mod not in MODIFIERS:
            raise ValueError(f"unknown modifier '{mod}'")
        flags |= MODIFIERS[mod]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"unsupported key '{key}'")
    pretty = "+".join([m.capitalize() for m in mods] + [key.upper()])
    return flags, vk, pretty


def configured_hotkey():
    return parse_hotkey(os.getenv("JARVIS_HOTKEY", "ctrl+shift+j"))


class GlobalHotkey:
    """Calls on_press() (from a background thread) whenever the hotkey is pressed anywhere."""

    def __init__(self, on_press, hotkey=None):
        self.on_press = on_press
        self.flags, self.vk, self.name = hotkey or configured_hotkey()
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self.ok = False

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True, name="hotkey")
        self._thread.start()
        self._ready.wait(timeout=2)
        return self.ok

    def stop(self):
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self):
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        # The hotkey must be registered in the same thread that reads the messages
        self.ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, self.flags | MOD_NOREPEAT, self.vk))
        self._ready.set()
        if not self.ok:
            logger.warning("[HOTKEY] %s is already used by another program", self.name)
            return
        logger.info("[HOTKEY] Select text anywhere and press %s", self.name)
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self.on_press()
                    except Exception as error:
                        logger.error("[HOTKEY] Handler failed: %s", error)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)


def _key_down(vk: int) -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def send_copy(hotkey_vk: int) -> None:
    """Wait (up to 1.5 s) until the user lets go of the hotkey, then press Ctrl+C for them.

    Sending Ctrl+C while Shift is still held would press Ctrl+Shift+C, which does
    something else in many apps (for example, it opens developer tools in browsers)."""
    end = time.time() + 1.5
    while time.time() < end and any(_key_down(k) for k in (VK_SHIFT, VK_MENU, VK_LWIN, hotkey_vk)):
        time.sleep(0.02)
    keybd = ctypes.windll.user32.keybd_event
    keybd(VK_CONTROL, 0, 0, 0)
    keybd(ord("C"), 0, 0, 0)
    keybd(ord("C"), 0, KEYEVENTF_KEYUP, 0)
    keybd(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
