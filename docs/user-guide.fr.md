# Guide utilisateur détaillé

[English](user-guide.md) | [Français](user-guide.fr.md)

Pour télécharger l’application, l’installer et configurer le jeu pour la
première fois, consultez le [README](../README.fr.md).

![Historique et statistiques des joueurs dans RocketLantern][screenshot]

Aperçu avec des joueurs et des données de match fictifs.

## Utilisation

Au premier lancement, l’assistant propose de rechercher les installations
Steam et Epic Games et de régler leur `PacketSendRate`. La recherche et
les modifications ne commencent qu’au clic sur leurs boutons respectifs.
Vous pouvez aussi choisir la langue et le port local ; **Terminer**
reconnecte l’application si vous avez changé le port. Le `WebPort` du jeu
reste à vérifier manuellement.

**Terminer**, **Passer pour le moment** et la fermeture de l’assistant sont
mémorisés : il ne réapparaît pas automatiquement au lancement suivant.
Vous pouvez le rouvrir dans
**Paramètres → Rocket League → Assistant de démarrage**. Il
n’est pas imposé aux utilisateurs ayant déjà sélectionné un joueur ou
enregistré des matchs.

Les chemins détectés sont conservés dans la base locale, mais pas le
contenu des fichiers INI ni une validation permanente de leurs valeurs.
Après un redémarrage, ils apparaissent comme **à vérifier**. Cliquez sur
**Vérifier les configurations** pour relire les fichiers avant d’appliquer
un réglage. Aucun balayage des installations n’a lieu au démarrage ou
périodiquement. Une recherche partiellement inaccessible conserve les
anciens chemins ; une recherche complète les remplace.

1. Lancez l’application, puis un match dans Rocket League.
2. Sélectionnez votre joueur dans la liste ; son identifiant est mémorisé.
3. Gardez l’application ouverte jusqu’à la réception du résultat du match.

Sous Windows, l’application attend Rocket League avant de se connecter.
La connexion démarre automatiquement au lancement du jeu ; les tentatives
s’arrêtent à sa fermeture. La détection peut prendre environ deux secondes.
Alt+Tab et la minimisation ne coupent ni la connexion ni le suivi des matchs.

Si la détection du jeu échoue, une connexion existante est conservée.
**Reconnecter** permet encore d’essayer la connexion à l’API lorsque la
détection est indisponible.

Ouvrez les **Paramètres** pour choisir **Français** ou **English**. Ce choix
est enregistré localement. Les libellés, filtres, infobulles et fenêtres de
détail déjà ouvertes changent immédiatement, sans redémarrer l’application
ni se reconnecter au jeu. Le format des dates et le séparateur décimal
suivent la langue sélectionnée. Les noms et identifiants des joueurs, les
noms des arènes et les données de l’API ne sont pas traduits. Les entrées de
logs existantes gardent la langue utilisée lors de leur création.
Au premier lancement, la langue du système détermine le choix entre le
français et l’anglais.

Les victoires, défaites, leur différence, le taux de victoire et les
résultats inconnus apparaissent au-dessus des onglets. Une coche et une
croix distinguent les résultats sans dépendre uniquement de la couleur.
Le bilan et les sélecteurs restent visibles dans **Matchs**, **Partie en
cours** et **Logs**.

Les sélecteurs filtrent le bilan, les statistiques du joueur et les
100 dernières observations affichées. Les totaux et les moyennes couvrent
tous les matchs correspondant au filtre, y compris ceux au-delà de ces
100 lignes.
Par défaut, le bilan porte sur la session actuelle et le dernier type de
partie joué. Ce type suit automatiquement le mode annoncé par le jeu ;
revenir à un mode retrouve ses résultats dans la session. **Tous les types**
regroupe les différents modes. La période permet aussi de sélectionner une
ancienne session ou tout l’historique. Choisir une session actualise le
bilan sans ouvrir de fenêtre.
**Détails de la session** ouvre la session entière, tous modes confondus :
totaux, moyennes, dates, résultats, arènes, scores, prolongations et
statistiques du joueur sélectionné pour chaque match. Un clic sur un match
ouvre ses participants et ses événements. Les fenêtres de détail montrent
les données enregistrées au moment de leur ouverture.

