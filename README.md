# RL Win/Loss

Petite application Windows en Python / Qt pour suivre les victoires et
défaites Rocket League en direct. Historique local SQLite, choix du joueur,
reconnexion automatique et détection des doublons.

## Installation et lancement

Prérequis : Python 3.13 et [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run rl-winloose
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

Les sélecteurs filtrent les compteurs et les 100 dernières observations.
Par défaut : session actuelle et dernier type joué. Le dernier type suit
automatiquement la playlist annoncée par le jeu ; revenir à un type retrouve
ses résultats dans la session. « Tout » regroupe les types de partie.
La période permet aussi de choisir une ancienne session ou tout l’historique.
Une nouvelle session commence après au moins une heure entre deux résultats.
Les sessions sont calculées par joueur depuis les dates enregistrées et
survivent au redémarrage de l’application. Sans résultat depuis une heure,
la session actuelle est vide en attendant le prochain résultat.
Les inconnus sont exclus du
taux de victoire. Le type de partie apparaît en direct et dans l'historique :
`2v2 classé`, `3v3 occasionnel`, `Match privé`, etc. L'identifiant API reste
visible ; les IDs non répertoriés sont affichés comme inconnus.
La date est celle de l'observation du résultat, affichée en heure locale.

Les préférences et résultats sont conservés dans `matches.sqlite3`, dans le
dossier local de données retourné par Qt (`AppLocalDataLocation`). Sous
Windows, ce dossier se trouve dans `%LOCALAPPDATA%`, sous `RLWinLoss`.
Les noms et identifiants des participants sont enregistrés localement avec
leurs statistiques de match. Aucun service distant ni compte supplémentaire
n'est utilisé.

### Détail des matchs

Double-cliquer une ligne de l’historique ouvre le résumé du match : score
bleu/orange, arène, prolongation, tableau de tous les joueurs observés et
liste des buts, événements de statistiques (`StatfeedEvent`) et barres.
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
dans `dist/RLWinLoss/`. Il faut conserver tout ce dossier avec son `.exe`.

L’installateur utilise `%LOCALAPPDATA%\Programs\RLWinLoss`, crée un
raccourci dans le menu Démarrer et propose un raccourci sur le bureau.
Il fonctionne sans droits administrateur et fournit un désinstalleur.
Historique et préférences restent dans
`%LOCALAPPDATA%\RLWinLoss\RLWinLoss\matches.sqlite3` ; ils sont conservés
pendant les mises à jour et la désinstallation.

Installation silencieuse possible, sans démarrage de l’application :

```powershell
.\RLWinLoss-0.1.0-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
```

Le workflow `.github/workflows/windows-build.yml` exécute tests, lint,
build et création de l’installateur sur un runner Windows GitHub Actions.
Il se déclenche sur push, pull request ou manuellement. Les deux livrables
sont téléchargeables depuis les artefacts de l’exécution, pendant 30 jours.
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
