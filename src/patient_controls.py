"""Patient-facing controls shared by the drawing and native mouse hit testing."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PatientButton:
    action: str
    label: str
    bounds: tuple
    enabled: bool = True
    selected: bool = False
    primary: bool = False


def patient_buttons(mode="running", arm="right", audio_enabled=True, details=False, help_visible=False):
    primary = {"ready": ("start", "Commencer"), "running": ("pause", "Faire une pause"),
               "paused": ("resume", "Reprendre"), "finished": ("restart", "Nouvelle séance")}[mode]
    return [
        PatientButton("arm_right", "Bras droit", (728,22,876,76), mode in ("ready","paused"), arm == "right"),
        PatientButton("arm_left", "Bras gauche", (884,22,1032,76), mode in ("ready","paused"), arm == "left"),
        PatientButton("audio", "Son activé" if audio_enabled else "Son coupé", (1070,22,1248,76), selected=audio_enabled),
        PatientButton(*primary, (32,750,248,806), primary=True),
        PatientButton("finish", "Terminer" if mode in ("running","paused") else "Mon bilan", (264,750,420,806), mode in ("running","paused")),
        PatientButton("details", "Masquer les mesures" if details else "Mesures", (630,750,814,806), selected=details),
        PatientButton("help", "Fermer l’aide" if help_visible else "Aide", (830,750,998,806), selected=help_visible),
        PatientButton("quit", "Fermer", (1096,750,1248,806)),
    ]


def dashboard_action_at(x, y, **state):
    for button in patient_buttons(**state):
        left,top,right,bottom = button.bounds
        if button.enabled and left <= x < right and top <= y < bottom:
            return button.action
    return None


@dataclass
class PatientControls:
    mode: str = "ready"
    details: bool = False
    help_visible: bool = False

    def apply(self, action):
        """Return whether an action is valid; resource effects belong to the app."""
        transitions = {("ready","start"): "running", ("running","pause"): "paused",
                       ("paused","resume"): "running", ("running","finish"): "finished",
                       ("paused","finish"): "finished", ("finished","restart"): "ready"}
        if (self.mode,action) in transitions:
            self.mode = transitions[self.mode,action]
            self.help_visible = False
            return True
        if action == "details":
            self.details = not self.details
            return True
        if action == "help":
            self.help_visible = not self.help_visible
            if self.help_visible and self.mode == "running":
                self.mode = "paused"
            return True
        if action in ("arm_left","arm_right"):
            return self.mode in ("ready","paused")
        return action in ("audio","quit","mirror")