Le bilan présente les points, buts, passes décisives, arrêts, tirs,
démolitions, touches de balle et contacts entre voitures. Chaque carte
affiche le total, la moyenne par match et le nombre de matchs renseignés
parmi ceux du filtre (`x/y`). Les valeurs manquantes apparaissent comme
« — » ; un zéro reçu reste « 0 ». Les moyennes excluent uniquement les
valeurs manquantes, pas les zéros. Les données partielles et les résultats
inconnus contribuent aux statistiques ; le nombre d’états de fin reçus est
indiqué.

Une nouvelle session commence après au moins une heure entre deux
résultats. Chaque session possède un identifiant en base pour le joueur,
indépendant des modes de jeu. **Nouvelle session** crée immédiatement une
session vide et remet ses compteurs à zéro sans supprimer l’historique.
Le prochain résultat non encore enregistré la rejoint, même si le match
est déjà en cours. Une correction tardive reste dans la session d’origine
du match. Les sessions, même vides, sont conservées après un redémarrage.
Après une heure sans résultat, ou depuis la création d’une session vide,
la session actuelle reste vide jusqu’à ce que le prochain résultat en crée
une nouvelle.
Au premier lancement de cette version, les anciennes données sont migrées
automatiquement : regroupement initial selon la règle d’une heure, puis
attribution d’identifiants permanents. Ces groupes ne sont ensuite plus
recalculés.

Les résultats inconnus sont exclus du taux de victoire. Les modes de jeu
apparaissent en direct et dans l’historique, par exemple `2v2 classé`,
`3v3 occasionnel` ou `Match privé`. Les identifiants de l’API restent visibles ;
ceux qui ne sont pas répertoriés sont indiqués comme inconnus. Les dates
correspondent au moment où le résultat a été observé et sont affichées dans
le fuseau horaire local.

### Paramètres

La fenêtre comprend quatre rubriques : **Général**, **Rocket League**,
**Overlay** et **Raccourcis**. Général regroupe la connexion, la langue,
l’onglet au lancement et les mises à jour. Chaque rubrique défile sur les
petits écrans ; le bouton **Fermer** reste visible sous les onglets.

### Overlay W/L

Dans **Paramètres → Overlay → Bilan W/L**, activez **Afficher l’overlay** et
choisissez l’écran du jeu. Les icônes et les nombres affichent les
victoires, les défaites et leur delta signé, sans lettres W/L. Les filtres
de joueur, de période et de mode restent ceux du bandeau. L’overlay laisse
passer les clics.

Choisissez un coin ou cliquez sur **Positionner l’overlay…**. Un éditeur
s’ouvre sur l’écran choisi : déplacez le bandeau, puis **Enregistrer** ou
**Annuler**. Échap annule également. Seul cet aperçu accepte les clics ;
l’overlay réel reste non interactif. La position est mémorisée localement,
relativement à la taille de l’écran, et reste dans ses limites si la
résolution change. Vous pouvez la régler avant d’activer l’overlay. Si
l’écran est débranché, l’écran principal le remplace temporairement sans
effacer le choix enregistré.

Dans Rocket League, privilégiez le mode **Sans bords** ou **Fenêtré**.
La visibilité des overlays n’est pas garantie en plein écran exclusif.
Sous Windows, les deux overlays apparaissent uniquement lorsque Rocket
League est au premier plan. Alt+Tab, la minimisation ou la fermeture du jeu
les masquent sans désactiver leurs préférences enregistrées. Minimiser
RocketLantern ne les masque pas si le jeu reste actif. L’éditeur de
placement reste accessible sans le jeu. Les overlays se ferment avec
RocketLantern et sont désactivés par défaut.
Le choix d’activation est restauré au lancement suivant.

### Overlay du boost des coéquipiers

Dans **Paramètres → Overlay → Boost des coéquipiers**, une seconde option
affiche uniquement les jauges nommées des alliés du joueur sélectionné.
Son propre boost et celui des adversaires sont exclus. Cet overlay peut
être activé indépendamment du bilan W/L, sur un autre écran ou à une
autre position. Privilégiez également le mode **Sans bords** ou **Fenêtré**.

Le réglage **Affichage** propose trois choix :

- **Jamais** (par défaut).
- **Parties privées uniquement** : matchs privés, matchs locaux/LAN,
  entraînement libre en ligne et modes hors ligne ou d’entraînement.
- **Toutes les parties** : sans restriction de mode.

Le choix est mémorisé. Le mode privé exclut le matchmaking, même
occasionnel, ainsi que les tournois. Si le type de partie n’est pas
identifié, l’overlay reste masqué dans ce mode. Un overlay déjà activé
avant l’ajout de ce réglage conserve le choix **Toutes les parties**.

