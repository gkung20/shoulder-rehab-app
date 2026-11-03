"""Offline evaluation must agree with the live processor, including unknowns."""
import csv
import numpy as np
import pytest

import evaluate_dataset as dataset
from tests.test_session_processor import body, config, run_sequence


def test_offline_pipeline_uses_video_time_and_same_rules(monkeypatch):
    angles = [0]*30 + [i*1.5 for i in range(61)] + [90]*30 + [90-i*1.5 for i in range(1,61)] + [0]*10

    class Capture:
        def __init__(self,*args):
            self.index = 0
            self.released = False
        def isOpened(self):
            return True
        def get(self,*args):
            return 30.
        def read(self):
            if self.index >= len(angles):
                return False,None
            frame = np.zeros((480,640,3),np.uint8)
            frame[0,0,0] = self.index // 256
            frame[0,0,1] = self.index % 256
            self.index += 1
            return True,frame
        def release(self):
            self.released = True

    capture = Capture()

    class Detector:
        def __init__(self, **kwargs):
            assert kwargs["model_variant"] == "full"
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
        def detect(self,image,timestamp):
            index = int(image[0,0,0])*256 + int(image[0,0,1])
            pts,self.last_world_landmarks = body(angles[index])
            return pts

    monkeypatch.setattr(dataset.cv2,"VideoCapture",lambda *args: capture)
    monkeypatch.setattr(dataset,"PoseDetector",Detector)
    offline,label = dataset.analyze_video_file("synthetic.mp4",config=config())
    _, live = run_sequence()
    assert label == "CORRECT"
    assert capture.released
    assert len(offline) == len(live) == 1
    assert offline[0].metrics.peak_abduction_deg == pytest.approx(live[0].metrics.peak_abduction_deg)
    assert offline[0].metrics.hold_duration_sec == pytest.approx(live[0].metrics.hold_duration_sec)


def test_group_metrics_report_coverage_and_false_approvals():
    rows = [
        {"arm":"right","participant_id":"p1","ground_truth_label":"A CORRIGER","predicted_label":"CORRECT"},
        {"arm":"right","participant_id":"p2","ground_truth_label":"CORRECT","predicted_label":"INDETERMINE"},
        {"arm":"left","participant_id":"p3","ground_truth_label":"CORRECT","predicted_label":"CORRECT"},
    ]
    groups = dataset.summarize_groups(rows)
    right = next(g for g in groups if g["dimension"] == "arm" and g["group"] == "right")
    assert right["assessed"] == 1
    assert right["unassessed"] == 1
    assert right["coverage_percent"] == 50
    assert right["false_approvals"] == 1
    unknown = next(g for g in groups if g["dimension"] == "participant_id" and g["group"] == "p2")
    assert unknown["accuracy_percent"] == ""


def test_missing_files_are_included_in_coverage_and_detail_reports(tmp_path,monkeypatch):
    annotations = tmp_path / "ground_truth.csv"
    annotations.write_text("video_file,arm,ground_truth_label,participant_id\nmissing.mp4,right,CORRECT,p1\n",encoding="utf-8")
    monkeypatch.setattr(dataset,"CLIPS_DIR",tmp_path)
    monkeypatch.setattr(dataset,"OUTPUT_DETAILS_CSV",tmp_path / "details.csv")
    monkeypatch.setattr(dataset,"OUTPUT_GROUPS_CSV",tmp_path / "groups.csv")
    cm = dataset.compute_dataset_metrics(annotations)
    assert cm.total == 0
    assert cm.unassessed == 1
    with open(tmp_path / "details.csv",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    assert rows[0]["predicted_label"] == "ERREUR_FICHIER"
    assert rows[0]["agreement"] == ""
