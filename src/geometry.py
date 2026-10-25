"""Biomechanical geometry and vector calculations for active shoulder abduction.

All functions in this module are pure functions, operating on 2D coordinates
projected onto the camera image plane. No external state or I/O is performed.
"""

from dataclasses import dataclass
from enum import IntEnum
import math
from typing import Sequence, Tuple


class PoseLandmarkIndex(IntEnum):
    """MediaPipe Pose 33 landmark standard indices."""
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


@dataclass(frozen=True)
class Point2D:
    """Represents a 2D landmark point with normalized image coordinates [0, 1]."""
    x: float
    y: float
    visibility: float = 1.0

    def to_pixel(self, image_width: int, image_height: int) -> Tuple[int, int]:
        """Convert normalized coordinates (0.0 to 1.0) to integer pixel coordinates."""
        px = int(round(self.x * image_width))
        py = int(round(self.y * image_height))
        return px, py


def calculate_angle_2d(p_vertex: Point2D, p1: Point2D, p2: Point2D) -> float:
    """Calculate the planar angle (in degrees) at p_vertex between p1 and p2.

    Computes the angle between vector (p1 - p_vertex) and vector (p2 - p_vertex):
        cos(theta) = (v1 . v2) / (||v1|| * ||v2||)

    Args:
        p_vertex: The central vertex point of the angle (e.g., shoulder).
        p1: The first endpoint (e.g., hip).
        p2: The second endpoint (e.g., elbow).

    Returns:
        Angle in degrees in the range [0.0, 180.0].
        Returns 0.0 if any vector has near-zero length.
    """
    v1_x = p1.x - p_vertex.x
    v1_y = p1.y - p_vertex.y

    v2_x = p2.x - p_vertex.x
    v2_y = p2.y - p_vertex.y

    norm1 = math.hypot(v1_x, v1_y)
    norm2 = math.hypot(v2_x, v2_y)

    # Prevent division by zero if joints coincide
    if norm1 < 1e-7 or norm2 < 1e-7:
        return 0.0

    dot_product = (v1_x * v2_x) + (v1_y * v2_y)
    cosine = dot_product / (norm1 * norm2)

    # Numerical safety clamp to avoid domain errors in acos
    clamped_cos = max(-1.0, min(1.0, cosine))
    angle_rad = math.acos(clamped_cos)
    return math.degrees(angle_rad)


def calculate_abduction_angle(shoulder: Point2D, hip: Point2D, elbow: Point2D) -> float:
    """Calculate active shoulder abduction angle in degrees.

    The abduction angle is formed by the vertex at the shoulder between:
      - Trunk vector: from shoulder to ipsilateral hip (pointing downwards along torso).
      - Arm vector: from shoulder to elbow (pointing downwards along the humerus).

    Biomechanical interpretation:
      - Anatomical rest (arm hanging down against flank): angle ~ 0 deg to 15 deg.
      - Arm raised to horizontal (shoulder level): angle ~ 90 deg.
      - Full overhead abduction: angle approaches 180 deg.

    Args:
        shoulder: The shoulder landmark of the active arm (vertex).
        hip: The ipsilateral hip landmark.
        elbow: The ipsilateral elbow landmark.

    Returns:
        Abduction angle in degrees [0.0, 180.0].
    """
    return calculate_angle_2d(p_vertex=shoulder, p1=hip, p2=elbow)


def calculate_elbow_angle(shoulder: Point2D, elbow: Point2D, wrist: Point2D) -> float:
    """Calculate the elbow extension angle in degrees.

    Vertex is at the elbow, formed by vectors to the shoulder and to the wrist.
    - Full anatomical extension (straight arm) = ~180 degrees.
    - 90-degree flexion = ~90 degrees.

    Args:
        shoulder: Shoulder landmark.
        elbow: Elbow landmark (vertex).
        wrist: Wrist landmark.

    Returns:
        Elbow angle in degrees [0.0, 180.0].
    """
    return calculate_angle_2d(p_vertex=elbow, p1=shoulder, p2=wrist)


def are_landmarks_visible(landmarks: Sequence[Point2D], min_visibility: float = 0.5) -> bool:
    """Check if all provided landmarks meet the minimum confidence threshold.

    Args:
        landmarks: Sequence of Point2D objects to check.
        min_visibility: Minimum acceptable visibility score [0.0, 1.0].

    Returns:
        True if every landmark has visibility >= min_visibility, False otherwise.
    """
    return all(lm.visibility >= min_visibility for lm in landmarks)