**Attention au risque de bannissement.** Les [règles Epic sur les outils
tiers][third-party-tools] excluent les avantages compétitifs en ligne.
L’affichage du boost pourrait entrer dans cette catégorie ; RocketLantern
ne garantit ni son autorisation ni l’absence de sanction. L’option reste
désactivée par défaut et demande une confirmation à la première activation.
Le choix d’activation et l’acceptation de l’avertissement sont mémorisés ;
il n’est donc pas nécessaire de les renouveler à chaque lancement.

La [note sur le fair-play](boost-overlay-fair-play.fr.md) présente nos
sources, notre raisonnement et les points qui restent incertains.

**Positionner l’overlay…** utilise des jauges fictives pour préparer le
placement hors match, sans activer l’affichage réel. La position est
mémorisée séparément de celle du bilan. En jeu, les jauges utilisent les
mêmes couleurs et l’alerte rouge animée à zéro que l’onglet Partie en cours.
« ≈ 0 % » indique un champ absent assimilé à zéro, pas une valeur confirmée.

L’overlay se masque sans allié identifiable, pendant les replays de but,
à la fin du match ou à la déconnexion. Il se masque aussi après trois
secondes sans nouvel état pour éviter d’afficher un boost périmé. Il
réutilise la connexion et le dernier état reçus : aucune mesure de boost
supplémentaire n’est conservée en base.

[third-party-tools]: https://www.rocketleague.com/code-of-conduct?lang=fr

### Évaluation des matchs

L’étiquette, affichée seule juste après le delta W/L, est indépendante des
filtres de l’historique. Elle cible le **match en cours**, ou le **dernier
match** une fois celui-ci terminé. Cliquez dessus pour choisir :

- **Non évalué** : aucune évaluation, le choix par défaut pour chaque
  nouveau match.
- **Aucune suspicion** : vous avez évalué le match sans soupçonner de
  smurfing.
- **Suspicion possible** : vous soupçonnez du smurfing.
- **Forte suspicion** : votre suspicion est forte, sans constituer une
  preuve objective.

L’étiquette change de symbole intérieur (tiret, coche, point d’interrogation
ou d’exclamation) et de couleur. Le survol affiche le libellé du choix dans
une infobulle. Les libellés et les menus changent avec la langue.

Après la fin d’un match ou une déconnexion, son étiquette reste modifiable
jusqu’à l’identification d’un nouveau match. Un identifiant de match
différent démarre sans évaluation ; se reconnecter au même match retrouve
le choix enregistré. Les replays d’anciens matchs et les observations sans
identité de match ou de joueur exploitable ne peuvent pas être évalués
depuis l’étiquette du bandeau.

Les petites étiquettes à droite de **Matchs** permettent de modifier un
match précédent. Une évaluation appartient au match, pas à une session,
un filtre ou une sélection de joueur. Modifier un ancien match ne change
pas l’étiquette du match en cours. Les choix sont enregistrés localement
dans SQLite, y compris ceux faits avant la réception d’un résultat. Ils ne
modifient pas le bilan W/L et n’envoient aucun signalement à Epic.

#### Raccourcis clavier optionnels sous Windows

L’édition à la souris reste disponible. Pour utiliser les raccourcis,
ouvrez les **Paramètres**, cochez **Activer les raccourcis clavier globaux**,
ajustez les combinaisons, puis cliquez sur **Appliquer les raccourcis**.
Ils sont désactivés au premier lancement.

| Raccourci par défaut | Évaluation |
| --- | --- |
| Ctrl+Maj+F1 | Non évalué |
| Ctrl+Maj+F2 | Aucune suspicion |
| Ctrl+Maj+F3 | Suspicion possible |
| Ctrl+Maj+F4 | Forte suspicion |

Utilisez une seule combinaison contenant Ctrl, Alt ou Maj avec une lettre,
un chiffre ou une touche de F1 à F24, sauf F12 et les raccourcis utilisant
la touche Windows. Les combinaisons doivent être différentes. Si Windows
ne peut pas en enregistrer une, aucun raccourci d’évaluation ne reste
actif ; ouvrez les Paramètres pour voir l’erreur et choisir d’autres touches.

