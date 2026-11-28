"""English versions of the patient screen's French text.

The interface is written in French; when the patient picks English, every string drawn on
screen goes through `tr()`. Willy's own lines come from assets/willy/lines.yaml instead.
"""
import re

EN = {
    # Physio settings and PIN pad
    "Réglages kiné": "Physio settings",
    "Code kiné": "Physio PIN",
    "Nouveau code (4 chiffres)": "New PIN (4 digits)",
    "Confirmez le nouveau code": "Confirm the new PIN",
    "Effacer": "Delete",
    "Annuler": "Cancel",
    "Code incorrect.": "Wrong PIN.",
    "Trop d'essais. Réessayez dans une minute.": "Too many tries. Try again in a minute.",
    "Les deux codes sont différents. Recommencez.": "The two PINs differ. Start again.",
    "Le plan du patient. Chaque valeur reste dans des limites sûres.": "The patient's plan. Every value stays within safe limits.",
    "Bras": "Arm",
    "Cible minimale": "Target minimum",
    "Cible maximale": "Target maximum",
    "Repos maximal": "Rest maximum",
    "Maintien": "Hold",
    "Répétitions par série": "Repetitions per set",
    "Séries": "Sets",
    "Repos entre les séries": "Rest between sets",
    "Séances par semaine": "Sessions per week",
    "Durée maximale d'une séance": "Longest session",
    "Douleur : séance normale jusqu'à": "Pain: normal session up to",
    "Douleur : séance douce jusqu'à": "Pain: gentle session up to",
    "Exercice assis": "Seated exercise",
    "Au choix du patient": "Patient's choice",
    "Droit": "Right",
    "Gauche": "Left",
    "Oui": "Yes",
    "Non": "No",
    "Changer le code": "Change the PIN",
    "Enregistrer": "Save",
    "Code modifié.": "PIN changed.",
    "Pause entre les séries": "Rest between sets",
    # Results and history
    "MOUVEMENTS": "MOVEMENTS", "MEILLEUR ANGLE": "BEST ANGLE", "ANGLE MOYEN": "AVERAGE ANGLE", "DURÉE": "DURATION",
    "Aucun mouvement compté.": "No movement counted.",
    "Correct": "Correct", "À corriger": "To improve", "Non mesuré": "Not measured", "Zone cible": "Target zone",
    "Retour": "Back", "Historique": "History", "Les 30 derniers jours": "The last 30 days",
    "Pas de série en cours": "No streak right now",
    "MEILLEUR ANGLE PAR JOUR": "BEST ANGLE PER DAY",
    "Pas encore de séance enregistrée.": "No session saved yet.",
    "MOUVEMENTS PAR JOUR": "MOVEMENTS PER DAY",
    "DOULEUR AVANT LA SÉANCE (0-10)": "PAIN BEFORE THE SESSION (0-10)",
    "7 jours": "7 days", "30 jours": "30 days", "Tout": "All", "Exporter": "Export",
    "Mes résultats": "My results",
    "Ouvrir le dossier": "Open the folder",
    # Pain check and safety
    "J'ai mal": "It hurts", "Aucune douleur": "No pain", "Douleur maximale": "Worst pain",
    "Repos 1 minute, puis en douceur": "Rest 1 minute, then gently", "Terminer la séance": "End the session",
    "Arrêtez l'exercice si la douleur augmente.": "Stop the exercise if the pain gets worse.",
    "Pause après la douleur": "Break after the pain", "Quand vous voulez": "Whenever you like",
    "Appuyez sur Reprendre pour continuer en douceur.": "Press Resume to carry on gently.",
    "PAUSE": "BREAK",
    "Caméra (numéro)": "Camera (number)",
    "Modèle de suivi": "Tracking model", "Automatique": "Automatic", "Précis": "Accurate", "Rapide": "Fast",
    "Auto (rapide)": "Auto (fast)",
    # the error screen (Phase 8.3)
    "Un problème est survenu.": "Something went wrong.",
    "Vos résultats sont enregistrés. Fermez l'application puis relancez-la. Si cela recommence, montrez le "
    "journal à votre kiné.": "Your results are saved. Close the app and start it again. If it happens again, "
                             "show the log to your physio.",
    "Vos résultats n'ont pas pu être enregistrés. Fermez l'application puis relancez-la. Si cela recommence, "
    "montrez le journal à votre kiné.": "Your results could not be saved. Close the app and start it again. If "
                                        "it happens again, show the log to your physio.",
    "Ouvrir le dossier du journal": "Open the log folder",
    "Willy parle": "Willy talks", "Beaucoup": "A lot", "Normalement": "Normally", "Peu": "A little",
    "Exercice": "Exercise", "Les deux": "Both",
    "Cette semaine": "This week",
    "Première séance": "First session", "3 jours de suite": "3 days in a row",
    "Semaine complète": "Full week", "100 mouvements": "100 movements",
    "Plan du patient": "Patient's plan", "Écran et voix": "Screen and voice",
    "Grand texte": "Large text", "Contraste élevé": "High contrast", "Voix plus lente": "Slower voice",
    "Sous-titres toujours": "Subtitles always",
    # Body of the guide silhouette (Phase 11, src.physio_settings.SILHOUETTE_LABELS)
    "Corps de la silhouette": "Silhouette body", "Actuelle": "Current",
    "Nouvelle, femme": "New, woman", "Nouvelle, homme": "New, man",
    # Guidance for the both-arm exercise (src.dashboard.BOTH_ARMS_TEXT)
    "Gardez les deux épaules et les deux coudes visibles, puis commencez.":
        "Keep both shoulders and both elbows in view, then start.",
    "Gardez les bras baissés": "Keep your arms down",
    "Replacez les deux épaules et les deux coudes dans l’image.": "Bring both shoulders and both elbows back into the picture.",
    "Montrez les coudes": "Show your elbows",
    "Vos épaules sont repérées. Vos deux coudes doivent aussi rester visibles.":
        "Your shoulders are found. Both elbows must stay in view too.",
    "Baissez les bras": "Lower your arms",
    "Levez les deux bras": "Raise both arms",
    "Montez doucement sur les côtés, en même temps, vers votre zone de mouvement.":
        "Raise them gently out to the sides, together, toward your movement zone.",
    "Ramenez doucement les bras au repos.": "Gently bring your arms back to rest.",
    "Levez doucement les deux bras sur les côtés pour commencer le mouvement.":
        "Gently raise both arms out to the sides to start the movement.",
    "Levez, maintenez, puis ramenez les bras au repos.": "Raise, hold, then bring your arms back to rest.",
    "Deux bras": "Both arms",
    "Montez les deux bras à la même hauteur": "Raise both arms to the same height",
    "Modèle rapide utilisé (ce PC est lent pour le modèle précis)":
        "Fast model in use (this PC is slow for the accurate model)",
    "Je me prépare…": "Getting ready…", "Préparation des avatars 3D…": "Preparing the 3D avatars…",
    "Démarrage de la caméra…": "Starting the camera…", "Chargement du suivi du mouvement…": "Loading movement tracking…",
    "Préparation de ma voix…": "Preparing my voice…",
    "Caméra déconnectée, reconnexion…": "Camera disconnected, reconnecting…",
    "L'export n'a pas pu être enregistré.": "The export could not be saved.",
    "REPOS": "REST",
    "PRÊT À REPRENDRE": "READY TO RESUME",
    "Appuyez sur Reprendre quand vous le souhaitez.": "Press Resume whenever you like.",
    "Le repos mesuré est proche de la cible : le plan garde ses valeurs. Baissez la cible minimale ou relevez le repos maximal.":
        "The measured rest is close to the target, so the plan keeps its values. Lower the target minimum or raise the rest maximum.",
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
    (re.compile(r"^Reprise possible dans (\d+) s\. Relâchez l'épaule et respirez\.$"),
     r"You can resume in \1 s. Relax your shoulder and breathe."),
    (re.compile(r"^Série (\d+)/(\d+)$"), r"Set \1/\2"),
    (re.compile(r"^Caméra n° (\d+) introuvable\.$"), r"Camera number \1 not found."),
    (re.compile(r"^Conseil : (.*)$"), r"Tip: \1"),
    (re.compile(r"^Douleur : (.*)$"), r"Pain: \1"),
    (re.compile(r"^(\d+) jour\(s\) d'affilée$"), r"\1 day(s) in a row"),
    (re.compile(r"^Fichiers enregistrés dans (.*)$"), r"Files saved in \1"),
    (re.compile(r"^SÉRIE (\d+)/(\d+)$"), r"SET \1/\2"),
    (re.compile(r"^Trop d'essais\. Réessayez dans (\d+) s\.$"), r"Too many tries. Try again in \1 s."),
    (re.compile(r"^Angle de repos mesuré : (.*)$"), r"Measured resting angle: \1"),
    (re.compile(r"^Mesuré le (.*)$"), r"Measured on \1"),
    (re.compile(r"^Modèle « (.*) » non installé\.$"), r"Model “\1” is not installed."),
    (re.compile(r"^(\d+(?:[.,]\d+)?) (s|min)$"), r"\1 \2"),
    (re.compile(r"^(\d+(?:[.,]\d+)?)/10$"), r"\1/10"),
    (re.compile(r"^Bras (droit|gauche) · Son (activé|coupé)$"),
     lambda m: f"{'Right' if m.group(1) == 'droit' else 'Left'} arm · Sound {'on' if m.group(2) == 'activé' else 'off'}"),
    (re.compile(r"^Deux bras · Son (activé|coupé)$"),
     lambda m: f"Both arms · Sound {'on' if m.group(1) == 'activé' else 'off'}"),
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
    "start_tour": ("Full tour", "Visite complète"),
    "express_tour": ("Express tour", "Visite express"),
    "back": ("Back", "Retour"),
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
