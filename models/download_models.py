"""Utility script to download official MediaPipe Pose Landmarker models (.task).

Runs locally once to ensure the application works 100% offline.
"""

from pathlib import Path
import sys
import urllib.request

MODELS = {
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "pose_landmarker_full.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
}


def download_model(model_name: str = "pose_landmarker_lite.task") -> Path:
    """Download the selected MediaPipe model if not already present."""
    if model_name not in MODELS:
        raise ValueError(f"Unknown model: {model_name}. Choices: {list(MODELS.keys())}")

    models_dir = Path(__file__).resolve().parent
    dest_path = models_dir / model_name

    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"[OK] Model already exists: {dest_path.name} ({dest_path.stat().st_size:,} bytes)")
        return dest_path

    url = MODELS[model_name]
    print(f"[DOWNLOADING] {model_name} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "MediaPipeDownloader/1.0"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as f:
        f.write(resp.read())

    print(f"[DONE] Saved model to: {dest_path} ({dest_path.stat().st_size:,} bytes)")
    return dest_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "pose_landmarker_lite.task"
    download_model(target)
