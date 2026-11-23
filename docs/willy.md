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

C’est la voix choisie à l’essai : **« Cartoon buddy »**. Même recette, en français :

1. une voix masculine de base : Piper **`fr_FR-tom-medium`** (l’essai utilisait
   Ryan, sa voix équivalente en anglais) ;
2. hauteur **et** timbre montés de **1,45×**, comme une bande accélérée ;
3. un léger **vibrato** à 6 Hz (profondeur 0,08, comme `vibrato=f=6:d=0.08`).

Le texte est synthétisé 1,45× plus lentement avant la transformation : le débit
reste celui de `length_scale` (lent et clair pour les patients).

```yaml
audio:
  voice: fr_FR-tom-medium
  willy_pitch: 1.45   # 1.0 = voix naturelle, jusqu’à 1.6
```

Télécharger la voix (avec les modèles MediaPipe) puis écouter un extrait sans caméra :

```powershell
python models/download_models.py
python -m src.audio_feedback --preview output/voix_willy.wav
```

Si la voix Tom manque, l’application prend une autre voix Piper française déjà
installée, puis la voix Windows française (de préférence masculine, « Paul ») :
dans tous les cas, la transformation de Willy est appliquée.

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
