"""Real neural synthesis validation, without using an audio device."""
import io
import wave
import pytest

from src.speech import PiperFrenchSpeech, VOICE_DIRECTORY


def test_local_french_voice_produces_valid_audio_and_reuses_cache():
    if not (VOICE_DIRECTORY / "fr_FR-siwis-medium.onnx").exists():
        pytest.skip("Download the French voice to exercise real neural synthesis")
    pytest.importorskip("piper")
    voice=PiperFrenchSpeech()
    try:
        audio=voice.synthesize("Très bien ! Redescendez doucement le bras.")
        assert voice.synthesize("Très bien ! Redescendez doucement le bras.") is audio
        with wave.open(io.BytesIO(audio)) as wav:
            assert wav.getframerate() == 22050
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getnframes() > wav.getframerate()
            assert any(wav.readframes(wav.getnframes()))
    finally:
        voice.close()


def test_voice_name_cannot_select_english_or_escape_voice_directory():
    with pytest.raises(ValueError):
        PiperFrenchSpeech("en_US-lessac-medium")
    with pytest.raises(ValueError):
        PiperFrenchSpeech("../../private-file")
