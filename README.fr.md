# RocketLantern

[English](README.md) | [Français](README.fr.md)

<p align="center">
  <img src="src/rocket_lantern/assets/rocket-lantern-256.png"
       alt="Logo RocketLantern" width="128" height="128">
</p>

RocketLantern accompagne vos parties de Rocket League. Suivez les victoires
et défaites de votre soirée, retrouvez vos matchs ou gardez un œil sur le
boost de vos coéquipiers sur un second écran pendant que vous jouez.

Disponible sur Windows, en français et en anglais.

## Télécharger et installer

**[Télécharger la dernière version stable pour Windows][latest-release]**

Utilisez l’installateur Windows : ni Python ni outils de développement ne
sont nécessaires.

1. Ouvrez la page de la version et dépliez **Assets**.
2. Téléchargez `RocketLantern-<version>-windows-x64-setup.exe`.
3. Lancez l’installateur, puis ouvrez **RocketLantern** depuis le menu Démarrer.

L’installateur est prévu pour Windows x64 et ne demande pas les droits
administrateur. L’application n’est pas encore signée ; Windows peut donc
afficher un avertissement SmartScreen.

Vous préférez ne rien installer ? Téléchargez
`RocketLantern-<version>-windows-x64-portable.zip`, extrayez **toute**
l’archive, puis lancez `RocketLantern.exe` depuis le dossier extrait.

![Partie en cours et jauges de boost dans RocketLantern][screenshot]

Aperçu avec des joueurs et des données de match fictifs.

## Activer la Stats API de Rocket League

RocketLantern utilise la Stats API intégrée au jeu. Il faut l’activer une
fois avant votre premier match ; aucun plugin BakkesMod n’est nécessaire.

Au premier lancement, un assistant vous guide dans ces réglages. Vous
pouvez le passer et le retrouver dans **Paramètres → Assistant de démarrage**.

1. Fermez Rocket League.
2. Dans l’assistant ou les **Paramètres** de RocketLantern, cliquez sur
   **Vérifier les configurations** pour rechercher vos installations Steam
   et Epic Games.
   Nous recommandons de laisser **Débit souhaité (PacketSendRate)** à
   **10 paquets/s**. Cliquez sur **Appliquer** à côté d’une installation pour
   modifier son débit.
3. Cliquez sur **Ouvrir le dossier** pour accéder à son dossier
   `TAGame\Config`. Vérifiez `WebPort` dans `TAStatsAPI.ini`, ou dans
   `DefaultStatsAPI.ini` si le premier fichier n’existe pas.

Voici une configuration type. Modifiez la section existante plutôt que
d’en ajouter une seconde :

```ini
[TAGame.MatchStatsExporter_TA]
PacketSendRate=10
WebPort=49124
```

Relancez Rocket League après avoir enregistré les modifications.

RocketLantern se connecte par défaut à `127.0.0.1` sur le port `49124`. Si
vous utilisez un autre `WebPort`, ouvrez les **Paramètres**, renseignez le
même **Port local** et cliquez sur **Reconnecter**. Le port TCP `Port`, s’il
est activé, doit être différent de `WebPort`.

L’application ne modifie que `PacketSendRate` : la vérification de `WebPort`
reste à faire manuellement. Le fichier n’est modifié qu’au clic sur
**Appliquer** ; les autres réglages sont conservés et une sauvegarde est
créée. Un débit inférieur à votre cible signifie des mises à jour moins
fréquentes en direct. Un débit supérieur convient et n’a pas besoin d’être
réduit.

