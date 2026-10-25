"""Unit tests for src/geometry.py vector math."""

import math
import pytest

from src.geometry import (
    Point2D,
    calculate_angle_2d,
    calculate_abduction_angle,
    calculate_elbow_angle,
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
    # Right shoulder at (0.4, 0.3), right hip at (0.4, 0.7) - vertical trunk
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
    # Vector (dx, dy) with dx=dy
    elbow_45 = Point2D(0.4 + 0.2, 0.3 + 0.2)
    angle_45 = calculate_abduction_angle(shoulder, hip, elbow_45)
    assert pytest.approx(angle_45, abs=1e-2) == 45.0


def test_calculate_elbow_angle():
    """Test elbow extension angle."""
    shoulder = Point2D(0.4, 0.3)
    elbow = Point2D(0.6, 0.3)
    # Straight arm: wrist continues in same direction
    wrist_straight = Point2D(0.8, 0.3)
    assert pytest.approx(calculate_elbow_angle(shoulder, elbow, wrist_straight), abs=1e-2) == 180.0

    # 90-degree bent elbow
    wrist_bent = Point2D(0.6, 0.5)
    assert pytest.approx(calculate_elbow_angle(shoulder, elbow, wrist_bent), abs=1e-2) == 90.0


def test_are_landmarks_visible():
    """Verify confidence visibility gating."""
    lm1 = Point2D(0.5, 0.5, visibility=0.9)
    lm2 = Point2D(0.6, 0.6, visibility=0.7)
    lm3 = Point2D(0.7, 0.7, visibility=0.4)

    assert are_landmarks_visible([lm1, lm2], min_visibility=0.6) is True
    assert are_landmarks_visible([lm1, lm2, lm3], min_visibility=0.6) is False
