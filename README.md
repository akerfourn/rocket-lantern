# RocketLantern

Application Windows en Python / Qt pour capter les données de la Stats API
Rocket League : suivi des matchs, bilans par session et statistiques.
Historique local SQLite, choix du joueur, reconnexion automatique et
détection des doublons.

## Installation et lancement

Prérequis : Python 3.13 et [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run rocket-lantern
```

PySide6 fournit Qt et son client WebSocket natif : aucune bibliothèque réseau
supplémentaire n'est nécessaire. SQLite fait partie de Python. Les versions
résolues sont conservées dans `uv.lock`.

## Activer l'API du jeu

Fermer Rocket League. Dans le dossier d'installation du jeu, ouvrir
`TAGame\Config\TAStatsAPI.ini`, ou `DefaultStatsAPI.ini` si le premier
n'existe pas. Adapter les clés de la section existante, sans la dupliquer :

```ini
[TAGame.MatchStatsExporter_TA]
PacketSendRate=1
WebPort=49124
```

Le port TCP `Port`, s'il est activé, doit être différent de `WebPort`.
Relancer le jeu après modification. L'application se connecte uniquement à
`ws://127.0.0.1:49124`. Le port est modifiable dans la fenêtre.

Source : [documentation officielle de la Stats API][stats-api].
L'application ne modifie pas les fichiers du jeu.

## Utilisation

1. Lancer l'application, puis un match Rocket League.
2. Sélectionner son joueur dans la liste ; son identifiant est mémorisé.
3. Laisser l'application ouverte jusqu'au résultat du match.

Le bilan victoires/défaites, son écart, le taux de victoire et les inconnus
sont affichés au-dessus des onglets. Une coche et une croix distinguent les
résultats, sans dépendre uniquement des couleurs. Le bilan et les sélecteurs
restent visibles dans **Matchs**, **Partie en cours** et **Logs**.

Les sélecteurs filtrent le bilan, les statistiques du joueur et les 100
dernières observations affichées. Les totaux et moyennes portent sur tous
les matchs du filtre, même au-delà de ces 100 lignes.
Par défaut : session actuelle et dernier type joué. Le dernier type suit
automatiquement la playlist annoncée par le jeu ; revenir à un type retrouve
ses résultats dans la session. « Tous les types » regroupe les playlists.
La période permet aussi de choisir une ancienne session ou tout l’historique.
Choisir une session actualise la synthèse sans ouvrir de fenêtre. Le bouton
**Détails de la session** ouvre la session complète, toutes playlists
confondues : totaux et moyennes, dates, bilan, arènes, scores, prolongations
et statistiques du joueur sélectionné pour chaque match. Un clic sur un
match ouvre les participants et événements de cette partie. Les fenêtres
de détail présentent les données enregistrées au moment de leur ouverture.

La synthèse affiche points, buts, passes décisives, arrêts, tirs,
démolitions, touches de balle et contacts entre voitures. Chaque carte
indique le total, la moyenne par match et le nombre de matchs renseignés
sur ceux du filtre (`x/y`). Les valeurs absentes sont affichées « — », les
zéros reçus restent « 0 ». Une moyenne exclut uniquement les valeurs
absentes, pas les zéros. Les données partielles et les résultats inconnus
participent aux statistiques ; le nombre d’états de fin reçus est indiqué.

Une nouvelle session commence après au moins une heure entre deux résultats.
Chaque session possède un ID enregistré en base, par joueur, indépendant
des playlists. Le bouton **Nouvelle session** crée immédiatement une session
vide et remet ses compteurs à zéro sans effacer l'historique. Le prochain
résultat non encore enregistré y sera rattaché, même si le match était déjà
en cours. Une correction tardive reste dans la session d'origine du match.
Les sessions, même vides, survivent au redémarrage. Après une heure sans
résultat (ou depuis la création d'une session vide), la session actuelle est
vide en attendant le prochain résultat, qui crée une nouvelle session.
Au premier lancement de cette version, les anciennes données sont migrées
automatiquement : regroupement initial selon la règle d'une heure, puis
attribution définitive des IDs. Les regroupements ne sont plus recalculés.
Les inconnus sont exclus du
taux de victoire. Le type de partie apparaît en direct et dans l'historique :
`2v2 classé`, `3v3 occasionnel`, `Match privé`, etc. L'identifiant API reste
visible ; les IDs non répertoriés sont affichés comme inconnus.
La date est celle de l'observation du résultat, affichée en heure locale.

### Partie en cours

Cet onglet affiche le dernier score reçu, le chrono, la prolongation,
le type de partie, l'arène, la vitesse du ballon en unités Unreal/seconde,
la dernière équipe au contact et les compteurs des participants présents.
Le score de l'équipe du joueur sélectionné est souligné. Les filtres
d'historique ne filtrent pas cette vue du match actuellement observé.

Une jauge affiche le boost du joueur sélectionné et une jauge nommée est
affichée pour chacun de ses coéquipiers présents, identifiés par leur ID et
leur équipe. Changer de joueur sélectionné change l'équipe affichée.
Les jauges sont regroupées dans une colonne compacte de 240 pixels, avec
le nom au-dessus de chaque barre. Le réglage **Boosts : À gauche / À droite**
est mémorisé localement. Dès que l'onglet atteint 900 pixels de large,
la colonne se place à côté du tableau ; sinon, elle reste au-dessus du
tableau, alignée du côté choisi. Les noms d'équipe du score et du tableau
sont remplacés par des pastilles bleues et orange, avec des infobulles.
Le score du joueur sélectionné reste souligné.

Les jauges des coéquipiers sont vertes au-dessus de 50 %, orange au-dessus
de 25 %, rouges jusqu'à 25 % inclus. À 0 %, toute la barre rouge affiche
des stries animées façon chargement, avec « 0 % · vide » à côté.
Le boost du joueur sélectionné reste gris, sans animation d'alerte à zéro.
Les animations s'arrêtent lorsque la vue est masquée ou le boost absent.
Une donnée absente reste
une jauge désactivée « — », sans animation. Les valeurs et couleurs sont
actualisées à chaque état reçu, sans recréer les jauges à chaque paquet.
Le tableau montre aussi les valeurs reçues pour les autres joueurs.
L'affichage ne suppose pas que seul le joueur local est visible. Un champ
absent ou invalide reste « — », pas zéro, et une valeur omise n'est pas
reprise d'un ancien état. La visibilité dépend des données émises par le jeu.
Le boost n'est pas déduit des événements de ramassage.

La vue conserve uniquement le dernier état en mémoire : aucune série de
boost ou de vitesse n'est enregistrée dans SQLite. La sauvegarde existante
des résumés de match et événements importants reste inchangée.
À la déconnexion ou en quittant la partie, les valeurs sont effacées. Les
ralentis de buts conservent les dernières données hors ralenti, explicitement
signalées ; les replays historiques sont exclus de cette vue en direct.

La fluidité suit `PacketSendRate` : avec `1`, les états périodiques arrivent
une fois par seconde ; `10` permet un rafraîchissement plus fluide. Un
changement du fichier INI exige un redémarrage du jeu. Voir la
[configuration officielle][stats-api]. RocketLantern ne change pas l'INI.

Les préférences et résultats sont conservés dans `matches.sqlite3`, dans le
dossier local de données Qt, en conservant le nom historique `RLWinLoss`.
Le renommage en RocketLantern ne déplace ni ne réinitialise la base. Sous
Windows : `%LOCALAPPDATA%\RLWinLoss\RLWinLoss\matches.sqlite3`.
Les noms et identifiants des participants sont enregistrés localement avec
leurs statistiques de match. Aucun service distant ni compte supplémentaire
n'est utilisé.

### Détail des matchs

Cliquer une ligne de l’historique ouvre la fiche du match : score
bleu/orange, puis onglets **Joueurs**, **Événements** et **Informations**
(arène, prolongation, playlist, dernière observation et identifiants).
Le tableau présente tous les joueurs observés, répartis par équipe. Le
joueur sélectionné est repéré par son identifiant, avec une ligne en
surbrillance et la mention « sélectionné » ; le score de son équipe reste
en gras et souligné. L’onglet Événements liste les buts, événements de
statistiques (`StatfeedEvent`) et barres.
Chaque joueur conserve ses derniers compteurs reçus : points, buts, tirs,
passes décisives, arrêts, touches de balle, contacts entre voitures et
démolitions. Un départ ne supprime pas ses statistiques.

Les buts conservent le buteur, le passeur éventuel, l’équipe, la vitesse et
la position du ballon si disponibles. Les vitesses sont en unités Unreal/s.
L’horloge est la dernière valeur reçue du jeu ; `GoalTime` reste séparé et
représente la durée de la manche précédente, pas la minute du but.
Les identités des événements sont reliées aux participants uniquement si
l’identifiant ou le raccourci/équipe/nom permet une attribution cohérente.
Une identité non résolue reste absente, jamais attribuée par le nom seul.

Une valeur absente s’affiche « — », distinctement d’un zéro. Sans état reçu
après l’annonce du vainqueur, le score et les statistiques restent des
dernières valeurs observées, potentiellement partielles. Les états tardifs
enrichissent un résultat déjà enregistré sans recompter le match.
Même avec un état final, les événements ne couvrent que la période de
connexion ; les participants partis ont leurs dernières valeurs observées.
Les ralentis et replays ne doivent pas ajouter de statistiques ou événements.

SQLite stocke des tables structurées avec identifiants internes, clés
étrangères et contraintes d’unicité. Aucun message JSON brut ni trajectoire
continue n’est conservé. Les buts sont des événements `GoalScored`.
Les événements identiques dans le même contexte d’horloge sont dédupliqués ;
l’API ne fournit pas d’identifiant d’événement, donc deux événements
strictement identiques dans ce contexte ne peuvent pas être distingués.
La migration est automatique et conserve l’historique existant au même
emplacement. Les anciens matchs n’ont pas de statistiques rétroactives.

## Diagnostic : onglet Logs

Relancer l'application après une mise à jour du code, puis ouvrir **Logs**.
L'onglet affiche les 1 000 dernières entrées horodatées :

- Adresse WebSocket, connexion, déconnexion et erreur exacte du socket.
- Tous les événements reçus, y compris `UpdateState`, avant leur traitement.
- Messages JSON invalides et raisons de rejet par le suivi des matchs.
- Résultats enregistrés, compteur de messages et heure de dernière réception.

Les logs restent en mémoire. Les noms et identifiants sont masqués sans
modifier les données utilisées par le compteur. Les entrées de plus de
16 000 caractères sont tronquées avec une indication explicite. Les boutons
permettent de copier les logs, de les effacer ou de suspendre le défilement.
Suspendre le défilement n'arrête pas la collecte.

L'API peut envoyer `Data` comme objet JSON ou comme chaîne contenant du JSON.
Les deux formats sont décodés avant le suivi et le masquage des logs. Le
journal affiche le contenu normalisé. Un champ `Data` encodé mais invalide
est masqué entièrement, avec une erreur de décodage explicite.

**Connecté ne signifie pas que des événements arrivent.** Après dix secondes
sans message, l'application affiche un avertissement : cela peut être normal
dans les menus. Vérifier la réception pendant une partie. Avec
`PacketSendRate=10`, les événements `UpdateState` sont attendus dix fois par
seconde pendant l'émission du jeu ; les autres événements s'y ajoutent.

Si le compteur reste à zéro pendant une partie :

1. Vérifier `WebPort=49124` et le même port dans la fenêtre de l'application.
2. Vérifier les paramètres de la section `[TAGame.MatchStatsExporter_TA]` et
   redémarrer complètement Rocket League après leur modification.
3. Vérifier aussi le fichier utilisateur, s'il existe :
   `Documents\My Games\Rocket League\TAGame\Config\TAStatsAPI.ini`.
   Une valeur dans `DefaultStatsAPI.ini` ne suffit pas à décrire la
   configuration utilisateur. Le projet ne modifie aucun de ces fichiers.
4. Copier les lignes de connexion et les événements/rejets depuis **Logs**.

La connexion et la réception sont distinctes du comptage : un événement sans
`MatchGuid` reste visible et son type de partie est affiché, mais aucun
résultat n'est enregistré sans identifiant de match fiable.

## Limites

- Le suivi commence quand l'application reçoit les matchs ; cette API
  n'importe pas automatiquement l'historique passé du compte.
- Quitter le match, fermer l'application ou perdre la connexion avant le
  résultat produit un résultat inconnu, sans déduire une défaite.
- Un résultat confirmé reçu après reconnexion remplace un inconnu.
- Les replays chargés sont exclus via `ReplayCreated`. À la connexion,
  `bReplay=true` associé à `Frame` / `Elapsed` déclenche aussi cette exclusion.
  Ces champs seuls ne suffisent pas si `bReplay=false`. Les ralentis de buts
  pendant un match déjà suivi ne sont pas exclus. Une première connexion
  pendant un ralenti avec ces champs peut rester ambiguë : consulter les logs.
- Seuls les matchs avec `MatchGuid` et une équipe connue pour le joueur
  choisi peuvent être comptés. L'entraînement n'est pas comptabilisé.
- Un changement de joueur interrompt le suivi courant. Le nouveau joueur
  est reconnu à la prochaine mise à jour du jeu.
- Un arrêt brutal du processus ne permet pas de sauvegarder le match actif.

## Build Windows et installation

Le build nécessite Windows x64, `uv` et Inno Setup 6. La version du
logiciel provient de `pyproject.toml`, et les dépendances de `uv.lock`.
PyInstaller est une dépendance de build uniquement : il embarque Python
et les modules Qt utilisés. Inno Setup produit l’installateur.

```powershell
.\scripts\build-windows.ps1
# Si le compilateur n’est pas à son emplacement habituel :
.\scripts\build-windows.ps1 -IsccPath 'C:\outils\InnoSetup\ISCC.exe'
```

Le script fonctionne sans question interactive et échoue si une étape
échoue. Les livrables sont dans `dist/installers/` : installateur `.exe`
et archive portable `.zip`. Le programme autonome est aussi disponible
dans `dist/RocketLantern/`. Il faut conserver tout ce dossier avec son `.exe`.

L’installateur utilise `%LOCALAPPDATA%\Programs\RocketLantern`, crée un
raccourci dans le menu Démarrer et propose un raccourci sur le bureau.
Il fonctionne sans droits administrateur et fournit un désinstalleur.
Historique et préférences restent dans
`%LOCALAPPDATA%\RLWinLoss\RLWinLoss\matches.sqlite3` ; ils sont conservés
pendant les mises à jour et la désinstallation.
L'identifiant de l'installateur reste inchangé : une installation existante
peut conserver son ancien dossier lors de la mise à jour.

Installation silencieuse possible, sans démarrage de l’application :

```powershell
.\RocketLantern-0.1.0-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
```

Le workflow `.github/workflows/windows-build.yml` exécute tests et lint sur
chaque push, pull request ou lancement manuel, sans filtre de branche.
Le build Windows et le test de l'installateur s'exécutent uniquement pour
un tag stable `vMAJEUR.MINEUR.CORRECTIF`, après réussite des vérifications.
Par exemple, `v0.1.0` construit les paquets ; `v0.1.0-alpha.1`,
`v0.1.0-beta.1` et `v0.1.0-rc.1` exécutent seulement les vérifications.
Un lancement manuel construit les paquets seulement si la référence choisie
est elle-même un tag stable. Le tag doit correspondre à la version déclarée
dans `pyproject.toml`, sinon le build échoue avant le packaging.

Pour déclencher le build de la version actuelle, après avoir commité les
changements et poussé le commit :

```powershell
git tag v0.1.0
git push origin v0.1.0
```

L'exécutable installé, l'installeur et le ZIP portable sont construits sur
un runner Windows. L'installeur et le ZIP sont téléchargeables depuis les
artefacts de l'exécution pendant 30 jours.
Il ne publie pas automatiquement de release. Aucun secret n’est requis.
Les exécutables ne sont pas signés ; Windows peut afficher SmartScreen.

## Vérifications de développement

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Les tests utilisent des événements synthétiques, une base en mémoire et Qt
sans fenêtre visible. Aucun jeu ni accès réseau n'est nécessaire.

[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en

Les noms de playlists sont une table locale d'IDs, issue de cette
[référence communautaire][playlist-ids]. Aucune installation de BakkesMod
n'est nécessaire ; toutes les données viennent de la Stats API officielle.

[playlist-ids]: https://bakkesplugins.com/wiki/bakkesmod-sdk/code-snippets/playlist-id
