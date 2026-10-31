"""Unit tests for src/geometry.py vector math."""

import math
import pytest

from src.geometry import (
    Point2D,
    Point3D,
    calculate_angle_2d,
    calculate_abduction_angle,
    calculate_elbow_angle,
    calculate_distance_2d,
    get_midpoint,
    calculate_trunk_lean,
    calculate_shoulder_shrug,
    calculate_anterior_drift_angle,
    are_landmarks_visible,
)


def test_calculate_angle_2d_orthogonal():
    """Verify right angle (90 deg) calculation."""
    vertex = Point2D(0.5, 0.5)
    p1 = Point2D(0.5, 0.9)  # Downwards vector (0, 0.4)
    p2 = Point2D(0.9, 0.5)  # Rightwards vector (0.4, 0)

    angle = calculate_angle_2d(vertex, p1, p2)
    assert pytest.approx(angle, abs=1e-3) == 90.0


def test_calculate_angle_2d_collinear_same_direction():
    """Verify angle between coincident/parallel vectors is 0 deg."""
    vertex = Point2D(0.5, 0.5)
    p1 = Point2D(0.5, 0.8)
    p2 = Point2D(0.5, 0.9)

    angle = calculate_angle_2d(vertex, p1, p2)
    assert pytest.approx(angle, abs=1e-3) == 0.0


def test_calculate_angle_2d_opposite_direction():
    """Verify angle between opposing collinear vectors is 180 deg."""
    vertex = Point2D(0.5, 0.5)
    p1 = Point2D(0.5, 0.9)  # Downwards
    p2 = Point2D(0.5, 0.1)  # Upwards

    angle = calculate_angle_2d(vertex, p1, p2)
    assert pytest.approx(angle, abs=1e-3) == 180.0


def test_calculate_angle_2d_degenerate_zero_length():
    """Verify zero division is safely handled when points coincide."""
    vertex = Point2D(0.5, 0.5)
    p1 = Point2D(0.5, 0.5)
    p2 = Point2D(0.8, 0.8)

    angle = calculate_angle_2d(vertex, p1, p2)
    assert angle == 0.0


def test_calculate_abduction_angle_rest_and_horizontal():
    """Test abduction angle for anatomically representative positions."""
    shoulder = Point2D(0.4, 0.3)
    hip = Point2D(0.4, 0.7)

    # Rest position: elbow straight down along side
    elbow_rest = Point2D(0.4, 0.55)
    angle_rest = calculate_abduction_angle(shoulder, hip, elbow_rest)
    assert pytest.approx(angle_rest, abs=1e-2) == 0.0

    # 90 degrees horizontal abduction: arm points out to the right
    elbow_90 = Point2D(0.65, 0.3)
    angle_90 = calculate_abduction_angle(shoulder, hip, elbow_90)
    assert pytest.approx(angle_90, abs=1e-2) == 90.0

    # 45 degrees abduction
    elbow_45 = Point2D(0.4 + 0.2, 0.3 + 0.2)
    angle_45 = calculate_abduction_angle(shoulder, hip, elbow_45)
    assert pytest.approx(angle_45, abs=1e-2) == 45.0


def test_calculate_elbow_angle():
    """Test elbow extension angle."""
    shoulder = Point2D(0.4, 0.3)
    elbow = Point2D(0.6, 0.3)
    wrist_straight = Point2D(0.8, 0.3)
    assert pytest.approx(calculate_elbow_angle(shoulder, elbow, wrist_straight), abs=1e-2) == 180.0

    wrist_bent = Point2D(0.6, 0.5)
    assert pytest.approx(calculate_elbow_angle(shoulder, elbow, wrist_bent), abs=1e-2) == 90.0


def test_calculate_trunk_lean():
    """Test lateral trunk lean relative to gravity vertical."""
    # Perfectly upright torso
    l_sh = Point2D(0.4, 0.2)
    r_sh = Point2D(0.6, 0.2)
    l_hip = Point2D(0.4, 0.7)
    r_hip = Point2D(0.6, 0.7)

    lean_upright = calculate_trunk_lean(l_sh, r_sh, l_hip, r_hip)
    assert pytest.approx(lean_upright, abs=1e-2) == 0.0

    # Tilted torso 45 degrees: shoulders shifted rightwards by 0.5
    # Midpoint of hips = (0.5, 0.7), midpoint of shoulders = (0.5 + 0.5, 0.7 - 0.5) = (1.0, 0.2)
    # dx = 0.5, dy = -0.5 -> angle with vertical (0, -1) = 45 degrees
    l_sh_tilted = Point2D(0.9, 0.2)
    r_sh_tilted = Point2D(1.1, 0.2)
    lean_tilted = calculate_trunk_lean(l_sh_tilted, r_sh_tilted, l_hip, r_hip)
    assert pytest.approx(lean_tilted, abs=1e-2) == 45.0


