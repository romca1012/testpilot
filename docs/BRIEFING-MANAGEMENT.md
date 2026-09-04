# TestPilot, où on en est

> Document de synthèse à destination du management — sans jargon technique. Le détail
> d'ingénierie (architecture, API, déploiement, exploitation) est documenté séparément pour
> l'équipe qui opère l'outil : voir `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPLOIEMENT.md`,
> `docs/EXPLOITATION.md`.
>
> Version présentable (mise en page) : [artifact publié](https://claude.ai/code/artifact/a2489548-90f6-46a1-b334-52706188f9af).
> Ce fichier en est la version texte, versionnée avec le code.

**3 septembre 2026.**

Un outil qui écrit, fait valider et exécute réellement les tests de vos applications métier —
pour que « c'est testé » ne soit plus une case cochée de mémoire, mais la trace d'une exécution
qui a vraiment eu lieu.

## En quatre chiffres

| | |
|---|---|
| **1 848** | vérifications automatiques rejouées à chaque changement de code |
| **2** | moteurs de base de données supportés (léger pour un pilote, robuste pour plusieurs équipes) |
| **90** | fonctions exposées par le service |
| **0** | perte de donnée constatée |

## Ce que ça fait, en une idée

La plupart des outils de gestion de tests laissent un humain cocher « passé » sans garantie que
quoi que ce soit se soit produit. TestPilot force le passage par une exécution réelle, dans un
navigateur, contre l'application testée.

```
1. Rédiger   — l'IA propose, un humain valide le métier
2. Exécuter  — un vrai navigateur pilote l'application testée
3. Constater — un verdict, jamais une supposition
```

Le verdict retenu est toujours l'une de ces quatre réponses — jamais un simple « ok » :

- **conforme** — le test a tourné, l'application se comporte comme attendu ;
- **non conforme** — le test a tourné, un vrai écart a été trouvé ;
- **erreur technique** — le test n'a pas pu s'exécuter (ce n'est pas un verdict sur l'application) ;
- **donnée du test invalide** — ce sont les données saisies par le test, pas l'application, qui
  ont été refusées.

> Une règle prime sur tout le reste : l'outil n'accuse jamais l'application sans preuve. S'il
> n'est pas sûr de ce qui s'est passé, il le dit — il n'invente pas un défaut.

## Comment c'est construit

Une interface que l'équipe utilise dans son navigateur, un service qui orchestre tout, et une
base de données qui garde l'historique — hébergés sur votre infrastructure, jamais chez un tiers.

- **L'interface** — l'écran que l'équipe utilise pour créer des projets, lire et valider des cas
  de test, lancer des campagnes.
- **Le service** — écrit les tests avec l'aide d'un modèle d'IA (Anthropic), les exécute
  réellement, calcule le verdict. C'est la seule brique qui appelle un service externe, et
  uniquement pour la rédaction — jamais vos données de production.
- **La base de données** — l'historique complet : projets, cas, exécutions, coûts, comptes.
  Sauvegardée automatiquement, jamais effacée en silence — supprimer quelque chose passe toujours
  par une « corbeille » récupérable avant toute suppression définitive.

Le seul système externe que TestPilot pilote directement est l'application que vous lui demandez
de tester — aujourd'hui Odoo, avec la possibilité d'en ajouter d'autres sans reconstruire l'outil.

## État réel, pas une promesse

Chaque ligne ci-dessous a été vérifiée en la faisant tourner réellement, pas supposée.

**Acquis** :

- Comptes, rôles, accès par projet — chaque personne ne voit et ne modifie que ce que son rôle
  autorise, contrôlé côté serveur.
- Vérification continue — 1 848 contrôles rejoués automatiquement à chaque modification du code,
  avant toute mise à disposition.
- Sauvegarde automatique — avant chaque mise à jour du schéma de données, plus une sauvegarde
  périodique programmable, testée par un cycle complet perte→restauration.
- Choix du moteur de base de données — léger pour un pilote (SQLite) ou robuste pour plusieurs
  équipes (PostgreSQL), les deux vérifiés en conditions réelles.
- Plafond de charge — un pic d'usage simultané est mis en file persistée. Une tâche en attente
  reprend après redémarrage ; une tâche interrompue est signalée et relançable, sans doublon caché.

**Pas encore** :

- Bascule vers un serveur de production — tout est prêt et vérifié, reste à décider quand et sur
  quel environnement.
- Un deuxième connecteur d'application — l'architecture l'anticipe, mais seul Odoo est branché
  aujourd'hui.
- Chiffres de coût par cas — mesurés sur un échantillon encore restreint, à confirmer sur un
  volume réel avant d'en faire une référence.

## Ce qui attend votre décision

Trois choix, pas des tâches techniques.

**Quand et où basculer en production ?** Le travail technique est fait et vérifié. Ce qui manque,
c'est de savoir quel serveur/environnement doit devenir « la vraie instance » — et une fenêtre
pour y basculer sans perturber une équipe qui l'utilise déjà.

**Rester sur un serveur interne, ou aller vers le cloud ?** Les deux sont possibles dès
aujourd'hui. Le cloud (ex. hébergement managé) simplifie la sauvegarde et la montée en charge si
plusieurs équipes s'en servent en même temps ; un serveur interne reste plus simple à opérer pour
un usage restreint.

**Quel est le prochain connecteur à financer ?** Odoo fonctionne. Étendre à une autre application
(SAP, un portail web...) est un investissement ciblé, pas une reconstruction — mais ça reste un
choix de priorité, pas une évidence technique.
