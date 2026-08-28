# Périmètre figé — V1 bêta interne

**Statut :** candidat au déploiement pilote  
**Date de cadrage :** 24 août 2026  
**Public :** 1 à 3 équipes internes connues  
**Objectif :** valider en usage réel la promesse centrale de TestPilot sans attendre les
fonctionnalités de personnalisation avancées.

## 1. Promesse de la bêta

Un utilisateur autorisé peut accéder à un projet, créer ou générer des cas de test, les relire,
les exécuter manuellement ou automatiquement, puis consulter un résultat traçable et honnête.

La bêta n'a pas pour objectif de reproduire tout TestRail. Elle doit prouver que ce parcours est
fiable, compréhensible et correctement isolé entre les équipes.

## 2. Fonctionnalités incluses

### Accès et projets

- connexion par compte utilisateur ;
- activation et désactivation des comptes ;
- rôles Admin, Dev, Testeur et Lecture seule ;
- sélection explicite du projet après la connexion ;
- membres et rôle propres à chaque projet ;
- isolation des données entre projets ;
- création et modification d'un projet ;
- connexion cible du projet chiffrée au repos.

### Référentiel de tests

- modules, groupes et cas de test ;
- création et modification manuelles d'un cas ;
- génération de cas à partir d'une spécification ;
- relecture humaine avant utilisation ;
- états New, Ready et Obsolete ;
- classification fonctionnelle ou non fonctionnelle ;
- priorité et référence vers une exigence ;
- archivage et corbeille selon les fonctions déjà disponibles.

### Exécutions et résultats

- création d'une campagne/exécution ;
- sélection des cas à exécuter ;
- exécution manuelle ;
- exécution automatisée pour le connecteur actuellement pris en charge ;
- résultats conformes, non conformes, techniquement en erreur ou fondés sur des données invalides ;
- conservation de la cible et des artefacts d'exécution ;
- clôture et consultation de l'historique.

### IA et qualité

- génération assistée par IA ;
- structuration des scripts automatisés ;
- garde-fous de coût et de réparation existants ;
- tableau de bord de qualité de génération ;
- absence de faux verdict lorsque l'exécution n'a pas réellement abouti.

## 3. Fonctionnalités explicitement hors bêta

Les éléments suivants ne bloquent pas le pilote et ne doivent pas être ajoutés pendant la phase de
stabilisation, sauf décision explicite après retour utilisateur :

- champs personnalisables des projets ;
- environnements multiples par projet ;
- scheduler et exécutions récurrentes ;
- plans de test avancés et matrices de configurations façon TestRail ;
- étiquettes sur les cas ;
- connecteurs SAP, Web générique et autres connecteurs supplémentaires ;
- gestion de projet type Jira ;
- tests de charge et de sécurité ;
- intégration CI/CD complète ;
- portail destiné à des clients externes ;
- exposition directe sur Internet ;
- haute disponibilité et montée en charge horizontale.

Les écrans ou boutons correspondant à une fonction non disponible ne doivent pas être montrés comme
utilisables. Ils sont retirés ou clairement désactivés avec une explication.

## 4. Parcours de validation obligatoire

La release est validée seulement si les scénarios suivants réussissent sur l'artefact destiné au
serveur pilote :

1. Un administrateur crée ou active deux comptes et deux projets.
2. Chaque utilisateur ne voit que les projets auxquels il appartient.
3. Une tentative d'accès direct à une ressource d'un autre projet est refusée sans révéler son
   existence.
4. Un utilisateur crée un cas manuel, le classe, ajoute une référence d'exigence et l'enregistre.
5. Un utilisateur génère un cas avec l'IA, le relit et l'approuve.
6. Une campagne contenant des cas de plusieurs modules est créée.
7. Un résultat manuel est saisi et reste visible après reconnexion.
8. Une exécution automatisée conserve sa cible, son verdict et ses artefacts.
9. Un compte Lecture seule ne peut effectuer aucune écriture.
10. La désactivation d'un compte invalide immédiatement son accès.
11. Les thèmes clair et sombre n'occultent aucune action principale.
12. Une sauvegarde est restaurée sur une instance de contrôle avec les projets, cas et résultats.

## 5. Règles de décision des anomalies

### Bloque le déploiement

- perte, corruption ou mélange de données entre projets ;
- contournement d'une autorisation ;
- secret affiché ou stocké en clair ;
- impossibilité de se connecter, créer un cas, lancer une campagne ou consulter un résultat ;
- verdict présenté comme concluant sans preuve d'exécution ;
- migration destructive ou restauration impossible ;
- échec du build de production ou de la suite de tests de référence.

### Peut attendre après le pilote

- défaut cosmétique sans perte d'action ni d'information ;
- texte perfectible ;
- filtre ou tri de confort ;
- type de champ ou paramètre supplémentaire ;
- automatisation non indispensable au parcours principal.

## 6. Conditions d'exploitation du pilote