def test_calculate_shoulder_shrug():
    """Test normalized shoulder shrug ratio."""
    # Baseline setup: ear at y=0.10, shoulder at y=0.25 (dist = 0.15), shoulder width = 0.30
    baseline_ear_shoulder_dist = 0.15
    baseline_shoulder_width = 0.30

    ear = Point2D(0.5, 0.10)

    # 1. At rest: shoulder still at y=0.25 -> shrug ratio = 0.0
    shoulder_rest = Point2D(0.5, 0.25)
    shrug_rest = calculate_shoulder_shrug(ear, shoulder_rest, baseline_ear_shoulder_dist, baseline_shoulder_width)
    assert pytest.approx(shrug_rest, abs=1e-4) == 0.0

    # 2. Shrugged: shoulder raised up to y=0.20 (closer to ear by 0.05)
    # Shrug ratio = 0.05 / 0.30 = 0.1667 (16.7% of shoulder width)
    shoulder_shrugged = Point2D(0.5, 0.20)
    shrug_val = calculate_shoulder_shrug(ear, shoulder_shrugged, baseline_ear_shoulder_dist, baseline_shoulder_width)
    assert pytest.approx(shrug_val, abs=1e-3) == (0.05 / 0.30)

    # 3. Shoulder pushed down lower: clamped at 0.0
    shoulder_lowered = Point2D(0.5, 0.30)
    assert calculate_shoulder_shrug(ear, shoulder_lowered, baseline_ear_shoulder_dist, baseline_shoulder_width) == 0.0


def test_are_landmarks_visible():
    """Verify confidence visibility gating."""
    lm1 = Point2D(0.5, 0.5, visibility=0.9)
    lm2 = Point2D(0.6, 0.6, visibility=0.7)
    lm3 = Point2D(0.7, 0.7, visibility=0.4)

    assert are_landmarks_visible([lm1, lm2], min_visibility=0.6) is True
    assert are_landmarks_visible([lm1, lm2, lm3], min_visibility=0.6) is False


def test_calculate_anterior_drift_3d():
    """Verify 3D out-of-plane forward drift calculations relative to coronal plane."""
    r_sh = Point3D(x=-0.2, y=0.5, z=0.0)
    l_sh = Point3D(x=0.2, y=0.5, z=0.0)
    r_hip = Point3D(x=-0.15, y=0.0, z=0.0)
    l_hip = Point3D(x=0.15, y=0.0, z=0.0)

    # 1. Pure coronal horizontal abduction (no forward or backward drift)
    el_coronal = Point3D(x=-0.5, y=0.5, z=0.0)
    drift_coronal = calculate_anterior_drift_angle(r_sh, l_sh, r_hip, l_hip, el_coronal)
    assert pytest.approx(drift_coronal, abs=1e-3) == 0.0

    # 2. 30 degrees anterior drift towards camera
    # Arm length = 0.3, dx = -0.3 * cos(30 deg), dz = 0.3 * sin(30 deg)
    el_30deg = Point3D(
        x=-0.2 - (0.3 * math.cos(math.radians(30.0))),
        y=0.5,
        z=0.3 * math.sin(math.radians(30.0)),
    )
    drift_30 = calculate_anterior_drift_angle(r_sh, l_sh, r_hip, l_hip, el_30deg)
    assert pytest.approx(drift_30, abs=1e-2) == 30.0

    # 3. Pure forward flexion (90 deg out of plane)
    el_forward = Point3D(x=-0.2, y=0.5, z=0.3)
    drift_90 = calculate_anterior_drift_angle(r_sh, l_sh, r_hip, l_hip, el_forward)
    assert pytest.approx(drift_90, abs=1e-2) == 90.0

    # 4. Rest position (arm hanging straight down along torso)
    el_rest = Point3D(x=-0.2, y=0.2, z=0.0)
    drift_rest = calculate_anterior_drift_angle(r_sh, l_sh, r_hip, l_hip, el_rest)
    assert pytest.approx(drift_rest, abs=1e-3) == 0.0

    # 5. Degenerate zero-length arm
    drift_degen = calculate_anterior_drift_angle(r_sh, l_sh, r_hip, l_hip, r_sh)
    assert drift_degen == 0.0
