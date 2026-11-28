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
| 6 Speed | done | camera thread, --debug timings, cached drawing, automatic fast model, hand model off |
| 7 Validation tools | done | protocol EN/FR with consent form, recorder, report, rotation chart |
| 8 Ready to share | done | licences with 6 blockers and their options, journal and error screen; 8.2 not chosen |
| 9 Willy polish | done | mouth follows the voice, points and looks at each zone, idle variety, pronunciation pass, express tour, chattiness |
| 10 More for patients | to do | 10.4 not chosen |
| 11 New silhouette body | in progress | half-body framing done (Marwane, 27 Nov); the new licensed body is still to do |

## Desktop folder

- `C:\Users\hp\Desktop\marwanes app` matched commit `ce68d90` exactly on 25 Nov (no local edits).
- Installed there: `pose_landmarker_full.task`, `pose_landmarker_lite.task`, `hand_landmarker.task`,
  `fr_FR-tom-medium` and `en_US-ryan-medium`. Python 3.13 on Windows (see `constraints-windows-py313.txt`).
- No shell on the PC this run, so files are synced by copying.
- Last synced: the end of Phase 9 (the commit that adds this line); updated after each phase.

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

- Hand model (`hand_landmarker.task`, 1280x720 frame): 11.7 ms per frame here. It only drew palms
  and fingers on the avatars, so it is now off by default: 11.7 ms saved on every tracked frame.
- Tests: 358 passed, 19 skipped after Phase 8 (from 231 at the start of the sprint).

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
- Phase 6.1: `--debug` shows each stage's time at the top of the screen and writes
  `%APPDATA%\Mouvement\timings.csv`; garbage collection was checked and is not what slows the slow
  frames here (the shared CPU is).
- Phase 6.2: the camera and the pose model run in a worker thread; the screen takes the newest
  result. `performance.pose_thread: false` brings back the single loop if anything misbehaves.
- Phase 6.3: the fixed parts of the session screen are drawn once and reused; Willy's renders are
  kept up to 48 MB.
- Phase 6.4: after 3 s of tracking below 15 images/s with the full model, the app switches to lite
  and saves it in the profile; the physio can choose Automatic / Accurate / Fast in the settings, and
  `--model` always wins. The default download now includes the lite model (5.5 MB, same licence).
- Phase 6.5: the hand model is off unless `--hands` or `performance.hand_model: true`.
- Settings page: long values now shrink to fit their box ("Au choix du patient" used to run under
  the minus button).
- Phase 7: the two earlier root tools became subcommands: `record_clip.py angles` (new) and
  `record_clip.py quality` (the labelled clips), `evaluate_dataset.py angles` and `quality`.
- Phase 7.2: study files go to `%APPDATA%\Mouvement\validation`, next to the patient data and out
  of the code folder. A stopped session resumes at the first missing trial; `--shuffle` mixes the
  positions of each round; `--blind` hides the app's angle from whoever reads the goniometer
  (added because the protocol asks for it).
- Phase 7.3: Bland-Altman limits use the correction for several trials per volunteer (Bland &
  Altman 2007); confidence intervals resample volunteers. The ICC code gives Shrout & Fleiss's
  published 0.29 on their example. numpy and matplotlib only (no new library).
- Phase 7.4: in the synthetic model, the 24 deg (depth) and 32 deg (width) thresholds keep the
  rotation error the app accepts within about 2 deg; at 45 deg it would reach 9 deg.
- Phase 7.1: the protocol's ethics section names law 28-13 (biomedical research, ethics committee;
  decree of 4 May 2026, AMMPS) and law 09-08 (CNDP) as questions for the supervisor, not advice.
- Phase 8.1: licences checked at the source on 27 Nov (PyPI metadata of the pinned versions,
  model cards, project pages). Blockers: piper-tts GPL-3.0-or-later (embeds espeak-ng); the Tom
  voice comes from an AGPL-3.0 model whose author adds conditions (never name the author in the
  app, never present the voice as a real person); the Ryan voice's dataset is CC BY-NC-SA 4.0;
  the GLB avatars and Male-low.OBJ (source of the silhouette frames) have no licence; Segoe UI is
  loaded from Windows, never bundled. Mouvement's own code has no licence yet: a team decision.
- Phase 8.3: the journal wraps the console instead of rewriting every print, so nothing printed is
  lost (with the double-click launcher there is no console at all). The camera thread's errors now
  reach the screen loop. English button labels were measured in French, so they sat off-centre:
  fixed for every button.
- Marwane, 27 Nov: the abduction silhouette doesn't need the whole body; cut it from the hands'
  reach (pelvis) to the head so the patient can stand closer. Done before Phase 8: the silhouette
  stops at the fingertips of the hanging arm (soft edge) and fills the picture from there to the
  head, so the shoulders are 0.37 of the picture's height instead of 0.28 (the patient stands about
  a quarter closer: roughly 1.4 m instead of 1.8 m from a usual webcam). Not cut higher, at the
  pelvis: the hips would sit at the bottom edge, and without them the app measures against the
  shoulder line, a rougher angle. "Step back" now comes from 1.15x the ideal size (was 1.28x) and the
  camera-height advice from 0.3 shoulder width (was 0.4), so the hips stay in view. On a 4:3 camera
  the silhouette moves away from the raised arm so the hand stays in the picture. Willy's lines
  S4.02 and S4.04 now say "upper body" and "hips".
