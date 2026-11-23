import voice.text_to_speech as tts


def _record(monkeypatch, natural_fails=False):
    calls = []

    def natural(text, voice, rate):
        calls.append(("natural", text, voice, rate))
        if natural_fails:
            raise RuntimeError("no internet")

    monkeypatch.setattr(tts, "_speak_natural", natural)
    monkeypatch.setattr(tts, "_speak_offline", lambda text: calls.append(("offline", text)))
    return calls


def test_natural_voice_is_default(monkeypatch):
    calls = _record(monkeypatch)
    for name in ("JARVIS_TTS", "JARVIS_VOICE", "JARVIS_VOICE_RATE"):
        monkeypatch.delenv(name, raising=False)
    tts.speak("Good evening, Sir.")
    assert calls == [("natural", "Good evening, Sir.", "en-GB-RyanNeural", "+5%")]


def test_falls_back_to_builtin_voice(monkeypatch):
    calls = _record(monkeypatch, natural_fails=True)
    tts.speak("Hello")
    assert [c[0] for c in calls] == ["natural", "offline"]


def test_offline_setting_skips_internet(monkeypatch):
    calls = _record(monkeypatch)
    monkeypatch.setenv("JARVIS_TTS", "offline")
    tts.speak("Hello")
    assert calls == [("offline", "Hello")]


def test_voice_can_be_changed(monkeypatch):
    calls = _record(monkeypatch)
    monkeypatch.setenv("JARVIS_VOICE", "en-IN-PrabhatNeural")
    monkeypatch.setenv("JARVIS_VOICE_RATE", "+0%")
    tts.speak("Namaste")
    assert calls[0][2:] == ("en-IN-PrabhatNeural", "+0%")


def test_empty_text_is_silent(monkeypatch):
    calls = _record(monkeypatch)
    tts.speak("   ")
    assert calls == []


def test_temp_audio_file_is_removed(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "TTS_DIR", tmp_path)
    monkeypatch.setattr(tts, "_synthesise", lambda text, voice, rate, path: path.write_bytes(b"ID3fake"))
    played = []
    monkeypatch.setattr(tts, "_play_mp3", lambda path: played.append(path.exists()))
    tts._speak_natural("Hi", "v", "+0%")
    assert played == [True] and list(tmp_path.iterdir()) == []


def test_never_raises(monkeypatch):
    def broken(text):
        raise RuntimeError("no audio device")
    monkeypatch.setenv("JARVIS_TTS", "offline")
    monkeypatch.setattr(tts, "_speak_offline", broken)
    tts.speak("Hello")  # must not raise