Les raccourcis enregistrés fonctionnent sans avoir RocketLantern au premier
plan. Ils modifient le match en cours ou le dernier match observé, jamais
une ligne sélectionnée dans l’historique. Sans match cible exploitable, ils
ne changent rien. Maintenir une touche enfoncée ne répète pas l’évaluation.
Les raccourcis sont suspendus tant que les Paramètres sont ouverts : saisir
une nouvelle combinaison n’évalue donc pas un match. Les modifications non
enregistrées sont ignorées ; la configuration précédemment sauvegardée
reprend à la fermeture de la fenêtre. Fermer RocketLantern libère les
raccourcis enregistrés auprès de Windows.

RocketLantern n’enregistre que ces combinaisons auprès de Windows. Il ne
collecte pas les autres frappes, ne s’injecte pas dans le jeu et ne simule
pas de touches. Ce fonctionnement ne garantit pas la compatibilité avec
les systèmes anti-triche. Sur les petits écrans, les Paramètres défilent
tout en gardant le bouton **Fermer** visible.

### Partie en cours

Cet onglet affiche les dernières données reçues : score, chrono,
prolongation, mode de jeu, arène, vitesse du ballon en unités Unreal par
seconde, dernière équipe à l’avoir touché et compteurs des joueurs présents.
Le score de l’équipe du joueur sélectionné est souligné. Les filtres de
l’historique n’affectent pas cette vue du match observé.

Une jauge affiche le boost du joueur sélectionné et une jauge nommée
apparaît pour chaque coéquipier présent, identifié par son identifiant et
son équipe. Changer de joueur sélectionné change l’équipe affichée. Les
jauges forment une colonne compacte de 240 pixels, avec les noms au-dessus
des barres. Le réglage **Boosts : À gauche / À droite** est mémorisé
localement. À partir d’une largeur d’onglet de 900 pixels, la colonne se
place à côté du tableau ; sinon, elle reste au-dessus, du côté choisi.
Dans le score et le tableau, les noms d’équipes sont remplacés par des
pastilles bleues et orange avec des infobulles. Le score de l’équipe du
joueur sélectionné reste souligné.

Les jauges des coéquipiers sont vertes au-dessus de 50 %, orange au-dessus
de 25 % et rouges à 25 % ou moins. À 0 %, toute la barre rouge affiche des
rayures animées, comme un indicateur de chargement, avec « 0 % · vide » à
côté. Le boost du joueur sélectionné reste gris, sans animation d’alerte à
zéro. Les animations s’arrêtent lorsque la vue est masquée. Si le champ
`Boost` d’un coéquipier présent est absent, sa jauge affiche la même alerte
rouge animée qu’à zéro, avec « ≈ 0 % » : c’est une hypothèse d’affichage, pas
une valeur reçue. Une valeur invalide ou un joueur explicitement sans
voiture garde une jauge désactivée « — ». Cette hypothèse ne s’applique pas
au joueur sélectionné. Les valeurs et les couleurs suivent chaque état
reçu sans recréer les jauges à chaque paquet.

Le tableau montre aussi les valeurs reçues pour les autres joueurs.
L’affichage ne suppose pas que seul le joueur local est visible. Les champs
manquants ou invalides restent « — » dans le tableau et l’état reçu, pas
zéro. Une valeur absente n’est pas reprise d’un état précédent ; l’alerte
« ≈ 0 % » concerne uniquement les jauges des coéquipiers. La visibilité
dépend des données envoyées par le jeu. Le boost n’est pas déduit des
événements de ramassage.

La vue garde uniquement le dernier état en mémoire : aucune série
temporelle de boost ou de vitesse n’est enregistrée dans SQLite. Le
stockage des résumés de match et des événements importants reste inchangé.
Une déconnexion ou la sortie du match efface les valeurs. Les ralentis de
but conservent les dernières données hors ralenti, avec une indication
explicite ; les replays d’anciens matchs sont exclus de cette vue en direct.

Nous recommandons `PacketSendRate=10` pour dix mises à jour périodiques par
seconde et des jauges plus fluides. Avec `1`, les mises à jour arrivent une
fois par seconde. Toute modification du fichier INI nécessite de relancer
le jeu ; consultez la [configuration officielle][stats-api]. RocketLantern
ne change que `PacketSendRate`, au clic explicite sur **Appliquer** pour une
installation dans les **Paramètres**. **Vérifier les configurations** lit
chaque installation détectée et compare son débit à la cible enregistrée :
un débit inférieur est un avertissement, un débit supérieur une information.
Les changements conservent les autres clés et créent une sauvegarde à côté
du fichier. Le jeu doit être redémarré après les modifications.

