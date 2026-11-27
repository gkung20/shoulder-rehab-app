"""Phase 9.1: Willy's mouth follows the loudness of his voice."""
import io
import threading
import wave

import numpy as np

from src import lip_sync
from src.audio_feedback import AudioCoach
from src.lip_sync import LipTrack, loudness, mouth_frames, text_loudness, wav_loudness


def tone(levels, rate=22050, step=.04):
    """int16 audio whose loudness follows `levels`, one value per 40 ms."""
    size = int(rate * step)
    t = np.arange(size) / rate
    return np.concatenate([level * 12000 * np.sin(2 * np.pi * 220 * t) for level in levels]).astype(np.int16)


def test_a_loudness_envelope_becomes_the_expected_mouth_frames():
    envelope = [0., .05, .3, .9, 1., .4, .1, 0.]
    assert mouth_frames(envelope) == ["smile", "smile", "talk1", "talk2", "talk2", "talk1", "smile", "smile"]


def test_loudness_is_measured_every_40_ms_and_scaled_to_the_line():
    levels = [0, 0, .2, .6, 1, 1, .5, 0, 0, .8, .8, .1]
    envelope = loudness(tone(levels), 22050)
    assert len(envelope) == len(levels)
    voiced = np.array([level for level in levels if level > .05])
    expected = np.array(levels) / np.percentile(voiced, 90)  # 1.0 = the line's usual loud level
    assert np.allclose(envelope, np.clip(expected, 0, 1.5), atol=.02)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(tone(levels).tobytes())
    assert np.allclose(wav_loudness(buffer.getvalue()), envelope)
    assert len(loudness(np.zeros(0, np.int16), 22050)) == 0 and not loudness(np.zeros(900), 22050).any()


def test_without_audio_the_mouth_follows_the_text():
    envelope = text_loudness("Bonjour, je suis Willy.")
    frames = mouth_frames(envelope)
    # bon-jour (2 syllables), a pause at the comma, je, suis, Wil-ly, a longer pause at the end
    assert frames.count("talk2") >= 5 and frames[-10:] == ["smile"] * 10
    comma = 10 + 1  # two syllables of 5 steps and a breath, then the pause (0.25 s: 6 steps)
    assert set(frames[comma:comma + 6]) == {"smile"} and frames[comma + 6 + 1] != "smile"  # then "je"
    assert envelope[comma:comma + 6].max() == 0
    assert abs(len(envelope) * lip_sync.STEP - (6 * .2 + .25 + .45 + .15)) < .3  # about 5 syllables a second


def test_the_track_shows_the_mouth_for_the_moment_played():
    track = LipTrack([0, 1, .3], started=10.)
    assert [track.mouth(t) for t in (9.9, 10., 10.05, 10.09, 10.2)] == ["smile", "smile", "talk2", "talk1", "smile"]


def test_the_audio_coach_hands_the_envelope_to_willy_while_the_line_plays():
    played = threading.Event()
    release = threading.Event()

    class Engine:
        label = "fake"

        def say(self, text, cancel, on_start=None):
            on_start(np.array([1.] * 100, np.float32))
            played.set()
            release.wait(2.)

        def close(self):
            pass

    coach = AudioCoach(enabled=False)
    coach._make_backend = lambda: Engine()
    coach.enabled = True
    coach._start_worker()
    try:
        assert coach.mouth() is False
        coach.say("Bonjour", interrupt=False)
        assert played.wait(2.)
        assert coach.mouth() == "talk2"  # loud now
    finally:
        release.set()
        coach.stop()
    assert coach.mouth() is False


def test_old_engines_without_lip_sync_still_talk():
    from src.audio_feedback import _accepts_on_start

    class Old:
        def say(self, text, cancel):
            pass

    class New:
        def say(self, text, cancel, on_start=None):
            pass

    assert not _accepts_on_start(Old()) and _accepts_on_start(New())
