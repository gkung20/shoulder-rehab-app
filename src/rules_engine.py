"""Rule-based clinical quality engine and French feedback generator.

Evaluates biomechanical thresholds from exercise_config.yaml, providing:
1. Real-time live coaching cues in French during the exercise.
2. Comprehensive per-repetition evaluation ('CORRECT' vs 'A CORRIGER').
3. End-of-session clinical summary metrics and error histograms.
"""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.config import ExerciseConfig
from src.state_machine import ExercisePhase, RepetitionMetrics


class FeedbackLevel(str, Enum):
    """Visual priority level for user feedback cues."""
    INFO = "INFO"          # Neutral status/guidance
    SUCCESS = "SUCCESS"    # Excellent form affirmation
    WARNING = "WARNING"    # Postural compensation or speed alert


@dataclass
class LiveFeedback:
    """Current live cue displayed to the patient in real time."""
    message: str
    level: FeedbackLevel


# Standard diagnostic error categories (used for session histograms and statistics)
ERR_INSUFFICIENT_ROM = "Amplitude insuffisante"
ERR_OVERSHOOT_ROM = "Elevation excessive"
ERR_SHOULDER_SHRUG = "Haussement d'epaule excessif"
ERR_TRUNK_LEAN = "Inclinaison du tronc"
ERR_ELBOW_BENT = "Coude plie"
ERR_FAST_CONCENTRIC = "Montee trop rapide"
ERR_SHORT_HOLD = "Maintien trop court"
ERR_FAST_ECCENTRIC = "Descente trop rapide"


@dataclass
class ClinicalError:
    """Represents a specific flagged compensation or execution defect."""
    category: str
    detail: str


@dataclass
class RepetitionEvaluation:
    """Diagnostic evaluation for one completed repetition."""
    rep_index: int
    arm: str
    is_correct: bool
    status_label: str       # 'CORRECT' or 'A CORRIGER'
    reasons: List[str]      # User-facing French explanation details
    errors: List[ClinicalError] = field(default_factory=list)
    metrics: Optional[RepetitionMetrics] = None


class SessionSummary:
    """Aggregates session statistics and error frequency distributions."""

    def __init__(self):
        self.evaluations: List[RepetitionEvaluation] = []
        self.error_counter: Counter = Counter()

    def record(self, eval_result: RepetitionEvaluation) -> None:
        """Record a completed repetition evaluation and aggregate error categories."""
        self.evaluations.append(eval_result)
        for err in eval_result.errors:
            self.error_counter[err.category] += 1

    @property
    def total_repetitions(self) -> int:
        return len(self.evaluations)

    @property
    def correct_repetitions(self) -> int:
        return sum(1 for e in self.evaluations if e.is_correct)

    @property
    def success_rate_percent(self) -> float:
        if self.total_repetitions == 0:
            return 0.0
        return (self.correct_repetitions / self.total_repetitions) * 100.0

    def get_most_frequent_errors(self, top_n: int = 5) -> List[Tuple[str, int]]:
        """Return the top most frequent error categories with occurrence counts."""
        return self.error_counter.most_common(top_n)

    def reset(self) -> None:
        """Reset all session history."""
        self.evaluations.clear()
        self.error_counter.clear()