Les préférences et les résultats sont enregistrés dans `matches.sqlite3`,
dans le dossier local RocketLantern géré par Qt. Sur Windows :
`%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3`.
La version 1.0.1 migre automatiquement les anciennes installations au
démarrage, en conservant l’historique et les préférences. Les fichiers
d’origine ne sont supprimés qu’après validation de la copie. Aucune
migration manuelle n’est nécessaire. Les noms et identifiants des
participants sont enregistrés localement avec leurs statistiques de match.
Aucun service distant ni compte supplémentaire n’est utilisé pour ces
données.

### Détails d’un match

Cliquez sur une ligne de l’historique pour ouvrir la fiche du match : score
bleu/orange, puis onglets **Joueurs**, **Événements** et **Informations**
(arène, prolongation, mode de jeu, dernière observation et identifiants).
Le tableau montre tous les joueurs observés, regroupés par équipe. Le
joueur sélectionné est reconnu par son identifiant ; sa ligne est mise en
évidence et porte la mention « sélectionné ». Le score de son équipe reste
en gras et souligné. L’onglet Événements liste les buts, les événements de
statistiques (`StatfeedEvent`) et les impacts sur la barre transversale.
Chaque joueur conserve ses derniers compteurs reçus : points, buts, tirs,
passes décisives, arrêts, touches de balle, contacts entre voitures et
démolitions. Quitter le match ne supprime pas ses statistiques.

Les buts conservent le buteur, le passeur éventuel, l’équipe, la vitesse et
la position du ballon lorsque ces informations sont disponibles. Les
vitesses sont en unités Unreal par seconde. Le chrono est la dernière
valeur reçue du jeu ; `GoalTime` reste séparé et représente la durée de la
manche précédente, pas le moment où le but a été marqué.
L’identité d’un événement est liée à un participant uniquement lorsque
l’identifiant ou la combinaison raccourci/équipe/nom permet une attribution
cohérente. Une identité non résolue reste manquante ; elle n’est jamais
attribuée sur le seul nom.

Une valeur manquante apparaît comme « — », distincte de zéro. Sans état
reçu après l’annonce du vainqueur, le score et les statistiques restent les
dernières valeurs observées, potentiellement partielles. Les états tardifs
complètent un résultat déjà enregistré sans compter le match une seconde
fois. Même avec un état de fin, les événements couvrent uniquement la
période de connexion ; les joueurs partis conservent leurs dernières
valeurs observées. Les ralentis de but et les replays d’anciens matchs ne
doivent ajouter ni statistiques ni événements.

SQLite conserve des tables structurées avec des identifiants internes,
des clés étrangères et des contraintes d’unicité. Aucun message JSON brut
ni trajectoire continue n’est gardé. Les buts sont des événements
`GoalScored`. Les événements identiques dans un même contexte de chrono
sont dédupliqués ; l’API ne fournit pas d’identifiant d’événement, donc deux
événements strictement identiques dans ce contexte ne peuvent pas être
distingués. La migration est automatique et conserve l’historique au même
emplacement. Les anciens matchs ne reçoivent pas de statistiques
rétroactivement.

## Diagnostic : onglet Logs

### Erreurs au démarrage

Si l’application ne démarre pas, la fenêtre d’erreur indique l’étape qui
échoue : fichiers de l’application, dossier de données, migration, base,
traductions ou lancement. Le diagnostic contient la version, l’exception
exacte, le chemin concerné et la trace d’exécution. **Copier le diagnostic**
le copie sans fermer la fenêtre. Rien n’est envoyé automatiquement. Les
chemins peuvent contenir le nom de votre compte Windows ; relisez le
diagnostic avant de le publier.

L’absence de base au premier lancement est normale : l’application la crée.
Ne supprimez pas une base existante pour résoudre une erreur. Pour la
version portable, extrayez toute l’archive et gardez ses fichiers ensemble.
Si un antivirus analyse l’application, attendez son verdict avant de
réessayer ; il n’est pas nécessaire de désactiver la protection pour lire
le diagnostic.

### Logs de connexion et d’événements

Après une mise à jour du code, redémarrez l’application puis ouvrez **Logs**.
Cet onglet conserve les 300 dernières entrées horodatées :

- Adresse WebSocket, connexion, déconnexion et erreurs exactes de la socket.
- Grandes étapes du match, notamment son début, les buts et sa fin, sans
  leur contenu JSON.
