"""Wake word: say "Hey JARVIS" instead of clicking SPEAK.

Uses openWakeWord's pre-trained "hey_jarvis" model, which runs locally on the CPU
(about 2 ms of work per 80 ms of audio), so no audio leaves the computer until the
wake word is heard.

The listener holds the microphone only while JARVIS is idle. Whenever JARVIS is busy
(listening to a request, thinking or speaking) the listener is paused and the microphone
is released, so speech recognition can use it and JARVIS never wakes itself up.

Settings in .env (optional):
    JARVIS_WAKE_WORD=on        # "off" to disable
    JARVIS_WAKE_THRESHOLD=0.5  # 0-1; higher = fewer false wake-ups, lower = easier to trigger
"""
import logging
import os
import threading
import time

logger = logging.getLogger("jarvis")

MODEL_NAME = "hey_jarvis"
SAMPLE_RATE = 16000
FRAME = 1280            # 80 ms of 16 kHz audio, the size openWakeWord expects
COOLDOWN_SECONDS = 2.0  # ignore repeats of the same "Hey JARVIS"


def enabled() -> bool:
    return os.getenv("JARVIS_WAKE_WORD", "on").strip().lower() not in ("off", "0", "false", "no")


def threshold() -> float:
    try:
        return min(max(float(os.getenv("JARVIS_WAKE_THRESHOLD", "0.5")), 0.05), 0.99)
    except ValueError:
        return 0.5


def load_model():
    """Load the 'hey_jarvis' model, downloading it once (about 2 MB) if it is missing."""
    from openwakeword.model import Model
    from openwakeword.utils import download_models
    try:
        return Model(wakeword_models=[MODEL_NAME], inference_framework="onnx")
    except Exception:
        logger.info("[VOICE] Downloading the wake-word model (first run only)")
        download_models([MODEL_NAME])
        return Model(wakeword_models=[MODEL_NAME], inference_framework="onnx")


class _Microphone:
    """16 kHz mono microphone stream through PyAudio (already used by speech recognition)."""

    def __init__(self):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                                     input=True, frames_per_buffer=FRAME)

    def read(self):
        import numpy as np
        return np.frombuffer(self._stream.read(FRAME, exception_on_overflow=False), dtype=np.int16)

    def close(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        finally:
            self._pa.terminate()


class WakeWordListener:
    """Runs in a background thread and calls on_wake() when "Hey JARVIS" is heard."""

    def __init__(self, on_wake, model=None, microphone_factory=_Microphone, sensitivity=None):
        self.on_wake = on_wake
        self.model = model if model is not None else load_model()
        self.microphone_factory = microphone_factory
        self.threshold = sensitivity if sensitivity is not None else threshold()
        self._paused = threading.Event()
        self._released = threading.Event()   # set while the microphone is NOT held
        self._released.set()
        self._stop = threading.Event()
        self._last_wake = 0.0
        self._thread = None

    # ---- control (safe to call from any thread) ----
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="wake-word")
        self._thread.start()
        logger.info("[VOICE] Wake word active: say \"Hey JARVIS\"")

    def pause(self, wait: float = 1.5):
        """Stop listening and release the microphone (waits until it is released)."""
        self._paused.set()
        if threading.current_thread() is not self._thread:
            self._released.wait(timeout=wait)

    def resume(self):
        self._paused.clear()

    def stop(self, wait: float = 1.0):
        self._stop.set()
        self._paused.set()
        if self._thread is not None and threading.current_thread() is not self._thread:
            self._thread.join(timeout=wait)

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    # ---- background loop ----
    def _run(self):
        microphone = None
        failures = 0
        while not self._stop.is_set():
            if self._paused.is_set():
                if microphone is not None:
                    microphone.close()
                    microphone = None
                    self._released.set()
                time.sleep(0.05)
                continue
            try:
                if microphone is None:
                    self._released.clear()
                    microphone = self.microphone_factory()
                    self.model.reset()
                score = float(self.model.predict(microphone.read()).get(MODEL_NAME, 0.0))
                failures = 0
            except Exception as error:
                failures += 1
                logger.error("[VOICE] Wake-word microphone error: %s", error)
                if microphone is not None:
                    try:
                        microphone.close()
                    except Exception:
                        pass
                    microphone = None
                self._released.set()
                if failures >= 5:
                    logger.error("[VOICE] Wake word stopped after repeated microphone errors")
                    break
                time.sleep(2)
                continue

            now = time.monotonic()
            if score >= self.threshold and now - self._last_wake > COOLDOWN_SECONDS:
                self._last_wake = now
                logger.info("[VOICE] Wake word heard (score %.2f)", score)
                self._paused.set()          # hand the microphone over to speech recognition
                microphone.close()
                microphone = None
                self._released.set()
                try:
                    self.on_wake()
                except Exception as error:
                    logger.error("[VOICE] Wake handler failed: %s", error)

        if microphone is not None:
            microphone.close()
        self._released.set()
