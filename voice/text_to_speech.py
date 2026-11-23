"""Text-to-speech.

By default JARVIS speaks with a natural neural voice from Microsoft Edge's online speech
service (edge-tts, free, no API key). If that fails, for example when the internet is down,
it falls back to the built-in Windows voice (pyttsx3), so JARVIS is never silent.

Settings in .env (all optional):
    JARVIS_TTS=edge            # "edge" (natural, needs internet) or "offline" (built-in voice)
    JARVIS_VOICE=en-GB-RyanNeural
    JARVIS_VOICE_RATE=+5%
"""
import asyncio
import logging
import os
import threading
import uuid
from pathlib import Path

logger = logging.getLogger("jarvis")

TTS_DIR = Path(__file__).resolve().parent.parent / "data" / "tts"
DEFAULT_VOICE = "en-GB-RyanNeural"  # calm British male voice

_lock = threading.Lock()  # one sentence at a time, so two replies never talk over each other


def _settings():
    return (
        os.getenv("JARVIS_TTS", "edge").strip().lower(),
        os.getenv("JARVIS_VOICE", DEFAULT_VOICE).strip(),
        os.getenv("JARVIS_VOICE_RATE", "+5%").strip(),
    )


def _synthesise(text: str, voice: str, rate: str, path: Path) -> None:
    """Ask the online service for an MP3 of the text."""
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(path)))


def _play_mp3(path: Path) -> None:
    """Play an MP3 and wait until it finishes, using Windows' built-in media player (no extra library)."""
    import ctypes
    mci = ctypes.windll.winmm.mciSendStringW
    alias = "jarvis_" + uuid.uuid4().hex[:8]
    error = mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    if error:
        raise RuntimeError(f"could not open audio (MCI error {error})")
    try:
        mci(f"play {alias} wait", None, 0, None)
    finally:
        mci(f"close {alias}", None, 0, None)


def _speak_natural(text: str, voice: str, rate: str) -> None:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TTS_DIR / f"{uuid.uuid4().hex}.mp3"
    try:
        _synthesise(text, voice, rate, path)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("the speech service returned no audio")
        _play_mp3(path)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _speak_offline(text: str) -> None:
    """The built-in Windows voice (works without internet)."""
    com_started = False
    try:
        import comtypes
        comtypes.CoInitialize()
        com_started = True
    except Exception:
        pass  # already set up in this thread, or not needed
    try:
        import pyttsx3
        # A fresh engine each time avoids a known bug where later calls stay silent
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)  # words per minute
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    finally:
        if com_started:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


def speak(text: str) -> None:
    """Speak text out loud (safe to call from any thread). Never raises."""
    text = (text or "").strip()
    if not text:
        return
    mode, voice, rate = _settings()
    with _lock:
        if mode != "offline":
            try:
                logger.info("[TTS] Speaking (natural voice)")
                _speak_natural(text, voice, rate)
                return
            except Exception as error:
                logger.warning("[TTS] Natural voice unavailable, using the built-in voice: %s", error)
        try:
            logger.info("[TTS] Speaking (built-in voice)")
            _speak_offline(text)
        except Exception as error:
            logger.error("[TTS] Error: %s", error)
