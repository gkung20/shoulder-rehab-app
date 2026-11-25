"""Download everything the app needs once, then it runs 100% offline.

    python models/download_models.py            # pose model + hand model + Willy's two voices
    python models/download_models.py voice      # only Willy's French voice (Piper "tom")
    python models/download_models.py voice-en   # only Willy's English voice (Piper "ryan")
    python models/download_models.py pose_landmarker_lite.task

MediaPipe models come from Google's model storage; the voice from the Piper voices repository.
"""

from pathlib import Path
import sys
import urllib.request

MODELS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
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


WILLY_VOICE = "fr_FR-tom-medium"
WILLY_ENGLISH_VOICE = "en_US-ryan-medium"  # licence: non-commercial, check before distributing


def download_voice(name: str = WILLY_VOICE) -> Path:
    """One of Willy's base voices (male Piper voice, ~64 MB), into models/voices."""
    from piper.download_voices import download_voice as piper_download
    voices = Path(__file__).resolve().parent / "voices"
    voices.mkdir(parents=True, exist_ok=True)
    target = voices / f"{name}.onnx"
    if target.exists() and target.with_suffix(".onnx.json").exists():
        print(f"[OK] Voice already exists: {target.name}")
        return target
    print(f"[DOWNLOADING] voice {name}...")
    piper_download(name, voices)
    print(f"[DONE] Saved voice to: {target}")
    return target


if __name__ == "__main__":
    # lite: the faster model the app switches to on a slow PC (Phase 6.4)
    targets = sys.argv[1:] or ["pose_landmarker_full.task", "pose_landmarker_lite.task", "hand_landmarker.task",
                               "voice", "voice-en"]
    for target in targets:
        if target == "voice":
            download_voice()
        elif target == "voice-en":
            download_voice(WILLY_ENGLISH_VOICE)
        elif target.startswith(("fr_FR-", "en_US-", "en_GB-")):
            download_voice(target)
        else:
            download_model(target)
