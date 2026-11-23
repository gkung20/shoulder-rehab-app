# French neural voice (Willy's voice)

The default is `fr_FR-tom-medium` (male), run locally with Piper and turned into
**Willy's voice**: pitch and timbre raised 1.45x plus a light 6 Hz vibrato, the
"Cartoon buddy" voice approved for Willy (see `docs/willy.md`). No camera images,
measurements or coaching text are sent to a speech service. Speech is synthetic;
it is not a recording of a clinician.

Install the requirements, then download the voice once (with the MediaPipe models):

```powershell
python models/download_models.py          # everything
python models/download_models.py voice    # only the voice
```

Any other French Piper voice already in this folder (for example `fr_FR-siwis-medium`)
is used if Tom is missing, still with Willy's transformation.

Create a WAV sample without opening a camera or playing audio automatically:

```powershell
python -m src.audio_feedback --preview output/voix_willy.wav
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
- [Tom medium model card](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/tom/medium/MODEL_CARD),
  French (France), one male speaker. Its training data is published under
  **AGPLv3** (https://git.bksp.space/Tjiho/French-tts-model-piper): check that
  license before any commercial distribution.
- [Siwis medium model card](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD)
  (optional fallback), French (France), one speaker, dataset under CC-BY 4.0.
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).

Keep these upstream license and model-card details with redistributions.
