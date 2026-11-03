# Reliability, evaluation and the future avatar

## What the program actually knows

MediaPipe estimates joints. `SessionProcessor` interprets those observations using
configured rules; it is not a model trained to diagnose shoulder rehabilitation.
The thresholds and confidence cutoffs remain prototype choices. This change does
not establish clinical accuracy or demographic fairness.

The default detector is now MediaPipe Full. Lite and Heavy remain selectable;
each needs its own downloaded `.task` bundle. Only model loading/inference and
software behavior have been verified here, not improved accuracy on representative
recordings. The model file hash remains in each exported configuration snapshot.

## Tight framing and camera hardware

The patient view now uses mouse-accessible Start, Pause, Resume, Finish, Help and
Mute controls. No inference/counting runs before Start or while paused/finished.
Opening help pauses the session; closing help does not silently resume it.
Pausing discards an in-flight attempt rather than crediting unobserved hold time.
Technical details and the skeleton are opt-in; measurements are unchanged by the
renderer. Patient screenshots are synthetic interface previews, not accuracy data.

Two visible shoulders can complete setup without facial landmarks, hips or an
elbow. Counting still needs a visible active shoulder and elbow. With visible
hips throughout calibration the original torso reference is used. Otherwise the
downward normal of the observed shoulder line supplies a labeled shoulder-based
angle estimate. This proxy cannot establish trunk compensation or clinical ROM.
Missing checks and the proxy reference keep overall quality **INDETERMINE**, while
the completed attempt count remains useful. No hidden hips or ears are filled in
as observations from inferred model coordinates.

The angle reference is held fixed after calibration. If hips disappear from a
torso-based session, an active repetition is discarded before switching to the
shoulder proxy; return to rest to resume. Recalibration can restore the torso
reference when framing permits. An absent or unstable optional ear disables the
shrug baseline, rather than preventing setup.

The app has no explicit head/face gate. However, Google's model card lists a
hidden head as outside supported conditions. A cropped-head camera may still
produce no pose at all. The synthetic cropped-landmark tests verify the app's
handling of available observations, not detector performance on cropped images.

Choose the camera index and requested resolution in Streamlit or with
`python app_live_cv.py --camera 1 --width 1920 --height 1080`. A compatible USB
wide-angle camera or phone exposed as a local virtual webcam can use this path.
Optional `--zoom` uses device-native units; drivers may reject it or report a
different value. Effective resolution is reported. No digital zoom-out, black
padding or image stretch is claimed to recover scene outside the physical lens.
The program displays the complete captured frame with letterboxing.

The application distinguishes:

- **Completed attempt:** a rise across the hysteresis boundary followed by a return
  to rest. A below-target attempt is counted and explained rather than disappearing.
- **CORRECT:** observed values meet the configured prototype thresholds.
- **A CORRIGER:** sufficient data was observed and at least one threshold was crossed.
- **INDETERMINE:** required observations were missing or tracking was interrupted.
  This is neither a pass nor a failed exercise. These attempts are counted, but
  excluded from success-rate and confusion-matrix denominators. Coverage is shown.
- **Interrupted attempt:** a long tracking gap discarded a movement in progress.
  It appears separately on the dashboard. The user must return to rest to restart.

Joint confidence is not a probability of correct exercise. The smoothness
percentage is an experimental mapping of a numerical jerk measure, sensitive to
lighting, frame rate, filtering and occlusion. It is not used for grading unless
`thresholds.compensation.evaluate_fluidity` is explicitly enabled. Insufficient
samples have no smoothness score. Relative ear/shoulder motion is an approximation
of shrugging; head movement can affect it. Monocular depth remains an estimate.

## Reference projects and the patterns adopted

- [Google MediaPipe pose classification and repetition counting](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose_classification.md):
  separate entry/exit thresholds prevent phantom counts. Its guidance also calls
  for varied camera angles, environments, body shapes and exercise variations.
- [TensorFlow.js pose detection](https://github.com/tensorflow/tfjs-models/tree/master/pose-detection):
  low-confidence keypoints should be excluded, and thresholds require evaluation.
- [MediaPipe Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker):
  image coordinates are normalized by the two image dimensions independently.
  This project converts them to equal units before calculating angles and ratios.
- [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment):
  bounded frame updates allow Stop and Recalibrate to run without an endless
  capture loop blocking the application.

These are architectural references. No exercise classifier or performance result
was copied from them, and their performance does not transfer to this project.

## Evaluation before claiming accuracy or reduced bias

1. Record consented, anonymized clips with at least three seconds of visible rest
   before exercise. Keep patient videos local. The recorder already records an
   anonymous participant ID, arm, intended compensation and notes.
2. Have a qualified reviewer annotate what actually happened. An intended
   compensation or a filename is not automatically ground truth. Include normal
   movements, incomplete attempts, no-person frames, occlusion, side views, pauses,
   overshoot, low light and camera movement.
3. Test both arms, camera aspect ratios, camera distances, backgrounds, clothing,
   skin tones, body sizes, mobility ranges and assistive devices. Collect only
   appropriate consented metadata; do not infer sensitive identity from video.
4. Separate participants used for tuning from participants used for evaluation.
   Freeze model version, configuration and thresholds before evaluating held-out
   clips. Never tune on the test set and then report that set as independent proof.
5. Report count error per clip, angle error against an independent reference,
   false approvals, false corrections, unassessed clips and assessment coverage.
   Report participant/condition counts and group results with uncertainty; small
   groups and repeated frames from one person are not independent evidence.
6. Compare the previous and new implementations on the same held-out clips.
   Synthetic tests verify software invariants, not human accuracy or fairness.

`evaluate_dataset.py` produces global and per-group metrics, including coverage.
Optional annotation columns `lighting`, `camera_view` and `clothing` enable
condition breakdowns; absent columns are not guessed. Data files remain ignored
by Git. No representative dataset is bundled, so no accuracy or fairness claim is
made. A future evaluation should also include confidence intervals and independent
angle/count annotations rather than just the current binary clip labels.

## Avatar integration later

`FrameAnalysis` separates observations and coaching from rendering. An avatar
renderer can consume its normalized landmarks, phase, fresh metrics, hold progress
and coaching cue, while the existing processor continues to count and evaluate.

Suggested implementation:

1. Add a clearly labeled **demonstration coach** that animates the prescribed
   movement, alongside or instead of the camera preview.
2. Optionally add a **your movement** avatar retargeted from observed joints.
   Preserve uncertainty: fade missing limbs, pause on tracking loss, and do not
   invent an ideal pose that looks like a real observation.
3. Keep avatar animation, facial encouragement and smoothing out of the scoring
   path. Never measure the ideal demonstration avatar to grade the user.
4. Use the same coaching events for speech bubbles, text and voice; respect mute
   and reduced-motion settings. Clearly identify demonstration versus observation.

The animated character and assets are future work. The current dashboard improves
guidance and reserves the rendering boundary without pretending an avatar exists.
