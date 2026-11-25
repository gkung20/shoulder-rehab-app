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
| 1 Foundations | done | cue codes, layout module, App class, exercises in YAML |
| 2 Plan per patient | done | plan in profile, physio settings (PIN 0000), resting angle, sets |
| 3 Results and history | done | session files, results screen, 30-day history, export PDF/CSV/JSON |
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
- Last synced commit: `2685adb` (end of Phase 2); updated after each phase.

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
- Phase 1.1: the first-session tour said "And now, lower slowly" (S7.12) as soon as the arm reached
  the zone, because the hold cue also contained "redescendez"; S7.11 ("Hold it") now plays first.
- Phase 1.2: renders of 35 screen states were compared before and after the layout change with a
  frozen clock: identical.
- Phase 1.3: the end-to-end tests now patch `src.desktop_app` (where the app lives) instead of
  `app_live_cv`.
- Phase 2.2: the PIN is 0000 until the physio changes it (chosen at the start of the sprint);
  the settings button shows on Willy's home once the tour is done, so the tour stays simple.
- Phase 2.3: calibration now accepts a resting arm up to the target minimum - 15 deg (65 deg by
  default) so a stiff shoulder can calibrate; an arm raised higher is still refused.
- Phase 2.4: a gentle session (pain 4-6, Phase 4) will have 30% fewer reps per set.
- Phase 3.4: no folder dialog (it could freeze the OpenCV window, which can't be checked here); the
  export goes to Documents\Mouvement with an "Open the folder" button. The PDF is a new multi-session
  report; `src/report_generator.py` still makes the one-session report of the web version.
- New Willy lines: E6.09, E6.10, E6.11 (sets), E8.01 (plan updated), E7.04 to E7.07 (history trend),
  E8.02 (export saved); in lines.yaml, and added to the script doc at the end of the sprint.
- `src/synthetic_pose.py`: one synthetic-body helper for tests, previews and tools (both arms,
  turning, seated, free hand raised).

## To test on the PC

- After Phase 3: finish a session, press "Mon bilan", then "Historique", choose a period and
  "Exporter"; open `Documents\Mouvement\bilan_...\bilan.pdf` and `mouvements.csv` in Excel.
- After Phase 2: on Willy's home, press "Réglages kiné", type 0000, change a value, save: Willy
  says the plan was updated. Then change the PIN. Start a session with a small plan (2 sets of 2)
  and check the rest between sets, then that the session ends by itself.
- After Phase 2: if your resting arm is a little raised, check the measured resting angle in the
  settings after a session.
- After Phase 1: run `python app_live_cv.py` once and check that the home screen, the tour and a
  session behave exactly as before (the code was reorganised, nothing should look different).