- Messages JSON invalides et motifs de rejet du suivi de match.
- Résultats enregistrés, nombre de messages et heure de la dernière réception.

Les mises à jour temps réel, le chrono et les événements de statistiques
répétitifs ne sont pas journalisés par défaut. Tous les messages alimentent
toujours le suivi, la vue en direct et le compteur de réception. Activez
**Détails API** pour inclure tous les événements et leur contenu JSON
masqué lors d’un diagnostic. Cette option est désactivée à chaque lancement
et ne concerne que les prochains messages, même si l’onglet Logs est masqué.

Les logs restent en mémoire, sans sauvegarde automatique dans un fichier.
Les noms et identifiants des messages détaillés sont masqués sans modifier
les données du suivi. Les entrées de plus de 2 000 caractères sont tronquées
avec une indication explicite. Les boutons permettent de copier ou vider
les logs, ou de suspendre leur défilement. Suspendre le défilement n’arrête
pas la collecte ; désactiver Détails API n’efface pas les entrées existantes.

L’API peut envoyer `Data` sous forme d’objet JSON ou de chaîne contenant du
JSON. Les deux formats sont décodés avant le suivi. Les logs détaillés
montrent le contenu normalisé. Un champ `Data` encodé invalide y est
entièrement masqué ; les logs normaux omettent le contenu et indiquent le
motif du rejet.

**Une connexion établie ne signifie pas que des événements arrivent.**
Après dix secondes sans message, l’application affiche un avertissement ;
cela peut être normal dans les menus. Vérifiez la réception pendant un
match. Avec `PacketSendRate=10`, les événements `UpdateState` sont attendus
dix fois par seconde lorsque le jeu envoie des données ; les autres
événements s’y ajoutent.

Si le compteur reste à zéro pendant un match :

1. Vérifiez `WebPort=49124` et le même port dans l’application.
2. Vérifiez les réglages de `[TAGame.MatchStatsExporter_TA]` et redémarrez
   complètement Rocket League après les avoir modifiés.
3. Vérifiez aussi le fichier utilisateur, s’il existe :
   `Documents\My Games\Rocket League\TAGame\Config\TAStatsAPI.ini`.
   Une valeur dans `DefaultStatsAPI.ini` seule ne décrit pas la configuration
   utilisateur. Les changements automatiques de débit concernent uniquement
   le fichier de l’installation explicitement sélectionnée, pas cette
   configuration utilisateur qui peut le remplacer.
4. Copiez les entrées de connexion, d’événements et de rejet depuis **Logs**.

La connexion et la réception sont distinctes du comptage : un événement
sans `MatchGuid` reste visible et son mode de jeu est affiché, mais aucun
résultat n’est enregistré sans identifiant de match fiable.

## Limites

- Le suivi commence à la réception des matchs ; cette API n’importe pas
  automatiquement l’historique du compte.
- Quitter un match, fermer l’application ou perdre la connexion avant le
  résultat produit un résultat inconnu, sans déduire une défaite.
- Un résultat confirmé reçu après reconnexion remplace un résultat inconnu.
- Les replays chargés sont exclus à l’aide de `ReplayCreated`. À la
  connexion, `bReplay=true` accompagné de `Frame` / `Elapsed` déclenche aussi
  cette exclusion. Ces champs seuls ne suffisent pas lorsque
  `bReplay=false`. Les ralentis de but pendant un match déjà suivi ne sont
  pas exclus. Une première connexion pendant un ralenti de but avec ces
  champs peut être ambiguë : consultez les logs.
- Seuls les matchs avec `MatchGuid` et une équipe connue pour le joueur
  sélectionné peuvent être comptés. L’entraînement n’est pas compté.
- Changer de joueur interrompt le suivi en cours. Le nouveau joueur est
  reconnu à la prochaine mise à jour envoyée par le jeu.
- Un arrêt brutal du processus ne peut pas sauvegarder le match en cours.

Les noms des modes de jeu viennent d’une table locale d’identifiants basée
sur cette [référence communautaire][playlist-ids]. Aucune installation de
BakkesMod n’est nécessaire ; toutes les données viennent de la Stats API
officielle.

[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
[playlist-ids]: https://bakkesplugins.com/wiki/bakkesmod-sdk/code-snippets/playlist-id
[screenshot]: images/rocket-lantern-matches.png
