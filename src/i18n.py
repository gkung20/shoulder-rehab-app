"""English versions of the patient screen's French text.

The interface is written in French; when the patient picks English, every string drawn on
screen goes through `tr()`. Willy's own lines come from assets/willy/lines.yaml instead.
"""
import re

EN = {
    # Header and panels
    "Épaule / séance guidée": "Shoulder / guided session",
    "VOTRE COACH": "YOUR COACH",
    "CAMÉRA": "CAMERA",
    "VOTRE MOUVEMENT · ESTIMATION": "YOUR MOVEMENT · ESTIMATE",
    "Démonstration": "Demonstration",
    "Suivi partiel · bras au repos": "Partial tracking · arm at rest",
    "En direct": "Live",
    "Au repos · aucun suivi": "At rest · not tracking",
    "Exemple à votre rythme": "Example at your pace",
    "Paume et doigts suivis": "Palm and fingers tracked",
    "Main absente : bras au repos": "No hand visible: arm at rest",
    "RÉPÉTITIONS": "REPETITIONS",
    "Comptées au retour au repos": "Counted back at rest",
    "Son indisponible. Suivez le texte.": "Sound unavailable. Follow the text.",
    "Repos": "Rest", "Lever": "Raise", "Maintenir": "Hold", "Redescendre": "Lower",
    "Certaines mesures de posture ne sont pas disponibles.": "Some posture measurements are not available.",
    "Mesures dans la zone prévue.": "Measurements within the planned zone.",
    "Suivez l’ajustement pour le prochain mouvement.": "Follow the adjustment for the next movement.",
    "Levez, maintenez, puis ramenez le bras au repos.": "Raise, hold, then bring your arm back to rest.",
    "Utilisez les commandes de la page pour mettre en pause ou terminer.": "Use the page controls to pause or finish.",
    "Prototype éducatif · Mesures estimées. Arrêtez en cas de douleur.":
        "Educational prototype · Estimated measurements. Stop if you feel pain.",
    # Guidance (title, body, status) from patient_guidance()
    "Installez-vous": "Get set up",
    "Gardez les deux épaules et le coude visibles. Choisissez votre bras, puis commencez.":
        "Keep both shoulders and your elbow in view. Choose your arm, then start.",
    "AVANT DE COMMENCER": "BEFORE YOU START",
    "En pause": "Paused",
    "Le comptage est arrêté. Reprenez quand vous voulez.": "Counting has stopped. Resume whenever you like.",
    "SÉANCE EN PAUSE": "SESSION PAUSED",
    "Séance terminée": "Session finished",
    "Consultez les mesures ou commencez une nouvelle séance.": "Check the measurements or start a new session.",
    "BILAN": "RESULTS",
    "Gardez le bras baissé": "Keep your arm down",
    "Restez au repos quelques instants pendant le réglage.": "Stay at rest for a few moments while I get set up.",
    "PRÉPARATION": "GETTING READY",
    "Ajustez le cadrage": "Adjust the framing",
    "Replacez les deux épaules et le coude du bras suivi dans l’image.":
        "Bring both shoulders and the tracked elbow back into the picture.",
    "SUIVI INTERROMPU": "TRACKING PAUSED",
    "Montrez le coude": "Show your elbow",
    "Vos épaules sont repérées. Le coude du bras suivi doit aussi rester visible.":
        "Your shoulders are found. The tracked elbow must stay visible too.",
    "CADRAGE": "FRAMING",
    "Baissez le bras": "Lower your arm",
    "Repartez de la position de repos.": "Start again from the resting position.",
    "POSITION DE DÉPART": "STARTING POSITION",
    "Ajustez doucement la position, sans forcer.": "Adjust your position gently, without forcing.",
    "AJUSTEMENT": "ADJUSTMENT",
    "Levez le bras": "Raise your arm",
    "Montez doucement sur le côté, vers votre zone de mouvement.": "Go up gently to the side, toward your movement zone.",
    "EN COURS": "IN PROGRESS",
    "Redescendez": "Lower your arm",
    "Ramenez doucement le bras au repos.": "Gently bring your arm back to rest.",
    "Maintenez": "Hold",
    "Gardez la position un instant, puis redescendez.": "Keep the position for a moment, then lower.",
    "Le mouvement sera compté au retour au repos.": "The movement counts when your arm is back at rest.",
    "À votre rythme": "At your own pace",
    "Levez doucement le bras sur le côté pour commencer le mouvement.": "Gently raise your arm to the side to start.",
    # Help panel
    "Comment faire": "How it works",
    "Willy, votre guide, reste à droite de l’écran et bouge avec vous.":
        "Willy, your guide, stays on the right of the screen and moves with you.",
    "Choisissez votre avatar et le bras suivi en haut de l’écran.":
        "Choose your coach and the tracked arm at the top of the screen.",
    "Vue caméra : « Silhouette » (touche G) montre où vous placer et le geste à suivre.":
        "Camera view: “Silhouette” (G key) shows where to stand and the movement to follow.",
    "Montrez les deux épaules et le coude du bras suivi.": "Show both shoulders and the elbow of the tracked arm.",
    "Commencez, puis gardez le bras baissé quelques instants.": "Start, then keep your arm down for a few moments.",
    "Suivez le coach et le texte : lever, maintenir, redescendre.": "Follow the coach and the text: raise, hold, lower.",
    "Faites une pause quand vous en avez besoin. Arrêtez en cas de douleur.":
        "Take a break whenever you need one. Stop if you feel pain.",
    # Buttons
    "Homme": "Man", "Femme": "Woman", "Bras droit": "Right arm", "Bras gauche": "Left arm",
    "Son activé": "Sound on", "Son coupé": "Sound off", "Commencer": "Start", "Faire une pause": "Pause",
    "Reprendre": "Resume", "Nouvelle séance": "New session", "Terminer": "Finish", "Mon bilan": "My results",
    "Voir la caméra": "Show camera", "Voir les avatars": "Show avatars", "Masquer les mesures": "Hide measurements",
    "Mesures": "Measurements", "Fermer l’aide": "Close help", "Aide": "Help", "Fermer": "Close",
    "Masquer la silhouette": "Hide silhouette", "Revoir la visite": "Replay the tour",
    # Silhouette
    "Placez-vous dans la silhouette": "Stand inside the silhouette",
    "Approchez-vous un peu": "Come a little closer",
    "Reculez un peu": "Step back a little",
    "Décalez-vous vers la droite": "Move to the right",
    "Décalez-vous vers la gauche": "Move to the left",
    "Baissez un peu la caméra": "Lower the camera a little",
    "Montez un peu la caméra": "Raise the camera a little",
    "Bonne position": "Good position",
    "Levez": "Raise",
}

