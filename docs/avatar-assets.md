# Personnages locaux

L’application native utilise les trois téléchargements placés dans `alo/` :

| Rôle | Nom du fichier |
| --- | --- |
| Médecin démonstrateur | `Stylized_Man_Doctor_-_Mixamo_Rigged_Character.glb` |
| Utilisateur homme | `Stylized_Male_Character_-_Game_Ready_Base_mesh.glb` |
| Utilisateur femme | `Stylized_Female_Character_Game_Ready_Base_mesh.glb` |

Les ZIP et images de fond ne sont pas nécessaires au rendu. Les GLB sont lus sans
modification ; les corrections sont appliquées en mémoire. Ce répertoire et les
archives sont ignorés par Git. Les fichiers téléchargés ne sont donc pas inclus
dans le dépôt. Pour une installation ailleurs, fournir les trois GLB séparément.
Si des fichiers manquent, les mannequins procéduraux servent de secours.

Ces téléchargements fournis par l’utilisateur ne contiennent pas de fichier de
licence. Leur provenance et leurs conditions de redistribution ne sont pas
établies ici ; conserver les liens d’origine avant de les distribuer avec l’app.
Ils ne sont pas présentés comme des modèles CC0 ou issus de MakeHuman/Gobkit.

## Correction de l’import

Les fichiers contiennent un squelette et des poids valides, mais les exports
FBX/GLB ajoutent des rotations et échelles de scène autour des articulations.
Le premier essai via un Actor Panda3D entraînait des étirements importants.

`src/rigged_avatar.py` utilise les positions de liaison obtenues depuis les
matrices inverses de liaison. La conversion glTF Y vertical vers Panda3D Z
vertical est appliquée une seule fois. Les trois personnages sont normalisés
à la même hauteur et les pieds sont placés au sol. Les rotations rigides du bras
et de l’avant-bras sont propagées aux articulations descendantes, puis les
positions et normales sont déformées par les poids existants. Les textures
intégrées sont chargées directement, sans téléchargement ni conversion externe.

Le lecteur couvre le sous-ensemble utilisé par ces fichiers : GLB 2 non compressé,
un squelette, triangles, textures intégrées, quatre poids par sommet, noms de
bras de ces modèles ou du médecin Mixamo. Il ne remplace pas un importeur glTF
général. Les modèles à compression Draco, plusieurs squelettes, morph targets
ou autres conventions de noms nécessitent une adaptation explicite.

## Affichage et incertitude

- **Homme / Femme** change uniquement l’apparence ; aucune analyse n’est relancée.
- Le médecin démontre une posture idéale, sans recopier la flexion du coude.
- Le bras utilisateur reprend les directions visibles, en conservant les
  proportions du personnage. Il ne reproduit pas la morphologie de la personne.
- Une main absente déclenche le retour de tout son bras au repos, sans retirer
  de triangles du personnage. Le repos est une pose graphique complète, séparée
  des observations incomplètes ; il ne valide ni posture ni répétition.
- Les clavicules accompagnent l’élévation des bras. Le haut du thorax suit une
  inclinaison filtrée de la ligne des épaules (bornée à 12°). Les déformations
  sont nulles sous le haut du ventre, avec une transition progressive vers le
  thorax. Ventre, bassin et jambes restent fixes. De petits mouvements décoratifs
  du cou et de la tête, une respiration et un léger balancement du thorax rendent
  le personnage moins rigide.
- Les mouvements vers l’avant utilisent une profondeur estimée lorsque disponible.
  Ce n’est pas une mesure réelle de profondeur, et les épaules ne sont pas
  simulées anatomiquement.
- Les meshes, textures et poses d’avatars ne sont jamais utilisés pour compter
  ou noter les répétitions. La voix française garde son rythme discret.

## Vérification sans webcam

### Stabilisation et limites d’affichage

