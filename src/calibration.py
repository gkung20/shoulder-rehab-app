"""Stable rest calibration using the same frame clock for camera and video."""
from dataclasses import dataclass
import math
import time
from typing import Optional

from src.geometry import (PoseLandmarkIndex as I, are_landmarks_visible,
    calculate_shoulder_reference_angle, calculate_distance_2d, calculate_trunk_lean)


@dataclass
class CalibrationData:
    is_calibrated: bool = False
    arm: str = "right"
    baseline_ear_shoulder_dist: Optional[float] = None
    baseline_shoulder_width: float = 0.0
    baseline_rest_angle_deg: Optional[float] = None
    baseline_trunk_lean_deg: Optional[float] = None
    reference_mode: str = "shoulders"


class CalibrationManager:
    def __init__(self, duration_sec=3.0, max_variance_ratio=0.05,
                 min_visibility=0.6, rest_threshold_deg=25.0, max_lean_deg=10.0):
        self.duration_sec = duration_sec
        self.max_variance_ratio = max_variance_ratio
        self.min_visibility = min_visibility
        self.rest_threshold_deg = rest_threshold_deg
        self.max_lean_deg = max_lean_deg
        self._is_calibrating = False
        self._active_arm = "right"
        self._start_time: Optional[float] = None
        self._now = None
        self._explicit_clock = False
        self._samples = []
        self.calibrated_data = CalibrationData()
        self.status_message = "Calibration requise : appuyez sur C"

    @property
    def is_calibrating(self):
        return self._is_calibrating

    def start(self, arm="right", timestamp_sec=None):
        if arm not in ("left", "right"):
            raise ValueError("arm must be left or right")
        self._active_arm = arm
        self._is_calibrating = True
        self._explicit_clock = timestamp_sec is not None
        self._now = timestamp_sec if self._explicit_clock else time.perf_counter()
        self._start_time = self._now
        self._samples.clear()
        # Previous baselines must never survive a failed recalibration or arm switch.
        self.calibrated_data = CalibrationData(arm=arm)
        self.status_message = "Montrez les deux epaules, gardez le bras au repos"

    def get_progress(self):
        if not self._is_calibrating or self._start_time is None:
            return 0.0, 0.0
        now = self._now if self._explicit_clock else time.perf_counter()
        elapsed = max(0.0, now - self._start_time)
        return min(1.0, elapsed / self.duration_sec), max(0.0, self.duration_sec - elapsed)

    def _reject(self, message):
        self._samples.clear()
        self._start_time = self._now
        self.status_message = message
        return False, message

    def update(self, landmarks, arm, timestamp_sec=None):
        if not self._is_calibrating:
            return False, self.status_message
        self._now = timestamp_sec if timestamp_sec is not None else time.perf_counter()
        if arm != self._active_arm:
            self.start(arm, timestamp_sec)
        if not landmarks or len(landmarks) < 33:
            return self._reject("Montrez les deux epaules pour commencer")
        sh, hip, el, ear = ((I.LEFT_SHOULDER, I.LEFT_HIP, I.LEFT_ELBOW, I.LEFT_EAR)
                            if arm == "left" else (I.RIGHT_SHOULDER, I.RIGHT_HIP, I.RIGHT_ELBOW, I.RIGHT_EAR))
        required = [landmarks[i] for i in (I.LEFT_SHOULDER, I.RIGHT_SHOULDER)]
        if not are_landmarks_visible(required, self.min_visibility):
            return self._reject("Calibration en attente : deux epaules peu visibles")
        width = calculate_distance_2d(landmarks[I.LEFT_SHOULDER], landmarks[I.RIGHT_SHOULDER])
        ear_dist = None
        if are_landmarks_visible([landmarks[ear]], self.min_visibility):
            distance = landmarks[sh].y - landmarks[ear].y
            if distance > 0:
                ear_dist = distance
        angle = None
        if are_landmarks_visible([landmarks[el]], self.min_visibility):
            angle = calculate_shoulder_reference_angle(landmarks[I.LEFT_SHOULDER], landmarks[I.RIGHT_SHOULDER], landmarks[sh], landmarks[el])
        hips_visible = (are_landmarks_visible([landmarks[I.LEFT_HIP], landmarks[I.RIGHT_HIP]], self.min_visibility)
                        and calculate_distance_2d(landmarks[sh], landmarks[hip]) > .1)
        lean = calculate_trunk_lean(*(landmarks[i] for i in (I.LEFT_SHOULDER, I.RIGHT_SHOULDER, I.LEFT_HIP, I.RIGHT_HIP))) if hips_visible else None
        if width < 0.05:
            return self._reject("Montrez les deux epaules bien separees dans l'image")
        if angle is not None and angle > self.rest_threshold_deg:
            return self._reject("Baissez le bras pour terminer la calibration")
        if lean is not None and lean > self.max_lean_deg:
            return self._reject("Redressez le buste pour la calibration")
        self._samples.append((ear_dist, width, angle, lean))
        progress, remaining = self.get_progress()
        self.status_message = f"Restez au repos encore {remaining:.1f} s"
        if progress >= 1.0:
            return self._finalize()
        return False, self.status_message

    def _finalize(self):
        if len(self._samples) < 15:
            self.status_message = f"Images valides : {len(self._samples)}/15, restez au repos"
            return False, self.status_message
        means, stds = [], []
        for i in range(4):
            values = [s[i] for s in self._samples if s[i] is not None]
            complete = len(values) == len(self._samples)
            mean = sum(values) / len(values) if complete else None
            means.append(mean)
            stds.append(math.sqrt(sum((v-mean)**2 for v in values) / len(values)) if complete else 0.)
        if means[0] is not None and stds[0] / means[1] > self.max_variance_ratio:
            means[0] = None  # An unstable optional ear disables shrug; it cannot block startup.
        if (stds[1] / means[1] > self.max_variance_ratio or stds[2] > 3 or stds[3] > 3):
            return self._reject("Mouvement detecte : restez au repos, nouvel essai")
        mode = "torso" if means[3] is not None else "shoulders"
        self.calibrated_data = CalibrationData(True, self._active_arm, *means, reference_mode=mode)
        self._is_calibrating = False
        self.status_message = "Calibration reussie" + (" : cadrage serre" if mode == "shoulders" else "")
        return True, self.status_message
