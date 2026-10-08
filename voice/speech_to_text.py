import logging

import speech_recognition as sr

logger = logging.getLogger("jarvis")

_recognizer = sr.Recognizer()


def listen(timeout: int = 8, phrase_time_limit: int = 15) -> str:
    """Listen once through the microphone and return the recognized text.
    Returns an empty string if nothing was heard or understood."""
    try:
        with sr.Microphone() as source:
            logger.info("[VOICE] Listening...")
            _recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = _recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_time_limit
            )
        logger.info("[STT] Transcribing")
        return _recognizer.recognize_google(audio)
    except sr.WaitTimeoutError:
        logger.info("[VOICE] No speech detected")
    except sr.UnknownValueError:
        logger.info("[STT] Could not understand audio")
    except sr.RequestError as error:
        logger.error("[STT] Speech service error: %s", error)
    except Exception as error:
        logger.error("[STT] Error: %s", error)
    return ""
