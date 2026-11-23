"""Windows toast notifications (the pop-ups in the bottom-right corner)."""
import logging

logger = logging.getLogger("jarvis")


def notify(title: str, message: str) -> bool:
    """Show a Windows notification. Returns False (and only logs) if it can't be shown."""
    try:
        from winotify import Notification, audio
        toast = Notification(app_id="J.A.R.V.I.S", title=title, msg=message[:250], duration="long")
        toast.set_audio(audio.Reminder, loop=False)
        toast.show()
        return True
    except Exception as error:
        logger.warning("[REMINDER] Could not show a Windows notification: %s", error)
        return False
