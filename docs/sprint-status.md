# Sprint status (improvement sprint, from 25 Nov 2026)

Live record of the sprint run from the "Mouvement + Willy: improvement sprint prompt" doc.
Updated after every phase.

## Choices made at the start

- Optional parts: **new silhouette body (Phase 11)** only. Not built: offline voice
  commands (5.2), Darija text (10.4), Windows installer (8.2).
- Second exercise: **both arms sideways** (same front camera).
- Physio settings: **default PIN 0000**, changeable in settings.

## Progress

| Phase | Status | Notes |
| --- | --- | --- |
| 0 Setup and baseline | done | see below |
| 1 Foundations | to do | |
| 2 Plan per patient | to do | |
| 3 Results and history | to do | |
| 4 Safety | to do | |
| 5 Hands-free, camera | to do | 5.2 not chosen |
| 6 Speed | to do | |
| 7 Validation tools | to do | |
| 8 Ready to share | to do | 8.2 not chosen |
| 9 Willy polish | to do | |
| 10 More for patients | to do | 10.4 not chosen |
| 11 New silhouette body | to do | |

## Desktop folder

- `C:\Users\hp\Desktop\marwanes app` matched commit `ce68d90` exactly on 25 Nov (no local edits).
- Installed there: `pose_landmarker_full.task`, `pose_landmarker_lite.task`, `hand_landmarker.task`,
  `fr_FR-tom-medium` and `en_US-ryan-medium`. Python 3.13 on Windows (see `constraints-windows-py313.txt`).
- No shell on the PC this run, so files are synced by copying.
- Last synced commit: `ce68d90` (updated after each phase).

## Baseline (before)

Measured in the build workspace (Linux, 2 cores) with `python tools/benchmark.py`, before any change.
Marwane's PC numbers will differ; run the same command there to compare.

| Measurement | Median (ms) | 95th percentile (ms) |
| --- | ---: | ---: |
| Exercise screen, 1280x840 | 7.0 | 23.3 |
| Exercise screen, 1920x1080 | 7.1 | 21.2 |
| Home screen, 1280x840 | 6.4 | 36.1 |
| Analysis of one frame | 0.1 | 0.1 |

- Tests: 231 passed, 19 skipped with the models installed; 227 passed, 23 skipped without them (0 failed either way).
- `main()` in `app_live_cv.py`: 220 lines.

## Decisions

- Phase 0.1: the voice test assumed 22.05 kHz; Tom's voice is 44.1 kHz, so the test now reads the
  voice's own sample rate.
- Phase 0.3: CI already existed (Windows only). It now also runs on Linux, lints with ruff and
  downloads the current voices (Tom, Ryan) instead of the old Siwis voice. `gh` isn't logged in
  here, so check the Actions tab on GitHub for the result.
- Validation tools: `record_clip.py` and `evaluate_dataset.py` already exist at the repo root, so
  Phase 7 extends them instead of writing new ones in `tools/`.
- `src/synthetic_pose.py`: one synthetic-body helper for tests, previews and tools (both arms,
  turning, seated, free hand raised).

## To test on the PC

- (filled in as phases land)