`src/avatar_filter.py` implémente le [filtre One Euro de Casiez et al.](https://gery.casiez.net/1euro/),
également utilisé dans les [filtres MediaPipe](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/util/filtering/one_euro_filter.h).
L’implémentation locale utilise NumPy, déjà installé ; aucune nouvelle dépendance
ni téléchargement n’est requis. Elle filtre les angles, plutôt que de mélanger
les positions des joints et de modifier implicitement les longueurs des bras.

- Les poses sont réfléchies horizontalement et les côtés échangés, uniquement
  pour le rendu du médecin et de l’utilisateur. Les mesures gardent leur côté
  anatomique d’origine.
- Un saut important doit persister environ 120 ms avant d’être accepté. Les
  nouvelles observations de bras/poignet doivent rester cohérentes environ 50 ms.
- La vitesse affichée est bornée à 150°/s pour le bras et 210°/s pour le coude.
  Le médecin utilise une limite de 120°/s.
- L’angle du bras est borné entre −65° et 155° ; la flexion du coude reste
  inférieure à 145°. Son sens reste stable jusqu’à ce que le bras redevienne
  presque droit, afin d’éviter un coude qui se retourne soudainement.
- Les rotations du mesh utilisent un repère de repos fixe et des axes de charnière
  stables, évitant les changements de roulis provoqués par les rotations 3D libres.
- Une perte de suivi efface l’historique des observations. Un historique séparé
  de rendu permet seulement de redescendre le bras au repos à 90°/s maximum,
  en dépliant le coude à 150°/s maximum. La réacquisition conserve les limites de
  vitesse au lieu de faire apparaître instantanément un bras levé. Aucun ancien
  poignet ou repos automatique n’est déclaré comme une observation actuelle.

Ces bornes sont des choix conservateurs de visualisation, pas des seuils médicaux
ni une garantie de validité anatomique. Une webcam de face ne permet pas de
retrouver toutes les rotations et profondeurs du bras. Les observations originales
restent seules utilisées pour les angles, avertissements et répétitions.

La position de repos est construite par `RestingAvatarPose`, séparément de
`AvatarMotion.smoothed`. Le rendu utilise `display_pose` tandis que le statut
de suivi reste calculé sur les observations fraîches. Les clavicules suivent
une élévation procédurale légère, complétée par la hauteur mesurée de l’épaule ;
cela améliore l’apparence sans prétendre reconstruire l’anatomie de l’omoplate.

### Doigts et animation naturelle

La limite verticale du bas du corps ne s’applique jamais aux sommets contrôlés
par les bras, mains et doigts, quelle que soit leur hauteur dans la pose de
liaison. Certains doigts du modèle homme sont sous la taille dans cette pose :
les immobiliser produisait des pointes lors de la descente des mains. Les tests
comparent désormais les sommets des mains au skinning complet et vérifient la
conservation des longueurs des arêtes des doigts. Au repos, un écart graphique
maximal de 6° (qui disparaît au-delà de 20° de levée) garde les paumes hors des
cuisses et de la blouse. Il ne change pas l’angle utilisé par l’évaluateur.

`src/avatar_life.py` fournit des mouvements cosmétiques lents : tête ±3° en
rotation horizontale, ±0,6° en inclinaison avant/arrière et ±0,7° latéralement ;
thorax ±0,35° et respiration ±1,5 mm. Ils utilisent un temps relatif, avec des
phases différentes pour le médecin et l’utilisateur, et se figent en pause.
Les pieds restent plantés. Aucun visage n’est nécessaire ; ce n’est pas un suivi
réel de la tête. Les doigts suivent le poignet et, si le modèle de main est actif,
une flexion détaillée filtrée. Sans observation détaillée, ils reviennent à la
forme neutre. La perte du poignet observé continue à ramener le bras au repos
sans effacer sa géométrie.

### Main devant le corps et mouvements vers la caméra

`FrameAnalysis.world_landmarks` transporte les estimations 3D de la trame courante
vers le rendu. Les observations 2D doivent rester visibles : un poignet 3D estimé
ne remplace jamais une main absente de l’image. Les profondeurs non finies ou à
faible visibilité sont ignorées. Seules les épaules, coudes et poignets sont
nécessaires ; les différences de profondeur sont relatives à l’épaule du bras,
sans exiger de visage ni de hanches visibles.

Le Z MediaPipe plus petit est plus proche de la caméra, conformément à la
[documentation officielle](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose.md).
Il devient un Y négatif vers l’avant dans Panda3D. La mise en miroir inverse X
et les côtés, mais garde ce sens de profondeur. Les angles vers l’avant sont
filtrés, bornés à 80° (avant-bras : retour possible jusqu’à −65°), avec des limites
de vitesse de 100°/s et 140°/s. La flexion 3D réelle du coude reste bornée à 145°.

Une correction de dégagement progressive place les bras croisés devant le
thorax/ventre. Le bras avance légèrement si l’avant-bras seul ne peut pas atteindre
la face avant du torse. Les directions sont corrigées sur une sphère unitaire :
la longueur des os ne change pas. La correction se désactive pour la pose de
repos. Elle évite les mains enfouies derrière le modèle, mais ne constitue pas
un moteur de collision anatomique ou une reconstruction complète du bras.
Les estimations vers l’arrière sont ramenées dans le domaine frontal de cet
exercice. Les mesures et verdicts continuent à utiliser les observations originales.

### Paume, poignet et doigts

L’application native peut charger `models/hand_landmarker.task`, modèle officiel
de 7 819 105 octets téléchargé avec `python models/download_models.py hand_landmarker.task`.
Il utilise le paquet MediaPipe existant, sans bibliothèque supplémentaire. Il ne
demande pas de visage. `--no-hands` désactive cette option ; en l’absence du fichier,
le suivi de pose reste utilisable et un message explique le téléchargement.

`src/hand_detector.py` exécute le modèle sur une image réduite à 640 pixels de
large au maximum. Les 21 points de chaque main permettent de calculer une normale
de paume, une direction poignet-vers-articulation centrale et des angles de flexion.
L’association gauche/droite se fait par proximité avec les poignets du corps avant
la mise en miroir, sans se fier aux libellés de latéralité du classificateur.
Une observation doit atteindre 0,6 de confiance et une géométrie valide.

Le rendu distribue une rotation bornée à ±90° entre avant-bras et main, avec une
vitesse limitée à 100°/s. La flexion du poignet est limitée à ±30° et sa déviation
latérale à ±20°. Les flexions de doigts sont bornées à 80° et 140°/s, puis propagées
dans leur chaîne d’os en gardant le poignet attaché à l’avant-bras. Les avatars
utilisateur ont trois chaînes A/B/C (thumb/index/middle dans notre correspondance),
pas cinq chaînes indépendantes : les doigts ne peuvent donc pas reproduire
fidèlement toutes les configurations détectées. Le médecin Mixamo a cinq chaînes.

Les coordonnées 3D de la main sont locales à la main ; elles ne donnent pas sa
position globale par rapport au torse. Elles améliorent l’orientation et les
doigts, sans résoudre seules l’ambiguïté de profondeur du bras. Le modèle de pose
continue à fournir l’épaule, le coude et la profondeur relative du poignet.
Un poignet confirmé par le modèle de main peut remplacer celui de pose dans une
copie destinée au rendu ; les observations originales et le comptage restent
inchangés. Sans main détaillée, l’orientation et les doigts reviennent doucement
au neutre ; si le poignet reste visible par le modèle de pose, le bras reste suivi.

Le diagnostic `python -m tools.check_hand_tracking CHEMIN_IMAGE` vérifie le modèle
réel et génère des vues des gestes sous `output/`. Le contrôle local a utilisé
l’image publique officielle MediaPipe `woman_hands.jpg`, sans webcam ni données
de patient. Cela vérifie l’intégration, pas la précision en conditions réelles.

Exécuter `python -m tools.preview_avatars` depuis la racine. Le diagnostic
utilise des poses synthétiques et génère des images sous `output/` : vues homme
et femme, interface prête/en cours/en pause, épaules inclinées et main absente
avec bras au repos. Il vérifie que chaque personnage
reste visible après changement de sélection, que les animations changent les
pixels, que le redimensionnement fonctionne et que le compteur n’est pas modifié.

Les tests de déformation vérifient les longueurs des os, les rotations opposées,
les articulations absentes et les limites spatiales des trois modèles locaux.
Ces vérifications logicielles ne prouvent pas la précision clinique du suivi.
