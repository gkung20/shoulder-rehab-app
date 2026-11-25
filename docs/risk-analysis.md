# Analyse des risques (style ISO 14971)

> **Mouvement est un prototype étudiant, pas un dispositif médical certifié.** Ce document
> organise la réflexion sur les risques et relie chaque mesure à un test ou à une partie de la
> documentation. Avant toute utilisation avec des patients, vérifier avec l'encadrant quelles
> autorisations s'appliquent (comité d'éthique, règles sur les dispositifs médicaux) et faire
> valider les valeurs par un kinésithérapeute.

**Échelles.** Gravité : 1 négligeable, 2 mineure, 3 modérée, 4 grave, 5 critique.
Probabilité : 1 improbable, 2 rare, 3 occasionnelle, 4 probable, 5 fréquente.
Risque = gravité × probabilité ; au-dessus de 8, une mesure est obligatoire.
Les valeurs de probabilité sont des estimations de l'équipe, à revoir après l'étude de validation
(`docs/validation-protocol.md`).

| N° | Danger | Cause | Dommage possible | G | P | Mesure dans l'application | Vérification | Risque résiduel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | Angle mesuré faux | Erreur du modèle, mauvais cadrage, vêtements amples | Effort trop fort ou trop faible ; faux sentiment de progrès | 3 | 3 | Calibration au repos ; seuils de visibilité ; « Mesures partielles » quand un point manque ; angle refusé si la largeur des épaules change trop ; étude de validation préparée | `tests/test_session_processor.py`, `tests/test_geometry.py`, `tests/test_evaluation_reliability.py`, `docs/validation-protocol.md` | Moyen tant que l'étude n'est pas faite |
| R2 | Corps tourné par rapport à la caméra | Patient de trois quarts | Angle 2D sous-estimé | 3 | 3 | Angle refusé si les épaules se rapprochent trop ; vérification « face à la caméra » (Phase 5.6) | `tests/test_session_processor.py` (largeur des épaules), `tests/test_face_check.py` | Faible |
| R3 | Mauvaise personne suivie | Quelqu'un passe derrière le patient | Mouvements comptés à tort, consignes absurdes | 2 | 3 | Verrouillage sur le patient de la calibration (Phase 5.3) | `tests/test_person_lock.py` | Faible |
| R4 | Douleur ignorée, effort excessif | Le patient force pour atteindre la cible | Aggravation de la lésion | 4 | 3 | Question de douleur avant et après (bandes du plan) ; séance douce ou pas de séance ; bouton « J'ai mal » ; arrêt après deux « J'ai mal » ; durée maximale ; pause proposée en cas de fatigue | `tests/test_safety.py`, `tests/test_plan.py` (bandes) | Faible |
| R5 | Chute en position debout | Vertige, fatigue, perte d'équilibre | Chute, blessure | 4 | 2 | Mode assis dans le plan ; consignes de sécurité de Willy à la première utilisation ; durée maximale | `tests/test_safety.py` (mode assis), `tests/test_willy_tour.py` (règles de sécurité) | Faible |
| R6 | Plan mal saisi | Erreur de frappe, valeur extrême | Cible trop haute, trop de répétitions | 3 | 2 | Boutons − / + avec limites sûres ; valeurs remises en ordre ; historique des 20 derniers plans | `tests/test_plan.py`, `tests/test_physio_settings.py` | Faible |
| R7 | Réglages modifiés par quelqu'un d'autre | Proche ou patient curieux | Plan inadapté | 3 | 2 | Code kiné haché (PBKDF2), blocage après cinq erreurs ; **le code 0000 par défaut doit être changé** | `tests/test_physio_settings.py` | Moyen si le code 0000 n'est pas changé |
| R8 | Atteinte à la vie privée | Images de la caméra conservées ou envoyées | Divulgation d'images du domicile ou du corps | 4 | 1 | Aucune image ni vidéo enregistrée ; aucun envoi réseau ; données dans `%APPDATA%\Mouvement` | `tests/test_session_store.py` (nombres seulement), README | Faible |
| R9 | Perte ou corruption des données | Coupure pendant l'écriture | Historique ou plan perdus | 2 | 2 | Écritures atomiques ; fichiers illisibles ignorés ; enregistrement sans bloquer l'exercice | `tests/test_session_store.py`, `tests/test_plan.py` | Faible |
| R10 | Plantage pendant la séance | Erreur logicielle, pilote graphique | Séance perdue, patient perdu | 2 | 3 | Séance enregistrée comme partielle à la fermeture ; journal et écran d'erreur (Phase 8.3) | `tests/test_app_smoke.py`, `tests/test_crash_screen.py` | Faible |
| R11 | Caméra débranchée | Câble, mise en veille | Arrêt brutal de l'application | 2 | 3 | Reconnexion automatique, séance reprise (Phase 5.4) | `tests/test_camera_reconnect.py` | Faible |
| R12 | Patient qui n'entend pas la voix | Surdité, son coupé, voix en panne | Consignes manquées | 3 | 3 | Bulle de Willy et colonne de consignes toujours affichées ; message si la voix ne marche pas (E6.07) ; sous-titres permanents (Phase 10.2) | `tests/test_willy_tour.py`, `tests/test_audio.py` | Faible |
| R13 | Encouragements qui poussent trop | Ton trop insistant | Effort excessif, culpabilité | 2 | 2 | Phrases courtes et bienveillantes (« à votre rythme ») ; aucun reproche pour un jour manqué ; Willy propose une pause en cas de fatigue et conseille d'appeler le kiné si la douleur augmente | `tests/test_willy_lines.py`, `tests/test_safety.py`, `tests/test_results_history.py` | Faible |
| R14 | Consigne mal comprise | Langue, vocabulaire | Mouvement mal fait | 2 | 2 | Français et anglais ; démonstration de Willy ; silhouette guide | `tests/test_willy_lines.py`, `tests/test_physio_settings.py` (textes traduits) | Faible |

## Bandes de douleur et règles d'arrêt (valeurs par défaut, à confirmer avec un kiné)

| Situation | Réponse de l'application |
| --- | --- |
| Douleur 0 à 3 avant la séance | Séance normale |
| Douleur 4 à 6 avant la séance | Séance douce : cible maximale −10°, 30 % de répétitions en moins |
| Douleur 7 à 10 avant la séance | Pas de séance ; Willy conseille le repos et d'appeler le kiné si cela dure |
| Douleur en hausse de 2 points ou plus après la séance | Willy conseille d'en parler au kiné ; signalé dans l'export |
| « J'ai mal » pendant la séance | Comptage arrêté ; douleur demandée ; repos d'une minute puis séance douce, ou fin |
| Deuxième « J'ai mal » | Fin de la séance |
| Durée maximale du plan atteinte (15 min par défaut) | Fin de la séance avec un mot de Willy |
| Angles en baisse de plus de 15° ou 3 compensations d'affilée | Willy propose une pause (au plus toutes les 3 minutes) |

Ces valeurs se règlent dans les réglages kiné (bandes, durée) et dans `config/exercise_config.yaml`
(section `safety:`).