- New Willy lines: E3.10 (gesture recognised); E6.08 reworded (the app now retries).
- New Willy lines: E9.01, E9.03 to E9.12 (pain and safety).
- New Willy lines: E6.09, E6.10, E6.11 (sets), E8.01 (plan updated), E7.04 to E7.07 (history trend),
  E8.02 (export saved); in lines.yaml, and added to the script doc at the end of the sprint.
- Phase 9.1: Willy's mouth follows the loudness of his voice (every 40 ms: closed, half open, open);
  with the Windows voice, which gives no sound to measure, it follows the rhythm of the text instead.
- Phase 9.5: "Willy parle : beaucoup / normalement / peu" is the last row of the physio settings.
  "Normalement" is the app as before. "Peu" doubles the pauses between lines, counts every 10
  movements and drops the everyday lines (encouragements, "still there?", tips, button reminders);
  "beaucoup" shortens the pauses and counts every 3. Safety and pain lines, and the lines needed to
  go on (framing, camera, sets, start and end), play at every level.
- Phase 9.2: Willy points from the shoulder on the zone's side at the angle of the line to the
  zone's centre (0 down, 90 level, 160 at most, 30 at least so a point downward is still seen);
  more faithful than a fixed "higher zone, higher arm" scale, and the same rule works for the big
  Willy of the demo. He turns his head (18 new layers, the same model turned 20 degrees) when the
  zone is more than half a head to one side. A point with no zone now lasts the line (4 s, or as
  long as he speaks) instead of staying up until the next line. The old "wave every 7 s before the
  session" became one greeting wave, then the idle moves; a glance alternates with a stretch or a
  wave, so the two bigger moves come every 30-60 s. Nothing idles while he talks, points, acts or
  the patient exercises.
- Phase 9.3: the pass read 392 texts (every line, every {a / b} option and singular form, and the
  screen cues the French voice may read). The French voice read 3 words the English way: "Willy"
  (wˈɪli, now "Houili": the silent h stops "Je suis‿z‿Ouili"), "express" and "coach". No symbols,
  abbreviations or sounds missing from the voices; the numbers read right (1,5 is "un virgule
  cinq"). Units after a number (°, %, m, cm, s, min) are respelled in both languages for future
  lines. The CI renders every line on Linux; a manual run ("Run workflow") keeps all_fr.wav and
  all_en.wav for a week (not on every push: 190 MB).
- Phase 9.4: the express tour also asks which arm (otherwise the first movements could be on the
  wrong side), so it is safety, arm, camera and the first movements. It is the highlighted button;
  the full tour is the other button and stays in Help. The dots under the bubble count the tour's
  stages (4 or 6), not each line, so they move at a pace the patient can follow. Back is only in the
  screen tour, the one part that is a sequence of things to look at; elsewhere a step is a choice.
- `src/synthetic_pose.py`: one synthetic-body helper for tests, previews and tools (both arms,
  turning, seated, free hand raised).

## To test on the PC

- After Phase 9: delete nothing, just run the app with sound. Listen to Willy: his mouth should
  open and close with his voice, and in French he should say "Willy", "visite express" and
  "coach" the French way. To hear every line: `python tools/render_voices.py`, then play
  `output\voices\all_fr.wav` (the times of each line are in `all_fr.txt`); tell me any word he
  says wrong and I'll add it to `assets/willy/pronounce.yaml`. Replay the tour from Aide: the
  dots move under the bubble, Retour works in the screen tour, and Willy points at each zone.
  Leave the home screen alone for two minutes: he blinks, glances, stretches or waves. Try
  "Willy parle : peu" in the physio settings during a short session.
- After Phase 8: start the app once from the double-click launcher, then open
  `%APPDATA%\Mouvement\logs\mouvement.log`: it should start with the version, Python and
  Windows lines. Read `docs/licences.md` with Zakaria and decide B1-B5 (and a licence for
  Mouvement's own code) before sharing the app outside the student demo.
- Half-body silhouette: open the camera view with the silhouette (G), stand where your upper body
  fits it (outline green), and check that raising the arm to 90 deg keeps the hand in the picture
  and that the app shows "Suivi actif" (not "Cadrage serré") when you stand a little too close.
- After Phase 7: a dry run of the study with a teammate, before the real afternoon:
  `python record_clip.py angles --subject TEST --arms right --trials 1 --blind`, then
  `python evaluate_dataset.py angles`, and open `%APPDATA%\Mouvement\validation\report`.
  Check the camera distance (section 2.2 of the protocol) and that the window keys respond.
  Give the consent form (appendix A of the protocol) to the supervisor to review, with the ethics
  questions of section 7.
- After Phase 6: run `python app_live_cv.py --debug`, do a short session and note the stage times
  shown at the top (and `python tools/benchmark.py`); add them here. Open the physio settings:
  "Modèle de suivi" says "Automatique", or "Auto (rapide)" if the PC was too slow for the full
  model. If the screen freezes or stutters, set `performance: pose_thread: false` in
  `config/exercise_config.yaml` and tell me what happened.
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