Si votre installation n’est pas détectée, retrouvez manuellement son dossier
`TAGame\Config` et modifiez les mêmes réglages. Si le jeu n’envoie toujours
pas de données, vérifiez la configuration utilisateur indiquée dans la
section [Dépannage](#dépannage).

La [documentation officielle de la Stats API][stats-api] donne davantage
de détails.

## Utiliser RocketLantern

1. Ouvrez RocketLantern, puis lancez un match dans Rocket League.
2. Sous Windows, votre compte Steam ou Epic est détecté automatiquement.
   Sinon, sélectionnez votre joueur dans la liste **Joueur**.
3. Gardez l’application ouverte jusqu’à la réception du résultat du match.

Sous Windows, RocketLantern attend le lancement du jeu pour se connecter.
Passer dans une autre application ne coupe pas le suivi des matchs.

Les changements de compte sont également détectés. Lorsque la détection
réussit, **Joueur** filtre l’historique sans changer le compte suivi dans
la partie en cours et l’overlay de boost.

Le suivi commence à ce moment-là : l’application n’importe pas les anciens
matchs de votre compte.

### Sessions et historique des matchs

Le bandeau affiche les victoires, les défaites, leur différence et le taux
de victoire pour la session et le mode de jeu en cours. Passez du 3v3 au 2v2
et il affiche vos résultats en 2v2 ; revenez en 3v3 et vous retrouvez ceux
de ce mode. Les filtres permettent de voir tous les modes, une ancienne
session ou l’ensemble de votre historique.

Une nouvelle session commence automatiquement après au moins une heure
entre deux résultats. **Nouvelle session** en démarre une immédiatement,
sans supprimer l’historique.

Dans **Matchs**, vous retrouvez votre historique, vos totaux et vos moyennes
par match pour les points, buts, passes décisives, arrêts, tirs, démolitions
et touches. Cliquez sur un match pour voir ses joueurs et événements, ou
sur **Détails de la session** pour consulter toute la session. Les valeurs
manquantes apparaissent sous la forme « — » ; un match rejoint en cours peut
avoir des données partielles.

Si vous quittez le match ou perdez la connexion avant la réception d’un
résultat confirmé, il est marqué **inconnu**, pas comme une défaite, et
exclu du taux de victoire. Les replays d’anciens matchs ne comptent pas dans
vos résultats.

### Partie en cours et boost des coéquipiers

Gardez **Partie en cours** ouvert sur un second écran pour voir le score,
le chrono, les statistiques des joueurs et les jauges de boost. Le score de
votre équipe est souligné. Le réglage **Boosts : À gauche / À droite** permet
de placer les jauges du côté qui vous convient.

Les jauges des coéquipiers passent du vert à l’orange puis au rouge lorsque
le boost diminue, avec une alerte animée lorsqu’il est vide. Celle du joueur
sélectionné reste grise. « ≈ 0 % » signale une valeur de boost manquante,
pas un zéro confirmé. Le boost et la vitesse sont affichés en direct, sans
être enregistrés sous forme de séries temporelles.

### Évaluation des matchs

Cliquez sur l’étiquette à droite du delta W/L pour choisir **Non évalué**,
**Aucune suspicion**, **Suspicion possible** ou **Forte suspicion**. Vous
pouvez changer ce choix pendant la partie ou plus tard, depuis l’étiquette
du match dans l’historique. Chaque choix a son propre symbole et un libellé
au survol. Ce sont des notes personnelles sur une suspicion de smurfing,
pas une détection automatique ni un signalement à Epic.

Pour évaluer un match sans quitter le jeu, cochez **Activer les raccourcis
clavier globaux** dans les **Paramètres**, puis cliquez sur **Appliquer les
raccourcis**. Ils sont désactivés par défaut ; **Ctrl+Maj+F1** à **F4**
sélectionnent les quatre choix ci-dessus. Le
[guide utilisateur](docs/user-guide.fr.md#évaluation-des-matchs)
détaille la configuration des touches et le choix du match en cours ou du
dernier match.

## Paramètres et mises à jour

Ouvrez les **Paramètres** depuis la barre supérieure pour changer la langue
ou choisir l’onglet affiché au lancement : **Matchs** ou **Partie en cours**.
La langue change immédiatement et vos préférences sont mémorisées pour le
prochain lancement.

Le canal sélectionné par défaut est **Mise à jour stable**. Choisissez
**Désactivé** pour arrêter les vérifications, ou **Toutes les mises à jour
(instable)** pour essayer les versions en développement, qui peuvent
comporter des bugs. Les vérifications ont lieu au démarrage puis toutes les
dix minutes lorsqu’elles sont activées. **Vérifier maintenant** permet de
lancer une recherche manuelle.

Lorsqu’une version plus récente est disponible, une icône de téléchargement
apparaît à côté du nom de l’application : verte pour une version stable,
orange pour une préversion. Un clic demande confirmation avant de
télécharger ou d’ouvrir le navigateur. La version installée peut télécharger
un installateur vérifié et lancer l’assistant d’installation. RocketLantern
se ferme pour permettre la mise à jour. Dans les autres cas, notamment avec
une version portable, la page de téléchargement s’ouvre pour une mise à jour
manuelle. Votre historique est conservé.

## Données locales et confidentialité

L’historique, les statistiques, les évaluations et les préférences sont
enregistrés localement dans :

```text
%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3
```

Cela inclut les noms et identifiants des joueurs. Les mises à jour et la
désinstallation ne suppriment pas cette base, et aucun compte supplémentaire
n’est nécessaire. Les vérifications de mise à jour contactent GitHub, mais
n’envoient ni données de joueurs ni données de matchs. Choisissez
**Désactivé** dans les Paramètres pour arrêter ces requêtes.

## Dépannage

**Connecté, mais aucun match ni événement ?**

- Vérifiez la réception pendant un match : l’absence de données dans les
  menus du jeu peut être normale.
- Vérifiez que le `WebPort` du jeu correspond au **Port local** de
  RocketLantern.
- Redémarrez complètement Rocket League après une modification de sa
  configuration.
- Si elle existe, vérifiez aussi la configuration utilisateur dans
  `Documents\My Games\Rocket League\TAGame\Config\TAStatsAPI.ini`.
- Ouvrez **Logs** pour voir les erreurs de connexion et les événements reçus.
  Les logs restent en mémoire ; les noms et identifiants des joueurs sont
  masqués.

Pour aller plus loin, consultez le
[guide utilisateur](docs/user-guide.fr.md#diagnostic--onglet-logs).

## Pour aller plus loin

- [Versions et téléchargements][releases]
- [Guide utilisateur détaillé](docs/user-guide.fr.md)
- [Overlay de boost et fair-play](docs/boost-overlay-fair-play.fr.md)
- [Développement, builds Windows et publication](docs/development.md)
  (en anglais)

[latest-release]: https://github.com/akerfourn/rocket-lantern/releases/latest
[releases]: https://github.com/akerfourn/rocket-lantern/releases
[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
[screenshot]: docs/images/rocket-lantern.png
