# Willy, le guide

Willy est la mascotte qui accompagne le patient. Il est **toujours visible** à
droite de l’écran, à côté du compteur de répétitions : avant la séance, pendant
la calibration, en pause, au bilan, dans la vue avatars comme dans la vue caméra,
avec `--no-avatars` et dans la page Streamlit (barre latérale + tableau de bord).

## Ce qu’il fait

| Moment | Willy |
| --- | --- |
| Avant de commencer | Salue de la main toutes les 7 s |
| Calibration, cadrage, suivi perdu | Reste calme, bras baissés |
| Mouvement | Lève le **même bras que le patient, du même côté de l’écran** (miroir), à l’angle d’abduction déjà mesuré |
| Maintien atteint | Yeux souriants |
| Avertissement de posture | Penche la tête |
| Répétition conforme | Lève les deux bras et sautille |
| Répétition à ajuster | Hoche la tête pour encourager, jamais de visage triste |
| Bilan | Fête la fin de séance |
| Voix en cours | Bouche animée pendant que la phrase est jouée |

Willy ne fait que **refléter** l’analyse : rien de ce qu’il affiche n’entre dans
le comptage ou l’évaluation.

## Voix de Willy

La voix française Piper locale est transformée en voix de dessin animé
(hauteur et timbre plus aigus). Le texte est synthétisé plus lentement puis
rééchantillonné : le débit reste celui de `length_scale`.

```yaml
audio:
  willy_pitch: 1.30   # 1.0 = voix naturelle, jusqu’à 1.6
```

Écouter un extrait sans caméra :

```powershell
python -m src.audio_feedback --preview output/voix_willy.wav
```

La voix Windows de secours (pyttsx3) n’est pas transformée.

## Rendu

Willy n’utilise pas le moteur 3D : `src/willy.py` assemble 54 calques PNG
pré-rendus (`assets/willy/`, ~1 Mo) avec NumPy/OpenCV (quelques ms par image).
Tête, bras gauche/droit (0–160° par pas de 10°, plus 5 images de salut) et corps
sont superposés ; la tête s’incline autour du cou.

Pour modifier le modèle (`tools/willy_sprites/willy_model.js`) puis régénérer
les calques :

```powershell
python -m pip install playwright
python -m playwright install chromium
python tools/willy_sprites/render_sprites.py
```