- serveur interne derrière HTTPS ;
- secrets de chiffrement et de session fournis par l'environnement ;
- accès limité aux équipes pilotes ;
- sauvegarde quotidienne de `data/` et copie séparée des clés ;
- surveillance de l'espace disque et des erreurs applicatives ;
- un seul serveur applicatif et un volume limité d'utilisateurs simultanés ;
- procédure documentée pour démarrer, arrêter, sauvegarder et restaurer l'instance.

## 7. Critère de succès du pilote

Pendant une semaine, au moins deux profils utilisateurs réalisent le parcours principal sur des
projets distincts sans anomalie bloquante ni fuite de données. Les retours sont classés en :

- anomalie à corriger ;
- amélioration d'ergonomie ;
- besoin métier à faire valider ;
- fonctionnalité hors périmètre.

Le manager arbitre ensuite l'ordre des chantiers suivants à partir de ces retours. Les champs
personnalisables, les environnements et le scheduler ne sont donc pas présumés prioritaires avant
cette revue.

## 8. État des validations

### Étape 2 — Comptes, rôles et isolation des projets

**Contrôle automatisé du 24 août 2026 : conforme.**

- 108 tests backend réussis sur les comptes, rôles, accès par projet, accès profonds/IDOR,
  administration des membres et protection des secrets ;
- 7 tests frontend réussis sur la sélection explicite du projet, la gestion des utilisateurs et
  la navigation selon les droits ;
- aucun défaut de code détecté par ce lot ciblé.

Contrôles manuels restant à effectuer sur l'instance candidate avant le GO pilote :

- connexion réelle avec chacun des quatre rôles ;
- tentative d'ouverture par URL d'un projet non autorisé ;
- désactivation d'un compte pendant qu'une session est ouverte ;
- vérification visuelle des messages 401, 403 et 404 ;
- consultation de la trace d'audit après ajout, changement de rôle et retrait d'un membre.

Point d'exploitation distinct du produit : le lanceur `python.exe` du `.venv` local doit être
réparé ou recréé avant de préparer l'artefact de déploiement. Les tests ont été exécutés avec
Python 3.12 et les dépendances déjà présentes dans ce `.venv`.

### Étape 3 — Parcours utilisateur complet

**Contrôle automatisé du 24 août 2026 : conforme.**

- 103 tests backend réussis sur le parcours API, les projets, la création et la génération de cas,
  les campagnes, la saisie manuelle, les exécutions et le tableau de qualité ;
- suite frontend complète réussie : 37 fichiers et 218 tests ;
- écran de connexion vérifié dans un navigateur réel sur `http://localhost:5173` en thème clair ;
- aucun défaut bloquant détecté par les contrôles automatisés.

La validation navigateur au-delà de la connexion reste à effectuer avec un compte de test autorisé.
Elle doit couvrir la sélection du projet, la création d'un cas manuel, la création d'une campagne,
la saisie d'un résultat et la consultation du tableau de qualité. Elle ne doit pas modifier les
données de référence sans accord explicite de l'utilisateur.

La suite frontend émet encore des avertissements de banc de test (`RouterLink` non simulé et
quelques propriétés absentes dans certains montages isolés). Ils ne font échouer aucun test mais
doivent être nettoyés avant de rendre la CI strictement silencieuse.

**Contrôle navigateur authentifié du 24 août 2026 : conforme avec une correction appliquée.**

- sélection explicite de `Portail Sapian` après connexion ;
- référentiel chargé avec 1 module, 2 sections et 7 cas ;
- formulaire de création manuelle cohérent et validation du bouton observée ;
- campagne R24 consultée avec répartition, statuts et origine manuelle du résultat ;
- dialogue d'ajout de résultat cohérent, sans enregistrement de donnée pendant l'audit ;
- tableau Qualité cohérent avec 3 réussites techniques et 1 erreur, soit 75 % ;
- thème sombre contrôlé : les actions Créer et Annuler restent visibles ;
- action factice « Ajouter un plan », route correspondante et encart « Pas encore construit »
  retirés de la bêta ; test de non-régression et vérification de types réussis.

### Préparation de l'artefact de déploiement

**Contrôle du 24 août 2026 : conforme pour l'artefact local.**

- option `TESTPILOT_COOKIE_SECURE` ajoutée et testée pour imposer le cookie sous HTTPS ;
- `.env.example` aligné sur les comptes, la clé de session et l'amorçage du premier Admin ;
- documentation actuelle créée dans `docs/DEPLOIEMENT-V1-BETA.md` ;
- environnement Python 3.12 de nouveau exécutable avec ses dépendances ;
- 45 tests ciblés comptes, cookie et secrets réussis ;
- frontend de production compilé avec succès ;
- artefact servi temporairement par FastAPI sur le port de contrôle 8020 ;
- `/api/health` répond `ok`, `/` répond 200 avec TestPilot et `/api/projects` sans session répond
  401 ;
- serveur de contrôle arrêté après la vérification.

Restent externes au dépôt avant le déploiement pilote : choix du serveur, nom DNS interne,
certificat/reverse proxy HTTPS, coffre de secrets, emplacement des sauvegardes et test de
restauration sur cette infrastructure.
