# 🦾 Assistant Intelligent de Réhabilitation : Abduction Active de l'Épaule

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
| **Fluidité Motrice (Jerk Normalisé)** | Dérivée 3ème du déplacement $j(t) = \frac{d^3\theta}{dt^3}$ normalisée sans dimension. | Score $[0, 100\%]$ ; alerte si $< 60\%$ (mouvement saccadé / tremblement). |
| **Machine à États (FSM)** | Hystérésis : déclenchement montée $> 32^\circ$, maintien $\ge 80^\circ$, validation retour $\le 25^\circ$. | Élimine les faux comptages causés par le bruit des capteurs. |
| **Lissage Temporel (EMA)** | $S_t = \alpha X_t + (1 - \alpha) S_{t-1}$ (équivalent à un `lerp()` avec $\alpha = 0.35$). | Rejette les images de faible visibilité $(< 0.60)$. |

> [!IMPORTANT]
> **Tous les seuils ci-dessus sont des VALEURS INDICATIVES (PLACEHOLDERS)** centralisées dans [`config/exercise_config.yaml`](file:///C:/Users/hp/shoulder-rehab-app/config/exercise_config.yaml). Ils doivent être validés avec votre kinésithérapeute référent.

---

## 🛠️ 3. Technologies & Pile Logicielle

- **Langage :** Python 3.10+ (testé sous Python 3.14)
- **Vision par Ordinateur :** MediaPipe Tasks (`PoseLandmarker` v1.1.1, repères 2D normalisés + repères 3D métriques `pose_world_landmarks`)
- **Traitement d'Image & Affichage :** OpenCV (`opencv-python` 5.0+)
- **Calcul Vectoriel & Biomécanique :** NumPy, math (Jerk normalisé)
- **Biofeedback Vocal (TTS) :** `pyttsx3` (Synthèse vocale SAPI5 hors ligne en français avec file d'attente non bloquante)
- **Génération de Bilans Médicaux :** `reportlab` & Matplotlib (PDF clinique prêt à imprimer avec graphiques doubles)
- **Interface Utilisateur Web :** Streamlit 1.66+
- **Configuration :** PyYAML
- **Tests & Assurance Qualité :** Pytest (51 tests unitaires & d'intégration)
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
│   └── pose_landmarker_lite.task (Fichier binaire du modèle, ignoré par git)
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
│   ├── audio_feedback.py      # Coach vocal hors-ligne non-bloquant en français (SAPI5/pyttsx3)
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
│   └── test_phase5_ui.py       # Tests des structures de données du tableau de bord
│
├── app_live_cv.py              # Application autonome OpenCV HUD (~30-60 FPS) avec coaching vocal
├── app_streamlit.py            # Tableau de bord clinique Streamlit complet avec exports CSV & PDF
├── evaluate_dataset.py         # Script d'évaluation hors ligne (Matrice de confusion)
├── record_clip.py              # Outil d'enregistrement éthique avec recueil de consentement
├── demo.py                     # Démonstrateur autonome (4 scénarios simulés ou caméra directe)
├── requirements.txt            # Dépendances verrouillées
└── README.md                   # Documentation complète du projet
```

---

## 🚀 5. Installation & Guide de Démarrage

### 5.1 Cloner le dépôt et créer l'environnement virtuel
```powershell
# Cloner le projet depuis GitHub
git clone https://github.com/gkung20/shoulder-rehab-app.git
cd shoulder-rehab-app

# Créer un environnement virtuel Python
python -m venv venv

# Activer l'environnement virtuel (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

### 5.2 Installer les dépendances & télécharger le modèle
```powershell
# Installer les bibliothèques requises
pip install -r requirements.txt

# Télécharger localement le modèle MediaPipe Tasks (5.7 Mo)
python models/download_models.py
```

### 5.3 Exécuter la suite de tests automatisée
```powershell
# 51 tests unitaires et d'intégration validant chaque module mathématique et biomécanique
pytest tests/ -v
```

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
Idéal pour un retour visuel ultra-fluide et une latence minimale sur PC portable :
```powershell
python app_live_cv.py
```
**Contrôles clavier :**
- **`L`** : Sélectionner le bras **GAUCHE**
- **`R`** : Sélectionner le bras **DROIT**
- **`C`** : Lancer la **CALIBRATION** (maintenez la position de repos pendant 3 secondes)
- **`A`** : Activer / Désactiver le **COACHING VOCAL EN FRANÇAIS (TTS)**
- **`S`** : Afficher / Masquer la **FICHE BILAN DE SÉANCE**
- **`M`** : Activer / Désactiver le mode miroir
- **`Q`** ou **`Échap`** : Quitter proprement

### Option C : Tableau de Bord Web Streamlit (`app_streamlit.py`)
Interface complète destinée au patient et au kinésithérapeute :
```powershell
streamlit run app_streamlit.py
```
- Ouvrez `http://localhost:8501` dans votre navigateur.
- Ajustez les curseurs cliniques (ROM cible, compensations, seuil de fluidité motrice).
- Visualisez le squelette en temps réel avec consignes orales/écrites en français.
- Consultez l'onglet **Bilan & Statistiques** pour analyser le graphique des compensations.
- Téléchargez au choix : le fichier brut **CSV** ou le **Bilan Kinésithérapique officiel en PDF** haute définition !

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

Toutes les ressources utilisées sont libres et open source. Nous remercions les auteurs des projets inspirants suivants :

1. **Google MediaPipe :** Pose Landmarker Tasks API ([Documentation Officielle](https://developers.google.com/mediapipe)) — *Licence Apache 2.0*.
2. **NgoQuocBao1010/Exercise-Correction :** Architecture de pipeline de correction d'exercices ([GitHub](https://github.com/NgoQuocBao1010/Exercise-Correction)) — *Licence MIT*.
3. **Pythonpreran/Posecheck-Pro :** Analyse d'angles articulaires et retours d'exercices ([GitHub](https://github.com/Pythonpreran/Posecheck-Pro)) — *Licence MIT*.
4. **Python-kunal/physio_app :** Structuration logicielle pour applications de kinésithérapie ([GitHub](https://github.com/Python-kunal/physio_app)) — *Licence MIT*.
5. **sing1ee/my-pose :** Normalisation géométrique de poses squelettiques ([GitHub](https://github.com/sing1ee/my-pose)) — *Licence MIT*.
6. **IEEE DataPort :** *"Shoulder Exercise Quality Dataset"* (Vidéos annotées d'exercices d'abduction/adduction de l'épaule) — *Accès de recherche académique IEEE DataPort*.