_PATTERNS = [
    (re.compile(r"^Répétition (\d+) comptée\.$"), r"Repetition \1 counted."),
    (re.compile(r"^(\d+) répétitions comptées\. (\d+) avec des mesures complètes\.$"),
     r"\1 repetitions counted. \2 with complete measurements."),
    (re.compile(r"^Bras : (.*?)   ·   Tronc : (.*?)   ·   Épaule : (.*?)   ·   Coude : (.*)$"),
     r"Arm: \1   ·   Trunk: \2   ·   Shoulder: \3   ·   Elbow: \4"),
    (re.compile(r"^Estimation depuis les épaules · Caméra (.*?) · Modèle (.*?) · (\d+) images/s$"),
     r"Estimated from the shoulders · Camera \1 · Model \2 · \3 fps"),
    (re.compile(r"^Angle depuis le tronc · Caméra (.*?) · Modèle (.*?) · (\d+) images/s$"),
     r"Angle from the trunk · Camera \1 · Model \2 · \3 fps"),
    (re.compile(r"^Bras (droit|gauche) · Son (activé|coupé)$"),
     lambda m: f"{'Right' if m.group(1) == 'droit' else 'Left'} arm · Sound {'on' if m.group(2) == 'activé' else 'off'}"),
]


def tr(text, language="fr"):
    """The text in the patient's language (French text is returned unchanged)."""
    if language != "en" or not text:
        return text
    text = str(text)
    if text in EN:
        return EN[text]
    for pattern, replacement in _PATTERNS:
        if pattern.match(text):
            return pattern.sub(replacement, text)
    return text


# Words for the buttons and screens added with Willy's tour, by language.
UI = {
    "next": ("Next", "Suivant"),
    "skip": ("Skip", "Passer"),
    "start_tour": ("Start the tour", "Commencer la visite"),
    "understand": ("I understand", "J'ai compris"),
    "watch_again": ("Watch again", "Revoir"),
    "start": ("Start", "Commencer"),
    "replay_tour": ("Replay the tour", "Revoir la visite"),
    "pause_sample": ("Pause", "Faire une pause"),
    "name_hint": ("Type your first name, then press Enter", "Tapez votre prénom, puis Entrée"),
    "ok": ("OK", "OK"),
    "tagline": ("Your shoulder exercise, guided by Willy", "Votre exercice d'épaule, guidé par Willy"),
}


def ui(key, language="fr"):
    english, french = UI[key]
    return english if language == "en" else french
