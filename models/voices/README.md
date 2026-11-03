# French neural voice

The default is `fr_FR-siwis-medium`, run locally with Piper. No camera images,
measurements or coaching text are sent to a speech service. Speech is synthetic;
it is not a recording of a clinician.

Install the requirements, then download the voice once:

```powershell
python -m piper.download_voices fr_FR-siwis-medium --data-dir models/voices
```

Create a WAV sample without opening a camera or playing audio automatically:

```powershell
python -m src.audio_feedback --preview output/voix_francaise.wav
```

The ONNX voice and JSON configuration stay local and are ignored by Git. Frequently
used sentences are cached in memory (32 entries), never as a persistent patient
speech cache. The model stays loaded in the audio worker. CPU synthesis uses one
ONNX thread so the camera can continue processing. Volume and pace are configurable
in `config/exercise_config.yaml`, and in Streamlit before starting a session.

With `audio.backend: auto`, Piper is preferred. If it is unavailable, only an
installed French Windows voice may be used; the application never silently reads
French using an English default. An unavailable backend or playback device is
reported in the UI and console. `system` forces Windows speech; `piper` forces
neural speech. A hardware playback test still requires listening on the target PC.

Press **A** in OpenCV to mute/unmute. Muting stops neural playback and discards
pending guidance. Corrections/results can interrupt obsolete instructions, and
expired messages are skipped. The last requested cue replaces older pending cues;
at most one repetition result is retained ahead of the next instruction.

The default `essential` guidance mode is deliberately quiet: slower neural speech
(`length_scale: 1.30`, Windows fallback: 130 words/minute), one setup announcement,
no routine phase narration, and a short count every five completed movements.
Posture warnings must persist for 1.5 seconds. All normal announcements, including
corrections, respect an eight-second minimum gap and a forty-second duplicate
cooldown. Text remains visible regardless of audio suppression. The optional
`complete` mode restores phase/result narration. These defaults are comfort
choices, not clinical timing thresholds.

Sources and attribution:

- [Piper](https://github.com/OHF-Voice/piper1-gpl), GPL-3.0.
- [Siwis medium model card](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD),
  French (France), 22,050 Hz, one speaker. The source dataset is credited there
  under CC-BY 4.0, with its training lineage described in the model card.
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).

Keep these upstream license and model-card details with redistributions.
