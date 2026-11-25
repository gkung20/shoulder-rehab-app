"""Patient-facing controls shared by the drawing and native mouse hit testing."""
from dataclasses import dataclass

from src import layout as L


@dataclass(frozen=True)
class PatientButton:
    action: str
    label: str
    bounds: tuple
    enabled: bool = True
    selected: bool = False
    primary: bool = False
    tone: str = ""        # "pain": the calm, warm "J'ai mal" button


LANGUAGE_BUTTON = L.LANGUAGE_BUTTON


def patient_buttons(mode="running", arm="right", audio_enabled=True, details=False, help_visible=False, avatars=True, avatar_gender="male",
                    silhouette=False, language="fr", results=False):
    """Every button of the patient screen. Labels are French; the screen translates them when drawing."""
    primary = {"ready": ("start", "Commencer"), "running": ("pause", "Faire une pause"),
               "paused": ("resume", "Reprendre"), "finished": ("restart", "Nouvelle séance")}[mode]
    buttons = [
        PatientButton("avatar_male", "Homme", L.AVATAR_MALE_BUTTON, selected=avatar_gender == "male"),
        PatientButton("avatar_female", "Femme", L.AVATAR_FEMALE_BUTTON, selected=avatar_gender == "female"),
        PatientButton("arm_right", "Bras droit", L.ARM_RIGHT_BUTTON, mode in ("ready","paused"), arm == "right"),
        PatientButton("arm_left", "Bras gauche", L.ARM_LEFT_BUTTON, mode in ("ready","paused"), arm == "left"),
        PatientButton("audio", "Son activé" if audio_enabled else "Son coupé", L.AUDIO_BUTTON, selected=audio_enabled),
        PatientButton(*primary, L.MAIN_BUTTON, primary=True),
        # "Terminer" during a session; "Mon bilan" (a saved session's results) otherwise.
        PatientButton("finish" if mode in ("running","paused") else "results",
                      "Terminer" if mode in ("running","paused") else "Mon bilan", L.FINISH_BUTTON,
                      mode in ("running","paused") or results),
        PatientButton("avatars", "Voir la caméra" if avatars else "Voir les avatars", L.VIEW_BUTTON, selected=avatars),
        # During a session this place belongs to "J'ai mal" (key P); "Mesures" stays on key D.
        (PatientButton("hurt", "J'ai mal", L.DETAILS_BUTTON, tone="pain") if mode in ("running", "paused") else
         PatientButton("details", "Masquer les mesures" if details else "Mesures", L.DETAILS_BUTTON, selected=details)),
        PatientButton("help", "Fermer l’aide" if help_visible else "Aide", L.HELP_BUTTON, selected=help_visible),
        PatientButton("quit", "Fermer", L.QUIT_BUTTON),
        # The other language, written in that language: always readable by whoever needs it.
        PatientButton("language", "Français" if language == "en" else "English", LANGUAGE_BUTTON),
    ]
    if help_visible:
        buttons.append(PatientButton("replay_tour", "Revoir la visite", L.REPLAY_TOUR_BUTTON))
    if not avatars and not help_visible:
        # Small toggle in the camera view's top-right corner.
        buttons.append(PatientButton("silhouette", "Masquer la silhouette" if silhouette else "Silhouette",
                                     L.SILHOUETTE_ON_BUTTON if silhouette else L.SILHOUETTE_OFF_BUTTON, selected=silhouette))
    return buttons


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
    avatars: bool = True
    avatar_gender: str = "male"
    silhouette: bool = False

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
        if action == "avatars":
            self.avatars = not self.avatars
            return True
        if action == "silhouette":
            self.silhouette = not self.silhouette
            return True
        if action in ("avatar_male","avatar_female"):
            self.avatar_gender=action.removeprefix("avatar_")
            return True
        if action == "help":
            self.help_visible = not self.help_visible
            if self.help_visible and self.mode == "running":
                self.mode = "paused"
            return True
        if action in ("arm_left","arm_right"):
            return self.mode in ("ready","paused")
        if action == "replay_tour":
            self.help_visible = False
            return True
        return action in ("audio","quit","mirror","language")
