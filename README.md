# 🦾 Assistant Intelligent de Réhabilitation : Abduction Active de l'Épaule

## Mise à jour : comptage, suivi et affichage

**Pour un patient sur ce PC :** double-cliquez sur **`Ouvrir Mouvement.cmd`**.
La fenêtre s’ouvre sans commande à saisir. Choisissez le bras, puis cliquez sur
**Commencer**. Le comptage attend ce clic. Les boutons **Faire une pause**,
**Reprendre**, **Terminer** et **Fermer** se pilotent à la souris. L’aide met
automatiquement le suivi en pause ; sa fermeture ne relance pas le mouvement.
La fenêtre peut être agrandie : l’interface garde ses proportions avec des marges
si nécessaire, et les boutons restent alignés avec les clics de la souris.
Le texte et les contrôles sont dessinés directement à la résolution de la fenêtre,
avec gestion du DPI Windows, sans agrandir une image fixe de l’interface. La
présentation utilise une palette neutre, des séparateurs fins et moins de blocs.
Tous les boutons ont un contour rectangulaire ; les sélections sont légèrement
ombrées et les actions indisponibles sont atténuées.
La netteté de la vidéo reste limitée par la résolution et l’éclairage de la webcam.

L’écran principal montre une seule consigne et un grand compteur. Les mesures,
le squelette et les informations techniques sont accessibles avec **Mesures**.
Dans Streamlit, ils sont regroupés dans **Réglages avancés** et les
exports détaillés restent dans **Mon bilan**. Une pause arrête l’analyse et
interrompt la tentative en cours sans inventer une répétition terminée.

La voix est **plus lente et discrète par défaut** : une aide de préparation,
puis des corrections persistantes seulement, au moins huit secondes entre
annonces et quarante secondes avant de répéter la même consigne. Elle ne lit plus
chaque phase ni chaque résultat ; un rappel est donné tous les cinq mouvements.
Le texte reste disponible en continu. **Voix discrète**, **Sans voix** et
**Guidage complet**, ainsi que les vitesses **Lente / Très lente**, sont proposés
dans Streamlit.

Le modèle **MediaPipe Full** est maintenant utilisé par défaut. L'application
accepte un cadrage serré : **les deux épaules suffisent pour la calibration**,
puis le coude du bras actif doit être visible pour compter. Le visage et les
hanches ne sont plus obligatoires dans les règles de démarrage de l'application.

Le coaching vocal utilise maintenant **Piper et une voix neuronale française
Siwis** en local. Après installation des dépendances, téléchargez la voix une fois :

```powershell
python -m piper.download_voices fr_FR-siwis-medium --data-dir models/voices
```

Les consignes sont accentuées pour la prononciation, plus courtes, et les anciens
messages sont remplacés au lieu de s'accumuler. **A** coupe/réactive la voix.
Le volume et le rythme sont réglables dans Streamlit ou dans la section `audio`
du fichier YAML. Aucun texte ni image n'est envoyé à un service vocal.
Voir [la voix française et son installation](models/voices/README.md).

L'application OpenCV utilise un tableau de bord séparant la vidéo, les consignes,
le compteur, les mesures et le dernier résultat. La calibration demande un bras
au repos et des articulations visibles ; ses instructions restent affichées et
un nouvel essai démarre automatiquement après un mouvement excessif.

Une tentative sous la cible est maintenant comptée et expliquée. Une mesure
manquante donne **INDETERMINE**, sans succès ni échec inventé. Les interruptions
longues sont affichées séparément. L'affichage miroir ne change plus le bras
anatomique analysé. OpenCV, Streamlit et l'évaluation vidéo partagent le même
processeur et la même horloge de trames.

```powershell
# Environnement existant dans ce projet
.\.env\Scripts\python.exe app_live_cv.py

# Webcam USB / virtuelle grand-angle : choisir son index et une résolution supportée
.\.env\Scripts\python.exe app_live_cv.py --camera 1 --width 1920 --height 1080

# Si le Full est trop lent : modèle Lite déjà téléchargé séparément
.\.env\Scripts\python.exe app_live_cv.py --model lite

# Installation avec les versions de l'environnement Windows / Python 3.13 testé
python -m pip install -r requirements.txt -c constraints-windows-py313.txt

# Interface locale Streamlit
python -m streamlit run app_streamlit.py
```

