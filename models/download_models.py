"""Utility script to download official MediaPipe Pose Landmarker models (.task).

Runs locally once to ensure the application works 100% offline.
"""

from pathlib import Path
import sys
import urllib.request

MODELS = {
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "pose_landmarker_full.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
    "pose_landmarker_heavy.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
}


def download_model(model_name: str = "pose_landmarker_full.task") -> Path:
    """Download the selected MediaPipe model if not already present."""
    if model_name not in MODELS:
        raise ValueError(f"Unknown model: {model_name}. Choices: {list(MODELS.keys())}")

    models_dir = Path(__file__).resolve().parent
    dest_path = models_dir / model_name

    if dest_path.exists() and dest_path.stat().st_size > 1_000_000:
        print(f"[OK] Model already exists: {dest_path.name} ({dest_path.stat().st_size:,} bytes)")
        return dest_path

    url = MODELS[model_name]
    print(f"[DOWNLOADING] {model_name} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "MediaPipeDownloader/1.0"})
    # Download atomically so an interrupted transfer never becomes the active model.
    temporary = dest_path.with_suffix(".task.part")
    with urllib.request.urlopen(req, timeout=60) as resp, open(temporary, "wb") as f:
        while block := resp.read(1024 * 1024):
            f.write(block)
    if temporary.stat().st_size < 1_000_000:
        raise RuntimeError("Downloaded model is incomplete; retry the download")
    temporary.replace(dest_path)

    print(f"[DONE] Saved model to: {dest_path} ({dest_path.stat().st_size:,} bytes)")
    return dest_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "pose_landmarker_full.task"
    download_model(target)
