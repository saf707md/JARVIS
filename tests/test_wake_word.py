import threading
import time

from voice import wake_word
from voice.wake_word import WakeWordListener


class FakeModel:
    """Returns the next score from a list for every 80 ms frame."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.resets = 0

    def predict(self, frame):
        return {"hey_jarvis": self.scores.pop(0) if self.scores else 0.0}

    def reset(self):
        self.resets += 1


class FakeMic:
    opened = 0
    open_now = 0

    def __init__(self):
        FakeMic.opened += 1
        FakeMic.open_now += 1

    def read(self):
        time.sleep(0.005)
        return b"\0" * 2560

    def close(self):
        FakeMic.open_now -= 1


def _wait(condition, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _listener(scores, **kwargs):
    FakeMic.opened = FakeMic.open_now = 0
    woke = threading.Event()
    listener = WakeWordListener(woke.set, model=FakeModel(scores), microphone_factory=FakeMic, sensitivity=0.5, **kwargs)
    return listener, woke


def test_wakes_on_high_score_and_releases_microphone():
    listener, woke = _listener([0.1, 0.2, 0.9])
    listener.start()
    assert woke.wait(2)
    assert listener.paused                     # hands the mic to speech recognition
    assert _wait(lambda: FakeMic.open_now == 0)
    listener.stop()


def test_low_scores_never_wake():
    listener, woke = _listener([0.1, 0.3, 0.49] * 20)
    listener.start()
    assert not woke.wait(0.6)
    listener.stop()


def test_paused_listener_holds_no_microphone():
    listener, woke = _listener([0.0] * 1000)
    listener.start()
    assert _wait(lambda: FakeMic.open_now == 1)
    listener.pause()
    assert FakeMic.open_now == 0               # pause() waits until the mic is released
    listener.resume()
    assert _wait(lambda: FakeMic.open_now == 1)
    listener.stop()


def test_starts_paused_until_resumed():
    listener, woke = _listener([0.9] * 10)
    listener.pause()
    listener.start()
    time.sleep(0.2)
    assert FakeMic.opened == 0 and not woke.is_set()
    listener.resume()
    assert woke.wait(2)
    listener.stop()


def test_microphone_errors_do_not_crash(monkeypatch):
    monkeypatch.setattr(wake_word.time, "sleep", lambda s: None)
    calls = []

    def broken_mic():
        calls.append(1)
        raise OSError("no microphone")

    listener = WakeWordListener(lambda: None, model=FakeModel([]), microphone_factory=broken_mic, sensitivity=0.5)
    listener._run()                            # gives up after 5 failures instead of looping forever
    assert len(calls) == 5


def test_settings(monkeypatch):
    monkeypatch.setenv("JARVIS_WAKE_WORD", "off")
    assert not wake_word.enabled()
    monkeypatch.setenv("JARVIS_WAKE_WORD", "on")
    assert wake_word.enabled()
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "0.7")
    assert wake_word.threshold() == 0.7
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "nonsense")
    assert wake_word.threshold() == 0.5