Cliquez sur **Commencer** et gardez les deux épaules dans le cadre. Attendez la fin de la calibration, puis
montrez le coude actif et levez et redescendez le bras : le compteur augmente au
retour au repos. **C** relance la calibration ; **L/R** sélectionnent le bras.
Dans Streamlit, les réglages sont verrouillés pendant la capture et le bouton
**Terminer ma séance** libère la caméra. La caméra et la voix utilisent l'ordinateur serveur,
ce mode est destiné à une utilisation locale.

Sans hanches visibles, l'angle est une **estimation à partir de la ligne des
épaules**, indiquée à l'écran et dans les exports. Les contrôles du tronc, du
haussement et de la profondeur restent non évalués quand leurs repères manquent.
Les répétitions sont comptées, mais ne reçoivent pas un verdict de qualité complet.
Un changement de référence pendant un mouvement interrompt cette tentative et
demande un retour au repos pour recommencer.

La caméra, la résolution, le modèle et le zoom facultatif sont aussi sélectionnables
dans Streamlit avant de démarrer. La résolution effective est affichée. Le zoom
utilise les unités du pilote et peut être indisponible. Un champ de vision plus
large nécessite une caméra qui le fournit ; augmenter la résolution ne suffit pas.
L'image complète est affichée sans recadrage central.

**Limite du modèle :** MediaPipe peut encore échouer si la tête est entièrement
hors champ, même si notre application ne la demande plus. Le cadrage serré est une
possibilité de traitement des repères détectés, pas une garantie de détection sans
tête. Voir la [fiche officielle du modèle](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf).

La fluidité est un indicateur expérimental, exclu de la notation par défaut.
Les exports conservent les réglages, la calibration et l'identifiant du modèle.
L'évaluation affiche la couverture et des résultats par participant/condition,
sans prétendre prouver l'absence de biais.

