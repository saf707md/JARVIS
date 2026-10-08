import logging
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

logger = logging.getLogger("jarvis")

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"


def take_screenshot() -> str:
    """Take a screenshot of the user's whole screen and save it as a picture file.

    Use this when the user asks to take a screenshot or capture the screen.
    """
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab().save(path)
    logger.info("[TOOL] Screenshot saved: %s", path)
    return f"Screenshot saved to {path}"
