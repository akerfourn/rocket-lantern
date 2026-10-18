# Overlay de boost : sources et position de RocketLantern

[English](boost-overlay-fair-play.md) | Français

Sources consultées le 18 octobre 2026.

RocketLantern propose une autre présentation du boost des coéquipiers.
Notre position est qu’il s’agit d’une personnalisation d’interface, pas
d’un outil destiné à tricher. Voici les sources et les choix techniques
sur lesquels repose cette position.

## Le choix d’interface expliqué par Psyonix

Dans son [annonce officielle du 15 avril 2024][announcement], Psyonix
présente les jauges de boost des coéquipiers sur leurs plaques nominatives.
Le studio justifie ce choix plutôt qu’un affichage permanent dans l’ATH
par la lisibilité et la distraction :

> pourrait être difficile à suivre et pourrait vous distraire.

Le même article souligne aussi l’intérêt de cette information pour les
décisions d’équipe. Nous comprenons ce choix comme un arbitrage de
lisibilité : RocketLantern propose un autre compromis d’affichage,
laissé au choix de l’utilisateur.

## Ce que fait notre overlay

L’implémentation actuelle :

- reçoit les messages de la Stats API locale intégrée au jeu ;
- affiche uniquement les coéquipiers du joueur sélectionné, sans son
  propre boost ni celui des adversaires ;
- utilise une fenêtre externe, sans injection, lecture de mémoire de jeu,
  automatisation des actions ou contournement de l’anti-triche ;
- ne reconstruit pas un boost caché à partir des déplacements ou des
  ramassages.

Ces points sont vérifiables dans le [client API][client], le
[filtre des coéquipiers][filter], les [jauges][gauges] et le
[placement Windows][windows]. Ce dernier identifie le processus au premier
plan et gère notre fenêtre ; cela ne lit pas la mémoire de gameplay.

## Pourquoi nous y voyons une personnalisation d’affichage

Le jeu propose déjà une indication du boost des alliés. RocketLantern
reprend cette ressource d’équipe dans une présentation indépendante,
adaptée aux préférences de chacun. Le joueur garde la main sur ses
décisions et ses actions ; l’overlay ne joue pas pour lui et ne présente
pas le boost de ses adversaires.

Notre position repose sur ce périmètre : proposer une autre présentation
des informations d’équipe transmises par le jeu, sans modifier ses
mécaniques ni contourner ses protections.

## Des données filtrées par le jeu

Le comportement observé par les utilisateurs du projet distingue les rôles :
un spectateur reçoit le boost des deux équipes, tandis qu’un joueur reçoit
celui de ses coéquipiers, pas celui des adversaires. Ce filtrage est cohérent
avec un accès aux informations adapté au rôle du client.

La [documentation de la Stats API][stats-api] décrit elle-même plusieurs
niveaux de visibilité, notamment **TEAM** et **SPECTATOR**. Le détail du
champ `Players.Boost` reste marqué **SPECTATOR** ; une description incomplète
du cas joueur est une explication possible de cette différence, alors que
le comportement observé applique un filtrage par équipe.

RocketLantern utilise les informations effectivement transmises par le jeu,
sans chercher à obtenir les valeurs que celui-ci ne fournit pas.

## Statut et précautions

Le [Code de conduite de Rocket League][conduct], rubrique « Mods tiers »,
interdit les avantages compétitifs en ligne. Les
[Conditions d’utilisation d’Epic, section 4][terms], interdisent notamment
les outils de triche et leur distribution.

Notre position n’est pas une autorisation officielle d’Epic/Psyonix.
En l’absence d’une confirmation écrite sur cet usage précis, nous conservons
une option désactivée par défaut et un avertissement sur le risque de
sanction, accepté avant la première activation. Cette note ne garantit
donc pas l’absence de bannissement et ne remplace pas les règles du jeu
ou celles d’une compétition.

[announcement]: https://www.rocketleague.com/news/teammate-boost-indicators-and-rarity-name-changes-coming-to-rocket-league?lang=fr
[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
[conduct]: https://www.rocketleague.com/code-of-conduct?lang=fr
[terms]: https://legal.epicgames.com/epicgames/tos?lang=en-US
[client]: ../src/rocket_lantern/client.py
[filter]: ../src/rocket_lantern/boost_overlay.py
[gauges]: ../src/rocket_lantern/boost_gauge.py
[windows]: ../src/rocket_lantern/windows_overlay.py
