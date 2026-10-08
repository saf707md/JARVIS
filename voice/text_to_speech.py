import logging

import pyttsx3

logger = logging.getLogger("jarvis")


def speak(text: str) -> None:
    """Speak text out loud using the built-in Windows voice (safe to call from any thread)."""
    com_started = False
    try:
        import comtypes
        comtypes.CoInitialize()
        com_started = True
    except Exception:
        pass  # already set up in this thread, or not needed

    try:
        logger.info("[TTS] Speaking")
        # A fresh engine each time avoids a known bug where later calls stay silent
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)  # words per minute
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as error:
        logger.error("[TTS] Error: %s", error)
    finally:
        if com_started:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
