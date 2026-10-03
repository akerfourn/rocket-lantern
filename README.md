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
Les noms des autres joueurs ne sont pas enregistrés ; seul le joueur choisi
est mémorisé. Aucun service distant ni compte supplémentaire n'est utilisé.

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

## Développement

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
