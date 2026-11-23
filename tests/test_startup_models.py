"""The app opens with whichever pose model is on the computer, preferring the configured one."""
from src.pose_detector import installed_pose_model


def test_missing_configured_model_falls_back_to_an_installed_one(tmp_path):
    assert installed_pose_model("full", tmp_path) == "full"  # nothing installed: the download message stays
    (tmp_path / "pose_landmarker_lite.task").write_bytes(b"x")
    assert installed_pose_model("full", tmp_path) == "lite"
    (tmp_path / "pose_landmarker_full.task").write_bytes(b"x")
    assert installed_pose_model("full", tmp_path) == "full"
    assert installed_pose_model("lite", tmp_path) == "lite"
