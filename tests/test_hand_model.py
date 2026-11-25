"""Phase 6.5: the optional hand model runs only when asked for (it costs about 12 ms a frame)."""
from dataclasses import replace

import src.desktop_app as desktop
from tests.app_fakes import ScriptedWindow, make_app


def test_the_hand_model_runs_only_when_asked_for(monkeypatch, tmp_path):
    hand_file = tmp_path / "hand_landmarker.task"
    hand_file.write_bytes(b"x")
    monkeypatch.setattr(desktop, "HAND_MODEL_PATH", hand_file)
    created = []
    monkeypatch.setattr(desktop, "HandDetector", lambda: created.append(1) or _Hands())
    cases = ((("--no-avatars",), False, False),            # default: off, even though it is installed
             (("--no-avatars", "--hands"), False, True),   # asked on the command line
             (("--no-avatars",), True, True),              # asked in the config
             (("--no-avatars", "--hands", "--no-hands"), True, False))  # --no-hands always wins
    for args, in_config, expected in cases:
        created.clear()
        app = make_app(monkeypatch, tmp_path, ScriptedWindow(), args=args)
        app.config = replace(app.config, performance=replace(app.config.performance, hand_model=in_config))
        app.start()
        app.close()
        assert bool(created) is expected, (args, in_config)


class _Hands:
    def detect(self, *args):
        return {}

    def close(self):
        pass
