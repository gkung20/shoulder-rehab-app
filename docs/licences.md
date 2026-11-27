# Licences

Every library, model, voice, font, image and 3D asset Mouvement uses, where it comes from,
its licence, whether it ships with the app, and whether it may be shared. Checked on
27 November 2026 from each source: PyPI metadata of the pinned versions
(`python tools/licence_inventory.py --pypi`), model cards, project pages. Not legal advice:
the **blockers** below need a team decision before Mouvement is shared outside a
non-commercial student demo.

**Mouvement's own code has no licence yet** (no LICENSE file): by default nobody else may
reuse it. Choosing one is a team decision with Zakaria and the repository owner (see B1).

No installer is built (Phase 8.2 was not chosen): everything below is installed by
`pip install -r requirements.txt` or downloaded by `python models/download_models.py` on
each PC. "Ships" in the tables means "is in the Git repository".

## Blockers and options

| # | What | Why it blocks sharing | Options |
|---|---|---|---|
| B1 | **piper-tts** 1.8.0 (Willy's neural voice engine) | GPL-3.0-or-later ([OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)); it embeds espeak-ng (GPL-3.0). A program distributed together with it must be under a GPL-3.0-compatible licence. | (a) Keep it for the non-commercial student demo, with attribution. (b) Publish Mouvement's own code under GPL-3.0, so bundling Piper is fine (team decision with Zakaria and the repo owner). (c) Use Windows' built-in voices only (`audio.backend: system`), already the fallback. (d) Pin the archived MIT-licensed `rhasspy/piper` (no updates since October 2025). |
| B2 | **fr_FR-tom-medium** (Willy's French voice) | Its source model ([tjiho/French-tts-model-piper](https://github.com/tjiho/French-tts-model-piper)) is AGPL-3.0 with the author's own conditions: loading the weights unchanged is allowed; sharing the weights keeps the AGPL notices; fine-tuning or converting them makes a derivative; the voice must not be presented as a real or identified person, and the author must not be named in a service that uses it. Mouvement only loads the weights and pitch-shifts the audio it plays (Willy is a robot, not a person). | (a) Keep it for the demo, never naming the voice's author in the app, and not sharing the weights ourselves (each PC downloads them). (b) Replace it with a French Piper voice whose model card allows sharing, e.g. `fr_FR-siwis-medium` (dataset CC-BY 4.0 per its model card; already supported as a fallback). (c) Ask the author for a specific licence (the project says to open an issue). |
| B3 | **en_US-ryan-medium** (Willy's English voice) | Its model card: dataset RyanSpeech, **CC BY-NC-SA 4.0**, so non-commercial use only, and share-alike. | (a) Keep it for the non-commercial demo, with attribution. (b) Replace it with an English Piper voice whose dataset allows sharing, e.g. `en_US-ljspeech-medium` (model card: LJ Speech dataset, public domain); check its card first. (c) Windows' English voices (David, Zira), already the fallback. |
| B4 | **Doctor and male/female avatar GLBs** (`alo/`, not in the repository) | Downloaded without a licence file; origin and redistribution terms unknown. | (a) Keep them on the demo PC only, never in the repository (already ignored by Git). (b) Replace them with checked CC0 models (for example Quaternius or Kenney packs, reading each pack's licence). (c) Use the built-in procedural mannequins (automatic when the GLBs are missing) or a Willy-only mode without the 3D coach. (d) Ask the authors, with the original download pages. |
| B5 | **Silhouette frames** (`assets/silhouette/`, in the repository) | Rendered from `body-1/Male-low.OBJ`, which has no licence: the frames are derived from it. | (a) Keep them for the demo. (b) Re-render them from a CC0 body (Phase 11: MakeHuman's CC0 exports or a checked CC0 pack) with `tools/silhouette_frames/render_frames.py`. (c) Ask the author of the OBJ. |
| B6 | **Segoe UI** (screen font on Windows) | Microsoft's font, not redistributable. Mouvement only loads it from `C:/Windows/Fonts` at run time. | Never copy it into the repository or an installer. Elsewhere the app uses DejaVu Sans from the system. |

## Python packages

The 66 packages of the tested Windows / Python 3.13 environment (`constraints-windows-py313.txt`);
the ones Mouvement asks for directly are in **bold**, the others come with them. None is
in the repository: pip installs them. Regenerate this table with
`python tools/licence_inventory.py --pypi` after changing a version.

| Package | Version | Licence | May it be shared? |
|---|---|---|---|
| [Jinja2](https://github.com/pallets/jinja/) | 3.1.6 | BSD License | Yes, keeping its licence notice |
| [MarkupSafe](https://github.com/pallets/markupsafe/) | 3.0.4 | BSD-3-Clause | Yes, keeping its licence notice |
| **[PyYAML](https://github.com/yaml/pyyaml)** | 6.0.3 | MIT License | Yes, keeping its licence notice |
| [Pygments](https://github.com/pygments/pygments) | 2.21.0 | BSD-2-Clause | Yes, keeping its licence notice |
| [absl-py](https://github.com/abseil/abseil-py) | 2.5.1 | Apache-2.0 | Yes, keeping its licence notice |
| [altair](https://github.com/vega/altair) | 6.3.0 | BSD License | Yes, keeping its licence notice |
| [anyio](https://pypi.org/project/anyio/) | 4.16.0 | MIT | Yes, keeping its licence notice |
| [attrs](https://pypi.org/project/attrs/) | 26.1.0 | MIT | Yes, keeping its licence notice |
| [certifi](https://github.com/certifi/python-certifi) | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) | Yes; its own files stay MPL-2.0 if changed |
| [cffi](https://github.com/python-cffi/cffi) | 2.1.1 | MIT-0 | Yes, keeping its licence notice |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | 3.5.2 | MIT | Yes, keeping its licence notice |
| [click](https://github.com/pallets/click/) | 8.5.0 | BSD-3-Clause | Yes, keeping its licence notice |
| [colorama](https://github.com/tartley/colorama) | 0.4.6 | BSD License | Yes, keeping its licence notice |
| [comtypes](https://github.com/enthought/comtypes) | 1.4.17 | MIT | Yes, keeping its licence notice |
| [contourpy](https://github.com/contourpy/contourpy) | 1.4.0 | BSD-3-Clause | Yes, keeping its licence notice |
| [cycler](https://matplotlib.org/cycler/) | 0.12.1 | BSD License | Yes, keeping its licence notice |
| [flatbuffers](https://github.com/google/flatbuffers) | 25.12.19 | Apache Software License | Yes, keeping its licence notice |
| [fonttools](http://github.com/fonttools/fonttools) | 4.68.0 | MIT | Yes, keeping its licence notice |
| [h11](https://github.com/python-hyper/h11) | 0.16.0 | MIT License | Yes, keeping its licence notice |
| [idna](https://github.com/kjd/idna) | 3.20 | BSD-3-Clause | Yes, keeping its licence notice |
| [iniconfig](https://github.com/pytest-dev/iniconfig) | 2.3.1 | MIT | Yes, keeping its licence notice |
| [itsdangerous](https://github.com/pallets/itsdangerous/) | 2.2.0 | BSD License | Yes, keeping its licence notice |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT | Yes, keeping its licence notice |
| [jsonschema-specifications](https://github.com/python-jsonschema/jsonschema-specifications) | 2025.9.1 | MIT | Yes, keeping its licence notice |
| [kiwisolver](https://github.com/nucleic/kiwi) | 1.5.1 | BSD License | Yes, keeping its licence notice |
| **[matplotlib](https://github.com/matplotlib/matplotlib)** | 3.11.2 | Python Software Foundation License | Yes, keeping its licence notice |
| **[mediapipe](https://github.com/google/mediapipe)** | 1.2.0 | Apache Software License | Yes, keeping its licence notice |
| [narwhals](https://github.com/narwhals-dev/narwhals) | 2.28.0 | MIT | Yes, keeping its licence notice |
| **[numpy](https://numpy.org)** | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Yes, keeping its licence notice |
| [onnxruntime](https://onnxruntime.ai) | 1.31.1 | MIT License | Yes, keeping its licence notice |
| [opencv-contrib-python](https://github.com/opencv/opencv-python) | 5.0.0.93 | Apache Software License | Yes, keeping its licence notice |
| **[opencv-python](https://github.com/opencv/opencv-python)** | 5.0.0.93 | Apache Software License | Yes, keeping its licence notice |
| [packaging](https://github.com/pypa/packaging) | 26.3 | Apache-2.0 OR BSD-2-Clause | Yes, keeping its licence notice |
| **[pandas](https://pandas.pydata.org)** | 3.1.0 | BSD-3-Clause | Yes, keeping its licence notice |
| [pathvalidate](https://github.com/thombashi/pathvalidate) | 3.3.1 | MIT License | Yes, keeping its licence notice |
| **[pillow](https://github.com/python-pillow/Pillow)** | 13.0.0 | MIT-CMU | Yes, keeping its licence notice |
| [pip](https://github.com/pypa/pip) | 26.2.1 | MIT | Yes, keeping its licence notice |
| **[piper-tts](http://github.com/OHF-voice/piper1-gpl)** | 1.8.0 | GPL-3.0-or-later | **Blocker B1**: a program shared with it must be GPL-3.0-compatible |
| [pluggy](https://github.com/pytest-dev/pluggy) | 1.7.0 | MIT License | Yes, keeping its licence notice |
| [protobuf](https://developers.google.com/protocol-buffers/) | 7.36.2 | 3-Clause BSD License | Yes, keeping its licence notice |
| [pyarrow](https://arrow.apache.org/) | 26.0.0 | Apache-2.0 | Yes, keeping its licence notice |
| [pycparser](https://github.com/eliben/pycparser) | 3.12 | BSD-3-Clause | Yes, keeping its licence notice |
| [pydeck](https://github.com/visgl/deck.gl/tree/master/bindings/pydeck) | 0.9.3 | Apache License 2.0 | Yes, keeping its licence notice |
| [pyparsing](https://github.com/pyparsing/pyparsing.git) | 3.3.3 | MIT | Yes, keeping its licence notice |
| [pypiwin32](https://pypi.org/project/pypiwin32/) | 223 | none stated | Only installs pywin32 (PSF-2.0); Windows-only, pulled in by pyttsx3 |
| **[pytest](https://github.com/pytest-dev/pytest)** | 9.2.0 | MIT | Yes, keeping its licence notice |
| [python-dateutil](https://github.com/dateutil/dateutil) | 4.0.0 | BSD-3-Clause | Yes, keeping its licence notice |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.33 | Apache-2.0 | Yes, keeping its licence notice |
| **[pyttsx3](https://github.com/nateshmbhat/pyttsx3)** | 2.99 | MPL-2.0 | Yes; its own files stay MPL-2.0 if changed |
| [pywin32](https://github.com/mhammond/pywin32) | 312 | Python Software Foundation License | Yes, keeping its licence notice |
| [referencing](https://github.com/python-jsonschema/referencing) | 0.37.0 | MIT | Yes, keeping its licence notice |
| **[reportlab](https://www.reportlab.com/)** | 5.1.0 | BSD License | Yes, keeping its licence notice |
| [requests](https://github.com/psf/requests) | 2.34.2 | Apache Software License | Yes, keeping its licence notice |
| [rpds-py](https://github.com/crate-py/rpds) | 2026.9.1 | MIT | Yes, keeping its licence notice |
| **[sounddevice](https://pypi.org/project/sounddevice/)** | 0.5.6 | MIT | Yes, keeping its licence notice |
| [starlette](https://github.com/Kludex/starlette) | 1.10.0 | BSD-3-Clause | Yes, keeping its licence notice |
| **[streamlit](https://github.com/streamlit/streamlit)** | 1.66.1 | Apache-2.0 | Yes, keeping its licence notice |
| [typing_extensions](https://pypi.org/project/typing-extensions/) | 4.16.0 | PSF-2.0 | Yes, keeping its licence notice |
| [tzdata](https://github.com/python/tzdata) | 2026.6 | Apache-2.0 | Yes, keeping its licence notice |
| [urllib3](https://pypi.org/project/urllib3/) | 2.8.0 | MIT | Yes, keeping its licence notice |
| [uvicorn](https://github.com/Kludex/uvicorn) | 0.54.0 | BSD-3-Clause | Yes, keeping its licence notice |
| [watchdog](https://github.com/gorakhargosh/watchdog/) | 6.0.0 | Apache Software License | Yes, keeping its licence notice |
| [websockets](https://github.com/python-websockets/websockets) | 17.4 | BSD-3-Clause | Yes, keeping its licence notice |
| **[panda3d](https://github.com/panda3d/panda3d)** | 1.10.16 | BSD License | Yes, keeping its licence notice |
| **[panda3d-gltf](https://github.com/Moguri/panda3d-gltf)** | 1.3.0 | BSD License | Yes, keeping its licence notice |
| [panda3d-simplepbr](https://github.com/Moguri/panda3d-simplepbr) | 0.13.1 | BSD License | Yes, keeping its licence notice |

## Models

| Model | Source | Licence | Ships | May it be shared? |
|---|---|---|---|---|
| `pose_landmarker_full.task`, `pose_landmarker_lite.task` (and `heavy` if downloaded) | Google MediaPipe, BlazePose GHUM 3D, downloaded by `models/download_models.py` | Apache-2.0 (model card *BlazePose GHUM 3D*: "Licensed under Apache License, Version 2.0") | No (downloaded) | Yes, with the licence notice |
| `hand_landmarker.task` (optional, off by default) | Google MediaPipe Hand Landmarker, same script | Apache-2.0 (MediaPipe model card; check the PDF linked from Google's Hand Landmarker page before sharing) | No (downloaded) | Yes, with the licence notice |

## Voices

| Voice | Source | Licence | Ships | May it be shared? |
|---|---|---|---|---|
| `fr_FR-tom-medium` (Willy, French) | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/tom/medium), from [tjiho/French-tts-model-piper](https://github.com/tjiho/French-tts-model-piper) | AGPL-3.0 with the author's conditions | No (downloaded) | **Blocker B2** |
| `en_US-ryan-medium` (Willy, English) | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ryan); dataset RyanSpeech | CC BY-NC-SA 4.0 (dataset, per the model card) | No (downloaded) | **Blocker B3**: non-commercial only |
| `fr_FR-siwis-medium` (optional French fallback, female) | rhasspy/piper-voices | CC BY 4.0 (dataset, per the voice's card) | No | Yes, with attribution |
| Windows voices (SAPI: Hortense, Paul, David, Zira…) | Windows | Part of Windows | No | Used in place, never copied |

## Fonts

| Font | Where it comes from | Licence | Ships | May it be shared? |
|---|---|---|---|---|
| Segoe UI, Segoe UI Bold | `C:/Windows/Fonts`, loaded at run time | Microsoft, not redistributable | No | **Never bundle (B6)** |
| DejaVu Sans, Bold | Linux system fonts (fallback); matplotlib's own copy for charts | Bitstream Vera / DejaVu licence (free) | No | Yes |
| Helvetica (PDF reports) | ReportLab's standard PDF fonts, not embedded | Part of PDF readers | No | Yes |

## Images and 3D assets

| Asset | Where | Origin | Licence | Ships | May it be shared? |
|---|---|---|---|---|---|
| Willy's sprite layers (56 PNG) and `willy.json` | `assets/willy/` | Rendered by `tools/willy_sprites/render_sprites.py` from Willy's procedural model `tools/willy_sprites/willy_model.js` (the team's own work) | The team's, like the code (no licence chosen yet) | Yes | Once the team picks a licence |
| Willy's model and render page | `tools/willy_sprites/willy_model.js`, `render.html` | The team's own code; three.js r147 (MIT) loaded from a CDN while rendering | The team's; three.js MIT | Yes | Once the team picks a licence |
| Silhouette frames (33 PNG) and `silhouette.json` | `assets/silhouette/` | Rendered by `tools/silhouette_frames/render_frames.py` (three.js r147, MIT, from a CDN) from `body-1/Male-low.OBJ` | Derived from an unlicensed model | Yes | **Blocker B5** |
| `Male-low.OBJ` (and `body-2/male_body_files.zip`) | Marwane's Desktop, not in the repository | Downloaded; no licence found | Unknown | No | **B5** |
| Doctor, male and female avatars (3 GLB) | `alo/`, not in the repository (ignored by Git) | Downloaded (names suggest Sketchfab models); no licence file | Unknown | No | **Blocker B4** |
| Procedural mannequins | Drawn by `src/` code | The team's own work | The team's | Yes (code) | Once the team picks a licence |
| Rotation charts | `docs/img/rotation_sensitivity_*.png` | Made by `tools/rotation_sensitivity.py` | The team's | Yes | Once the team picks a licence |

## Keeping this up to date

- Before adding a library, model, voice, font, image or 3D asset: read its licence at the
  source, add a row here in the same commit, and keep any notice it requires.
- `tests/test_licences.py` fails when a pinned package or a folder of assets is missing
  from this file.
