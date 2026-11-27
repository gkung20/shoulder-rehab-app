"""Local webcam coach with shared analysis and a readable dashboard.

The app opens on Willy's home screen. The first time, Willy runs the guided tour (in English
or French); afterwards he greets the patient and the session starts from his Start button.
This file reads the command line; the app itself is `src.desktop_app.App`.
"""
import sys
import argparse
import platform
from dataclasses import replace

from src import __version__, app_log
from src.config import ExerciseConfig
from src.desktop_app import App, show_startup_error, window_size  # noqa: F401  (kept importable from here)
from src.pose_detector import installed_pose_model
from src.user_profile import Profile


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Coach epaule : cadrage serre ou webcam externe large")
    parser.add_argument("--camera", type=int, help="Index camera, par exemple 1 pour une webcam USB")
    parser.add_argument("--width", type=int, help="Largeur de capture demandee, sans recadrage")
    parser.add_argument("--height", type=int, help="Hauteur de capture demandee")
    parser.add_argument("--zoom", type=float, help="Zoom du pilote, si pris en charge (unites du fabricant)")
    parser.add_argument("--model", choices=("lite", "full", "heavy"), help="Modele : full par defaut")
    parser.add_argument("--no-avatars", action="store_true", help="Vue camera seule, sans moteur 3D")
    parser.add_argument("--no-hands", action="store_true", help="Desactiver le suivi detaille des mains")
    parser.add_argument("--hands", action="store_true", help="Activer le suivi detaille des mains (plus lent)")
    parser.add_argument("--tour", action="store_true", help="Rejouer la visite guidee de Willy / replay Willy's tour")
    parser.add_argument("--skip-home", action="store_true", help="Ouvrir directement la seance, sans l'accueil de Willy")
    parser.add_argument("--debug", action="store_true", help="Temps de chaque etape a l'ecran et dans timings.csv")
    return parser, parser.parse_args(argv)


def build_config(parser, args):
    """The exercise configuration with the command-line overrides and an installed pose model."""
    config = ExerciseConfig.from_yaml()
    overrides = {name: getattr(args, arg) for name, arg in (("index", "camera"), ("width", "width"),
                                                            ("height", "height"), ("zoom", "zoom"))
                 if getattr(args, arg) is not None}
    try:
        config = replace(config, camera=replace(config.camera, **overrides),
                         pose=replace(config.pose, model=args.model or config.pose.model))
    except ValueError as exc:
        parser.error(str(exc))
    model = installed_pose_model(config.pose.model)
    if model != config.pose.model:
        print(f"[MODELE] pose_landmarker_{config.pose.model}.task absent : modele {model} utilise. "
              "Pour le suivi le plus precis : python models/download_models.py")
        config = replace(config, pose=replace(config.pose, model=model))
    return config


def main(argv=None):
    parser, args = parse_args(argv)
    journal = app_log.setup()  # %APPDATA%\Mouvement\logs\mouvement.log (Phase 8.3)
    app_log.logger().info("Mouvement %s, Python %s, %s ; journal : %s", __version__, platform.python_version(),
                          platform.platform(), journal.path)
    profile = Profile.load()
    config = build_config(parser, args)
    return App(args, config, profile).run()


if __name__ == '__main__':
    sys.exit(main())
