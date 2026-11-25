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
| 4 Safety | done | pain check, J'ai mal, stop rules, seated mode, risk analysis |
| 5 Hands-free, camera | done | gesture, person lock, camera reconnect, fast start, face check (5.2 not chosen) |
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
- Last synced commit: `7b224cc` (end of Phase 4); updated after each phase.

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

## After Phase 6 (same workspace, same command)

| Measurement | Before: median / p95 (ms) | After: median / p95 (ms) |
| --- | ---: | ---: |
| Exercise screen, 1280x840 | 7.0 / 23.3 | 3.5 / 14.6 |
| Exercise screen, 1920x1080 | 7.1 / 21.2 | 4.2 / 14.7 |
| Home screen, 1280x840 | 6.4 / 36.1 | 4.2 / 23.2 |
| Analysis of one frame | 0.1 / 0.1 | 0.1 / 0.1 |

The 95th percentiles move a lot between runs here (shared 2-core workspace); the medians are the
stable numbers. On top of drawing, the pose model now runs in its own thread, so the screen no
longer waits for it. Run `python tools/benchmark.py` and `python app_live_cv.py --debug` on the PC.

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
- Phase 4.2: "J'ai mal" takes the place of "Mesures" during a session (Mesures stays on key D and
  before/after the session), so the patient always finds it in the bottom bar.
- Phase 4.4: seated mode estimates the trunk lean from the shoulder line's tilt, minus 5 deg of
  natural tilt as the arm rises; this is only used when the plan says seated.
- Phase 4.5: the risk analysis is in French, like the README; it names the tests of later phases,
  and a test checks that every named test exists once its phase lands.
- Phase 5.1: gestures only on the session screen (pause while counting; resume after a pause made from
  a distance), so the camera model never runs on Willy's home or after a pause clicked at the PC, as
  before. Not on the tour or results screens.
- Phase 5.3: the lock re-finds the patient only by position (never switches to someone else after a
  delay); a new session, an arm change or C restarts it.
- Phase 5.4: no camera probing at first use (DirectShow is slow to open cameras); the camera number
  is set in the physio settings.
- Phase 5.5: loading stays on the main thread (Panda3D, the OpenCV window and the Windows DLL order
  need it); the window is refreshed between steps instead.
- Phase 5.6: the face check fires from about 24 deg with depth, 32 deg without.
- New Willy lines: E3.10 (gesture recognised); E6.08 reworded (the app now retries).
- New Willy lines: E9.01, E9.03 to E9.12 (pain and safety).
- New Willy lines: E6.09, E6.10, E6.11 (sets), E8.01 (plan updated), E7.04 to E7.07 (history trend),
  E8.02 (export saved); in lines.yaml, and added to the script doc at the end of the sprint.
- `src/synthetic_pose.py`: one synthetic-body helper for tests, previews and tools (both arms,
  turning, seated, free hand raised).

## To test on the PC

- After Phase 5: during a session, hold your free hand above your head for 2 s (pause), then again
  (resume); ask someone to walk behind you; unplug the camera for a few seconds and plug it back;
  turn your body about 30 deg and check Willy asks you to face the camera. Note the startup times
  printed in the console ("[DÉMARRAGE] Fenêtre en … s, prêt en … s") and add them here.
- After Phase 5: check that "face the camera" never shows when you stand straight (MediaPipe's depth
  is noisy; the thresholds are in config/exercise_config.yaml, filtering:).
- After Phase 4: start a session and answer the pain question (try 2, 5 and 8 on three days); during a
  session press "J'ai mal" (or P); try the seated mode from the physio settings.
- After Phase 3: finish a session, press "Mon bilan", then "Historique", choose a period and
  "Exporter"; open `Documents\Mouvement\bilan_...\bilan.pdf` and `mouvements.csv` in Excel.
- After Phase 2: on Willy's home, press "Réglages kiné", type 0000, change a value, save: Willy
  says the plan was updated. Then change the PIN. Start a session with a small plan (2 sets of 2)
  and check the rest between sets, then that the session ends by itself.
- After Phase 2: if your resting arm is a little raised, check the measured resting angle in the
  settings after a session.
- After Phase 1: run `python app_live_cv.py` once and check that the home screen, the tour and a
  session behave exactly as before (the code was reorganised, nothing should look different).