Voir [la démarche de validation et la préparation de l'avatar](docs/validation-and-avatar.md).
Le personnage animé est prévu pour une étape ultérieure ; le moteur de suivi est
déjà séparé du rendu pour permettre cette évolution.

> **Projet Universitaire de 3ème Année - Spécialité Santé Numérique (Digital Health)**  
> *Auteur : Étudiant ingénieur (Profil Développement de Jeux & Vision par Ordinateur)*  
> *Encadrement : Ingénieur Senior & Mentor en Vision par Ordinateur*

---

> [!WARNING]
> ### ⚠️ Avertissement Médical et Portée Pédagogique
> Ce logiciel est un **prototype expérimental à vocation strictement éducative**. Il **ne constitue pas un dispositif médical certifié** et ne doit pas être utilisé pour établir un diagnostic médical ou prescrire un traitement de rééducation clinique.
> 
> **CONSIGNE DE SÉCURITÉ POUR LE PATIENT :**
> **ARRÊTEZ IMMÉDIATEMENT L'EXERCICE si vous ressentez une douleur vive, un tiraillement inhabituel ou une sensation de blocage articulaire.** Consultez toujours un kinésithérapeute diplômé d'État ou un médecin rééducateur avant de débuter tout protocole de réhabilitation.

---

## 🎯 1. Périmètre & Objectifs du Projet

L'application a pour objectif d'assister un patient réalisant à domicile un exercice de kinésithérapie ciblé : **l'abduction active de l'épaule dans le plan frontal** (élévation latérale du bras), un bras à la fois (sélectionnable gauche ou droite).

À l'aide d'une simple webcam standard, le système :
1. Détecte la posture squelettique en temps réel sans capteur intrusif (via **MediaPipe Tasks PoseLandmarker**).
2. Mesure l'angle d'abduction et les compensations motrices posturales.
3. Guide le patient par des consignes orales/écrites en français (*"Levez un peu plus le bras"*, *"Gardez l'épaule basse"*, *"Gardez le tronc droit"*).
4. Compte les répétitions complètes grâce à une **machine à états finis munie d'hystérésis**.
5. Fournit un bilan complet de fin de séance (taux de réussite, erreurs posturales fréquentes, export CSV).

---

## 📐 2. Modélisation Biomécanique & Géométrique

Les concepts exploitent des principes fondamentaux de développement de jeux (moteurs physiques, squelettes hiérarchiques et interpolation) :

```
             Tête / Oreille (7, 8)
                   │
    Épaule D (12) ─── Épaule G (11)   <--- Haussement (Shrug) = Δd(Oreille-Épaule) / Largeur Épaules
         │                 │
         │ (Vecteur Bras)   │
         ▼                 │
    Coude D (14)           │ (Vecteur Tronc)
         │                 │
         ▼                 ▼
    Poignet D (16)     Hanche G (23) / Hanche D (24)
                           ▲
                           │ Inclinaison du tronc (Lean) relative à la verticale (0, -1)
```

| Métrique | Formule / Définition Mathématique | Règle Clinique (Valeurs Indicatives) |
| :--- | :--- | :--- |
| **Angle d'Abduction** | Angle 2D entre le vecteur tronc $(\text{Hanche} - \text{Épaule})$ et le vecteur bras $(\text{Coude} - \text{Épaule})$. | Cible : $[80^\circ, 100^\circ]$. Repos : $\le 25^\circ$. |
| **Haussement d'Épaule (Shrug)** | $\text{Ratio} = \frac{d_{\text{repos}}(\text{Oreille}, \text{Épaule}) - d_{\text{actuelle}}(\text{Oreille}, \text{Épaule})}{W_{\text{repos}}(\text{Épaule G}, \text{Épaule D})}$ | Alerte si $\text{Ratio} > 0.12$ ($> 12\%$ de la largeur d'épaules). |
| **Inclinaison du Tronc (Lean)** | Angle entre l'axe rachidien $(M_{\text{épaules}} - M_{\text{hanches}})$ et la verticale ascendante $(0, -1)$. | Alerte si déviation $> 10.0^\circ$. |
| **Extension du Coude** | Angle 3-points $\text{Épaule} - \text{Coude} - \text{Poignet}$. | Alerte si angle $< 155.0^\circ$ (bras fléchi pour tricher l'inertie). |
| **Dérive 3D Hors Plan (Antépulsion)** | Angle $\theta = \arcsin\left(\frac{\|\vec{A} \cdot \vec{N}_{\text{coronal}}\|}{\|\vec{A}\|}\right)$ via repères 3D métriques MediaPipe. | Alerte si dérive $> 25.0^\circ$ (projection du bras vers l'avant). |
| **Fluidité Motrice (Jerk Normalisé)** | Dérivée 3ème du déplacement $j(t) = \frac{d^3\theta}{dt^3}$ normalisée sans dimension. | Indicateur expérimental, exclu de la notation par défaut ; aucune valeur si les échantillons sont insuffisants. |
| **Machine à États (FSM)** | Hystérésis : déclenchement montée $\ge 32^\circ$, maintien dans la zone cible, comptage au retour $\le 25^\circ$. | Compte aussi les tentatives sous la cible ; rejette le comptage d’une tentative interrompue par une perte de suivi prolongée. |
| **Lissage Temporel (EMA)** | $S_t = \alpha X_t + (1 - \alpha) S_{t-1}$ (équivalent à un `lerp()` avec $\alpha = 0.35$). | Rejette les images de faible visibilité $(< 0.60)$. |

> [!IMPORTANT]
> **Tous les seuils ci-dessus sont des VALEURS INDICATIVES (PLACEHOLDERS)** centralisées dans [`config/exercise_config.yaml`](config/exercise_config.yaml). Ils doivent être validés avec votre kinésithérapeute référent.

---

## 🛠️ 3. Technologies & Pile Logicielle

- **Langage :** Python 3.10+ (vérifié sous Python 3.13)
- **Vision par Ordinateur :** MediaPipe Tasks `PoseLandmarker`, modèle Full par défaut ; coordonnées 2D et estimations 3D.
- **Traitement d'Image & Affichage :** OpenCV et Pillow, dessin à la résolution native de la fenêtre.
- **Calcul Vectoriel & Biomécanique :** NumPy, math (Jerk normalisé)
- **Biofeedback Vocal (TTS) :** Piper + Siwis en local, lecture via SoundDevice ; voix Windows française via `pyttsx3` en secours.
- **Bilans du Prototype :** ReportLab et Matplotlib, exports PDF, CSV et JSON avec contexte d’acquisition.
- **Interface Utilisateur Web :** Streamlit avec mises à jour vidéo par fragments.
- **Configuration :** PyYAML
- **Tests & Assurance Qualité :** Pytest (tests unitaires, intégration et contrôles de l'interface)
- **Gestion de Version :** Git & GitHub

---

## 📁 4. Architecture Modulaire du Code

```text
shoulder-rehab-app/
│
├── config/
│   └── exercise_config.yaml    # Source unique de vérité pour les seuils biomécaniques
│
├── models/
│   ├── download_models.py      # Script de téléchargement local du modèle MediaPipe (.task)
│   ├── voices/                 # Documentation et modèle vocal local Siwis (binaires ignorés)
│   └── pose_landmarker_full.task (Modèle Full par défaut, ignoré par git)
│
├── src/
│   ├── __init__.py
│   ├── config.py               # Chargeur fortement typé (dataclasses) du fichier YAML
│   ├── capture.py              # Abstraction de la webcam, calcul FPS et mode miroir
│   ├── pose_detector.py        # Wrapper MediaPipe Tasks PoseLandmarker (2D + 3D World Landmarks)
│   ├── geometry.py             # Calculs vectoriels 2D, dérivées du mouvement (Jerk) et dérive 3D hors plan
│   ├── smoothing.py            # Filtre EMA (Exponential Moving Average) anti-gigue
│   ├── calibration.py          # Enregistrement des mesures de référence au repos (3 sec)
│   ├── state_machine.py        # Machine à états finis (REST/RISING/HOLD/LOWERING) & télémétrie de fluidité
│   ├── rules_engine.py         # Moteur de règles cliniques et retours en français
│   ├── session_processor.py    # Pipeline commun OpenCV, Streamlit et évaluation vidéo
│   ├── dashboard.py            # Interface patient minimale dessinée à la résolution native
│   ├── patient_controls.py     # Boutons et états de la séance, communs au rendu et aux clics
│   ├── window_viewport.py      # Proportions, DPI et conversion des coordonnées de souris
│   ├── speech.py               # Synthèse Piper locale et secours Windows français
│   ├── audio_feedback.py       # Voix discrète : priorité, rythme et suppression des répétitions
│   ├── live_session.py         # Ressources caméra/modèle/audio et pause dans Streamlit
│   ├── report_generator.py     # Générateur de bilans cliniques PDF avec graphiques doubles
│   └── visualizer.py           # Dessin du squelette, HUD médical et alertes visuelles
│
├── data/
│   ├── recorded_clips/         # Stockage local des clips MP4 de test
│   └── annotations/            # Fichiers CSV de vérité terrain et rapports de métriques
│
├── tests/
│   ├── test_environment.py     # Vérification des dépendances et du modèle MediaPipe
│   ├── test_geometry.py        # Tests des calculs 2D, dérive 3D et fluidité motrice
│   ├── test_smoothing.py       # Tests du filtre exponentiel et rejet d'images bruitées
│   ├── test_calibration.py     # Tests de la routine de calibration posturale
│   ├── test_state_machine.py   # Tests sur trajectoires synthétiques (répétitions/hystérésis/jerk)
│   ├── test_rules_engine.py    # Tests des seuils cliniques, antépulsion et messages
│   ├── test_audio.py           # Tests du coach vocal hors ligne et de la régulation de fréquence
│   ├── test_report_generator.py# Tests de génération du document PDF médical
│   ├── test_session_processor.py # Régressions du pipeline commun et du suivi
│   ├── test_closeup_and_camera.py # Cadrage serré, caméra externe et mesures manquantes
│   ├── test_evaluation_reliability.py # Accord des pipelines et couverture d’évaluation
│   ├── test_french_speech.py    # Synthèse réelle de la voix française, sans lecture sonore
│   ├── test_patient_controls.py # Parcours à la souris et dessin à la résolution native
│   ├── test_window_viewport.py  # Plein écran, proportions, clics et DPI
│   ├── test_live_ui.py          # Commandes Streamlit et libération des ressources
│   └── test_phase5_ui.py       # Tests des structures de données du tableau de bord
│
├── Ouvrir Mouvement.cmd        # Lanceur Windows par double-clic, sans saisie dans un terminal
├── app_live_cv.py              # Interface patient OpenCV avec boutons et coaching discret
├── app_streamlit.py            # Séance patient et exports, réglages avancés repliés
├── evaluate_dataset.py         # Script d'évaluation hors ligne (Matrice de confusion)
├── record_clip.py              # Outil d'enregistrement éthique avec recueil de consentement
├── demo.py                     # Démonstrateur autonome (4 scénarios simulés ou caméra directe)
├── requirements.txt            # Dépendances ; contraintes Windows dans un fichier séparé
├── constraints-windows-py313.txt # Versions de l’environnement Windows testé
├── docs/validation-and-avatar.md # Limites, évaluation et évolution de l’avatar
└── README.md                   # Documentation du projet
```

---

## 🚀 5. Installation & Guide de Démarrage

### 5.1 Cloner le dépôt et créer l'environnement virtuel
```powershell
# Cloner le projet depuis GitHub
git clone https://github.com/gkung20/shoulder-rehab-app.git
cd shoulder-rehab-app

# Créer un environnement virtuel Python
python -m venv .env

# Activer l'environnement virtuel (Windows PowerShell)
.\.env\Scripts\Activate.ps1
```

### 5.2 Installer les dépendances & télécharger le modèle
```powershell
# Installer les bibliothèques requises (Windows / Python 3.13)
python -m pip install -r requirements.txt -c constraints-windows-py313.txt

# Télécharger localement MediaPipe Full (environ 9,4 Mo)
python models/download_models.py

# Télécharger la voix française locale (environ 63 Mo)
python -m piper.download_voices fr_FR-siwis-medium --data-dir models/voices
```

### 5.3 Exécuter la suite de tests automatisée
```powershell
# Tests unitaires, intégration et contrôles de l'interface
pytest tests/ -v
```

La CI Windows installe ces dépendances, télécharge les deux modèles et exécute les
tests. Les tests synthétiques et les contrôles d’interface ne remplacent pas une
validation sur webcam ou sur des participants représentatifs.

---

## 🎮 6. Utilisation de l'Application

### Option A : Démonstration Rapide (Sans Webcam ou Mode Direct)
```powershell
# Mode simulation automatique (4 scénarios biomécaniques : correct, postural, vitesse et dérive 3D)
python demo.py

# Mode caméra en direct
python demo.py --live
```

### Option B : Application Directe OpenCV (`app_live_cv.py`)
Interface locale utilisable à la souris ; les performances dépendent du PC et du modèle choisi :
```powershell
python app_live_cv.py
```
Les boutons à l’écran suffisent. Raccourcis clavier facultatifs :
- **`Espace`** : Commencer / Faire une pause / Reprendre
- **`L`** : Sélectionner le bras **GAUCHE**
- **`R`** : Sélectionner le bras **DROIT**
- **`C`** : Lancer la **CALIBRATION** (maintenez la position de repos pendant 3 secondes)
- **`A`** : Activer / Désactiver le **COACHING VOCAL EN FRANÇAIS (TTS)**
- **`S`** : Terminer la séance et afficher le bilan
- **`D`** : Afficher / Masquer les mesures
- **`H`** : Ouvrir / Fermer l’aide (le suivi reste en pause)
- **`M`** : Activer / Désactiver le mode miroir
- **`Q`** ou **`Échap`** : Quitter proprement

### Option C : Tableau de Bord Web Streamlit (`app_streamlit.py`)
Interface complète destinée au patient et au kinésithérapeute :
```powershell
streamlit run app_streamlit.py
```
- Ouvrez `http://localhost:8501` dans votre navigateur.
- Choisissez votre bras et l’accompagnement vocal, puis cliquez sur **Commencer ma séance**.
- Suivez la consigne écrite. Les mesures et réglages de l’exercice sont facultatifs, dans **Réglages avancés**.
- Faites une pause ou terminez avec les boutons. Consultez **Mon bilan** pour enregistrer le PDF.
- Exportez les observations et leur contexte en **CSV / JSON**, ou le **bilan PDF du prototype**.

---

## 🧪 7. Évaluation Hors Ligne & Validation Clinique

Le projet intègre un pipeline complet d'évaluation de la qualité :

### Étape 1 : Enregistrement d'un clip de test avec consentement
```powershell
python record_clip.py
```
*Le script invite le participant à confirmer son consentement éclairé, consigne le type de mouvement (correct ou compensation intentionnelle) et sauvegarde la vidéo dans `data/recorded_clips/` avec son annotation dans `data/annotations/ground_truth.csv`.*

### Étape 2 : Évaluation par lot et calcul de la Matrice de Confusion
```powershell
python evaluate_dataset.py
```
*Le script traite chaque vidéo hors ligne et génère :*
- La **Matrice de Confusion** ($2 \times 2$) dans la console.
- Les métriques : **Exactitude (Accuracy)**, **Sensibilité (Recall)**, **Spécificité**, **Précision**, **F1-Score**.
- Les rapports CSV détaillés dans `data/annotations/evaluation_details.csv` et `evaluation_metrics.csv`.
- Les résultats par participant/condition dans `evaluation_groups.csv`, avec les clips non évaluables et la couverture du suivi. Les résultats indéterminés sont exclus des scores d’accord.

---

## ⚠️ 8. Limites Techniques & Biomécaniques

1. **Projection 2D dans le plan frontal :** L'estimation est réalisée à partir d'une caméra monoculaire standard. L'abduction scapulaire pure s'effectue physiologiquement à environ $30^\circ$ en avant du plan frontal (plan de la scapula). Une rotation du buste par rapport à la caméra peut fausser légèrement l'angle mesuré.
2. **Ambiguïté de profondeur :** La distance caméra-patient est compensée par la normalisation anatomique (largeur bi-acromiale), mais une avancée ou un recul violent pendant l'exercice peut introduire un bruit transitoire.
3. **Conditions d'éclairage & vêtements :** Les vêtements très amples peuvent masquer les repères articulaires de l'épaule et du coude, réduisant le score de confiance de MediaPipe.

---

## 🔮 9. Perspectives & Travaux Futurs

- Intégration d'autres exercices de l'épaule (antépulsion, rotation externe coude au corps).
- Fusion multimodale avec des capteurs inertiels miniatures (IMU Bluetooth / montre connectée).
- Portail clinicien en ligne sécurisé permettant au kinésithérapeute d'ajuster les programmes d'exercices à distance.
- Export direct au format de données de santé (HL7 / FHIR).

---

## 📚 10. Licences & Références Citées

Références et attributions du projet. Les mesures publiées par ces projets ne constituent pas une validation de ce prototype :

1. **Google MediaPipe :** Pose Landmarker Tasks API ([Documentation Officielle](https://developers.google.com/mediapipe)) — *Licence Apache 2.0*.
2. **NgoQuocBao1010/Exercise-Correction :** Architecture de pipeline de correction d'exercices ([GitHub](https://github.com/NgoQuocBao1010/Exercise-Correction)) — *Licence MIT*.
3. **Pythonpreran/Posecheck-Pro :** Analyse d'angles articulaires et retours d'exercices ([GitHub](https://github.com/Pythonpreran/Posecheck-Pro)) — *Licence MIT*.
4. **Python-kunal/physio_app :** Structuration logicielle pour applications de kinésithérapie ([GitHub](https://github.com/Python-kunal/physio_app)) — *Licence MIT*.
5. **sing1ee/my-pose :** Normalisation géométrique de poses squelettiques ([GitHub](https://github.com/sing1ee/my-pose)) — *Licence MIT*.
6. **IEEE DataPort :** *"Shoulder Exercise Quality Dataset"* (Vidéos annotées d'exercices d'abduction/adduction de l'épaule) — *Accès de recherche académique IEEE DataPort*.
7. **Piper / Siwis :** moteur vocal local et voix française ; sources et licences dans [models/voices/README.md](models/voices/README.md).
