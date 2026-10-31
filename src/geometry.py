"""Biomechanical geometry and vector calculations for active shoulder abduction.

All functions in this module are pure functions, operating on 2D coordinates
projected onto the camera image plane. No external state or I/O is performed.
"""

from dataclasses import dataclass
from enum import IntEnum
import math
from typing import Sequence, Tuple, Union


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


@dataclass(frozen=True)
class Point3D:
    """Represents a 3D landmark point with metric coordinates in meters."""
    x: float
    y: float
    z: float
    visibility: float = 1.0


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


def calculate_distance_2d(p1: Point2D, p2: Point2D) -> float:
    """Euclidean distance between two 2D points in normalized image space."""
    return math.hypot(p2.x - p1.x, p2.y - p1.y)


def get_midpoint(p1: Point2D, p2: Point2D) -> Point2D:
    """Calculate the midpoint between two landmarks."""
    return Point2D(
        x=(p1.x + p2.x) / 2.0,
        y=(p1.y + p2.y) / 2.0,
        visibility=min(p1.visibility, p2.visibility),
    )


def calculate_trunk_lean(
    left_shoulder: Point2D,
    right_shoulder: Point2D,
    left_hip: Point2D,
    right_hip: Point2D,
) -> float:
    """Calculate lateral trunk lean deviation from vertical in degrees.

    Trunk axis vector is defined from hip midpoint to shoulder midpoint
    pointing upward (towards head). Vertical reference vector is (0, -1) in
    screen coordinates where Y points downwards.

    Args:
        left_shoulder: Left shoulder landmark.
        right_shoulder: Right shoulder landmark.
        left_hip: Left hip landmark.
        right_hip: Right hip landmark.

    Returns:
        Deviation from vertical in degrees [0.0, 90.0].
        0 degrees = perfectly upright torso.
    """
    shoulder_mid = get_midpoint(left_shoulder, right_shoulder)
    hip_mid = get_midpoint(left_hip, right_hip)

    # Spine vector pointing upwards from hips to shoulders
    spine_dx = shoulder_mid.x - hip_mid.x
    spine_dy = shoulder_mid.y - hip_mid.y  # In image coords, shoulder is higher (smaller y), so spine_dy < 0

    spine_norm = math.hypot(spine_dx, spine_dy)
    if spine_norm < 1e-7:
        return 0.0

    # Vertical vector pointing upwards in image coords: (0, -1)
    # dot_product = (spine_dx * 0) + (spine_dy * -1) = -spine_dy
    cos_lean = (-spine_dy) / spine_norm
    clamped_cos = max(-1.0, min(1.0, cos_lean))
    lean_deg = math.degrees(math.acos(clamped_cos))
    return min(90.0, max(0.0, lean_deg))


def calculate_shoulder_shrug(
    ear: Point2D,
    shoulder: Point2D,
    baseline_ear_shoulder_dist: float,
    baseline_shoulder_width: float,
) -> float:
    """Calculate normalized shoulder shrug (clavicle elevation) ratio.

    A patient shrugs by pulling their shoulder upward toward the ear.
    In image coordinates (where Y increases downwards), the vertical distance
    d = (shoulder.y - ear.y). When shrugging, shoulder.y decreases, so d decreases.

    The elevation delta is normalized by baseline shoulder width to ensure
    invariance to patient size and distance from the camera.

    Args:
        ear: Ear landmark of the active side.
        shoulder: Shoulder landmark of the active side.
        baseline_ear_shoulder_dist: Calibrated rest vertical distance (y_shoulder - y_ear).
        baseline_shoulder_width: Calibrated distance between left and right shoulders.

    Returns:
        Shrug ratio (non-negative float).
        0.0 = no shrug / normal baseline shoulder height.
        > 0.10 = shoulder has raised upward by >10% of shoulder width.
    """
    if baseline_shoulder_width < 1e-5:
        return 0.0

    # Current vertical distance between ear and shoulder
    current_dist = shoulder.y - ear.y

    # If current_dist < baseline, the shoulder moved upward closer to the ear
    elevation = baseline_ear_shoulder_dist - current_dist

    # Shrug ratio normalized by anatomical shoulder width
    ratio = elevation / baseline_shoulder_width
    return max(0.0, ratio)