class RulesEngine:
    """Biomechanical quality evaluator based on configurable clinical thresholds."""

    def __init__(self, config: Optional[ExerciseConfig] = None):
        """Initialize RulesEngine with typed thresholds."""
        self.config = config if config is not None else ExerciseConfig.from_yaml()
        self.session = SessionSummary()

    def evaluate_live_frame(
        self,
        current_angle: Optional[float],
        current_lean: Optional[float],
        current_shrug: Optional[float],
        current_elbow: Optional[float],
        current_phase: ExercisePhase,
    ) -> LiveFeedback:
        """Generate real-time live French feedback cue for the current video frame.

        Prioritizes postural safety corrections before coaching speed or range.
        """
        if current_angle is None:
            return LiveFeedback("Positionnez-vous face a la camera", FeedbackLevel.INFO)

        # 1. Postural Compensation Checks (Highest Priority)
        if current_shrug is not None and current_shrug > self.config.compensation.max_shrug_ratio:
            return LiveFeedback("Gardez l'epaule basse !", FeedbackLevel.WARNING)

        if current_lean is not None and current_lean > self.config.compensation.max_trunk_lean_deg:
            return LiveFeedback("Gardez le tronc droit !", FeedbackLevel.WARNING)

        if current_elbow is not None and current_elbow < self.config.compensation.min_elbow_angle_deg:
            return LiveFeedback("Gardez le bras tendu !", FeedbackLevel.WARNING)

        # 2. Phase-Specific Real-time Guidance
        if current_phase == ExercisePhase.REST:
            return LiveFeedback("Pret : levez le bras sur le cote", FeedbackLevel.INFO)

        elif current_phase == ExercisePhase.RISING:
            if current_angle < self.config.abduction.target_min_deg - 10.0:
                return LiveFeedback("Montez lentement le bras...", FeedbackLevel.INFO)
            else:
                return LiveFeedback("Presque en haut, atteignez l'horizontale", FeedbackLevel.INFO)

        elif current_phase == ExercisePhase.HOLD:
            if current_angle > self.config.abduction.overshoot_warn_deg:
                return LiveFeedback("Ne levez pas trop haut (restez a l'horizontale)", FeedbackLevel.WARNING)
            return LiveFeedback("Tres bien ! Maintenez la position...", FeedbackLevel.SUCCESS)

        elif current_phase == ExercisePhase.LOWERING:
            return LiveFeedback("Controlez la descente lentement", FeedbackLevel.INFO)

        return LiveFeedback("Continuez le mouvement", FeedbackLevel.INFO)

    def evaluate_repetition(self, rep: RepetitionMetrics) -> RepetitionEvaluation:
        """Perform comprehensive clinical check on a finished repetition.

        Returns an evaluation with French reasons for any flagged compensations.
        """
        errors: List[ClinicalError] = []

        # 1. Target Range of Motion Check
        if not rep.target_reached or rep.peak_abduction_deg < self.config.abduction.target_min_deg:
            errors.append(ClinicalError(
                category=ERR_INSUFFICIENT_ROM,
                detail=f"Amplitude insuffisante : {rep.peak_abduction_deg:.1f} deg (cible : >={self.config.abduction.target_min_deg:.0f} deg)",
            ))
        elif rep.peak_abduction_deg > self.config.abduction.overshoot_warn_deg:
            errors.append(ClinicalError(
                category=ERR_OVERSHOOT_ROM,
                detail=f"Elevation trop haute : {rep.peak_abduction_deg:.1f} deg (max : {self.config.abduction.overshoot_warn_deg:.0f} deg)",
            ))

        # 2. Shoulder Shrug Compensation
        if rep.max_shrug_ratio > self.config.compensation.max_shrug_ratio:
            errors.append(ClinicalError(
                category=ERR_SHOULDER_SHRUG,
                detail=f"Haussement d'epaule excessif ({rep.max_shrug_ratio * 100:.1f}% > {self.config.compensation.max_shrug_ratio * 100:.0f}%)",
            ))

        # 3. Lateral Trunk Lean Compensation
        if rep.max_trunk_lean_deg > self.config.compensation.max_trunk_lean_deg:
            errors.append(ClinicalError(
                category=ERR_TRUNK_LEAN,
                detail=f"Inclinaison du tronc excessive ({rep.max_trunk_lean_deg:.1f} deg > {self.config.compensation.max_trunk_lean_deg:.0f} deg)",
            ))

        # 4. Elbow Flexion Compensation
        if rep.min_elbow_angle_deg < self.config.compensation.min_elbow_angle_deg:
            errors.append(ClinicalError(
                category=ERR_ELBOW_BENT,
                detail=f"Coude plie pendant le geste ({rep.min_elbow_angle_deg:.1f} deg < {self.config.compensation.min_elbow_angle_deg:.0f} deg)",
            ))

        # 5. Timing / Speed Controls
        if rep.concentric_duration_sec < self.config.timing.min_concentric_time_sec:
            errors.append(ClinicalError(
                category=ERR_FAST_CONCENTRIC,
                detail=f"Montee trop rapide ({rep.concentric_duration_sec:.1f}s < {self.config.timing.min_concentric_time_sec:.1f}s)",
            ))

        if rep.hold_duration_sec < self.config.timing.min_hold_time_sec:
            errors.append(ClinicalError(
                category=ERR_SHORT_HOLD,
                detail=f"Maintien au sommet trop bref ({rep.hold_duration_sec:.1f}s < {self.config.timing.min_hold_time_sec:.1f}s)",
            ))

        if rep.eccentric_duration_sec < self.config.timing.min_eccentric_time_sec:
            errors.append(ClinicalError(
                category=ERR_FAST_ECCENTRIC,
                detail=f"Descente trop rapide ({rep.eccentric_duration_sec:.1f}s < {self.config.timing.min_eccentric_time_sec:.1f}s)",
            ))

        is_correct = (len(errors) == 0)
        status_label = "CORRECT" if is_correct else "A CORRIGER"
        reasons = [err.detail for err in errors]

        result = RepetitionEvaluation(
            rep_index=rep.rep_index,
            arm=rep.arm,
            is_correct=is_correct,
            status_label=status_label,
            reasons=reasons,
            errors=errors,
            metrics=rep,
        )

        # Record into session summary
        self.session.record(result)
        return result