def are_landmarks_visible(landmarks: Sequence[Union[Point2D, Point3D]], min_visibility: float = 0.5) -> bool:
    """Check if all provided landmarks meet the minimum confidence threshold.

    Args:
        landmarks: Sequence of Point2D or Point3D objects to check.
        min_visibility: Minimum acceptable visibility score [0.0, 1.0].

    Returns:
        True if every landmark has visibility >= min_visibility, False otherwise.
    """
    return all(lm.visibility >= min_visibility for lm in landmarks)


def calculate_anterior_drift_angle(
    active_shoulder: Point3D,
    other_shoulder: Point3D,
    active_hip: Point3D,
    other_hip: Point3D,
    active_elbow: Point3D,
) -> float:
    """Calculate the 3D out-of-plane forward drift angle (antepulsion) in degrees.

    Uses 3D world coordinates (in meters) to determine the angle between the arm vector
    (shoulder -> elbow) and the patient's anatomical coronal (frontal) plane.

    The coronal plane is spanned by:
      - Lateral vector (from active shoulder across to contralateral shoulder)
      - Spine vector (from hips midpoint to shoulders midpoint)

    The normal vector N to this plane is:
      N = (Lateral x Spine) normalized

    When the arm moves purely in the frontal plane, its projection along N is 0 (0 degrees).
    If the arm drifts forward towards the camera (antepulsion / anterior flexion),
    the out-of-plane deviation angle theta is:
      theta = arcsin( |A . N| / ||A|| )

    Args:
        active_shoulder: 3D position of the exercising shoulder.
        other_shoulder: 3D position of the opposite shoulder.
        active_hip: 3D position of the active side hip.
        other_hip: 3D position of the opposite side hip.
        active_elbow: 3D position of the active side elbow.

    Returns:
        Drift angle in degrees in range [0.0, 90.0].
        Returns 0.0 if vectors are degenerate or arm length is near zero.
    """
    # Lateral vector across shoulders
    lat_x = other_shoulder.x - active_shoulder.x
    lat_y = other_shoulder.y - active_shoulder.y
    lat_z = other_shoulder.z - active_shoulder.z

    # Midpoints
    sh_mid_x = (active_shoulder.x + other_shoulder.x) / 2.0
    sh_mid_y = (active_shoulder.y + other_shoulder.y) / 2.0
    sh_mid_z = (active_shoulder.z + other_shoulder.z) / 2.0

    hip_mid_x = (active_hip.x + other_hip.x) / 2.0
    hip_mid_y = (active_hip.y + other_hip.y) / 2.0
    hip_mid_z = (active_hip.z + other_hip.z) / 2.0

    # Spine vector pointing upwards (hips -> shoulders)
    spine_x = sh_mid_x - hip_mid_x
    spine_y = sh_mid_y - hip_mid_y
    spine_z = sh_mid_z - hip_mid_z

    # Normal to coronal plane via 3D cross product: Lateral x Spine
    nx = (lat_y * spine_z) - (lat_z * spine_y)
    ny = (lat_z * spine_x) - (lat_x * spine_z)
    nz = (lat_x * spine_y) - (lat_y * spine_x)

    norm_n = math.sqrt(nx * nx + ny * ny + nz * nz)
    if norm_n < 1e-7:
        return 0.0

    # Unit normal vector
    nx /= norm_n
    ny /= norm_n
    nz /= norm_n

    # Arm vector (active shoulder -> active elbow)
    arm_x = active_elbow.x - active_shoulder.x
    arm_y = active_elbow.y - active_shoulder.y
    arm_z = active_elbow.z - active_shoulder.z

    arm_len = math.sqrt(arm_x * arm_x + arm_y * arm_y + arm_z * arm_z)
    if arm_len < 1e-7:
        return 0.0

    # Projection along plane normal
    dot = (arm_x * nx) + (arm_y * ny) + (arm_z * nz)
    sin_theta = abs(dot) / arm_len
    clamped_sin = max(-1.0, min(1.0, sin_theta))
    theta_rad = math.asin(clamped_sin)
    return min(90.0, max(0.0, math.degrees(theta_rad)))
