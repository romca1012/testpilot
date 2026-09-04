# Utiliser l'API TestPilot

Ce document explique **comment lire et utiliser** l'API réelle de TestPilot. Ce n'est pas une
liste de routes — FastAPI en génère déjà une, à jour par construction. C'est un guide pour un
intégrateur : où trouver la documentation générée, comment s'authentifier, ce que chaque rôle
autorise, la forme des erreurs, et ce que signifie une réponse mise en file d'attente.

## 1. Où trouver la documentation générée

Une fois le serveur lancé (`uvicorn testpilot.api.app:app --reload`, voir `README.md`), FastAPI
sert deux vues interactives, générées depuis le code des routes (`src/testpilot/api/routes/`) :

- **`/api/docs`** — Swagger UI, interactif et protégé par la session : chaque route peut s'appeler directement depuis le
  navigateur (« Try it out »), pratique en développement.
- **`/api/redoc`** — ReDoc, lecture seule et protégée par la session : préférable pour parcourir l'ensemble des
  routes d'une traite.

Ces deux vues listent les **90 routes** réellement enregistrées dans
`src/testpilot/api/routes/*.py` à l'état actuel du dépôt (`auth`, `users`, `corbeille`, `projects`,
`modules`, `groups`, `runs`, `cases`, `executions`, `settings`), plus `/api/health` et le fallback
SPA déclarés directement dans `api/app.py`. Elles sont à jour par construction — elles
lisent directement les signatures et les modèles Pydantic (`api/schemas.py`) — mais leurs résumés
sont pour la plupart dérivés du nom de la fonction Python (`Health`, `Login`, `List Timezones`…),
pas rédigés pour un lecteur externe. Ne cherchez pas de prose dans Swagger : cherchez-y la forme
exacte d'une requête/réponse, les codes de statut possibles et les modèles de données. Pour
comprendre *pourquoi* une route se comporte ainsi, le code source de la route reste la référence —
chaque fichier de `api/routes/` commente ses propres décisions.

`GET /api/health`, `/api/health/live` et `/api/health/ready` ne demandent aucune authentification.
La première conserve le contrat historique, `live` vérifie le processus et `ready` vérifie la
base ainsi que le stockage. Ces routes confirment que
l'instance répond (voir §2).

## 2. Authentification

TestPilot authentifie par **cookie de session**, jamais par jeton porté dans un en-tête (pas
d'API-key à ce jour). Le modèle est entièrement dans `src/testpilot/api/routes/auth.py` et
`src/testpilot/api/access.py`.

### Ouvrir une session

```
POST /api/auth/login
{"username": "...", "password": "..."}
```

En cas de succès, la réponse pose un cookie `testpilot_session` :

- `HttpOnly` — inaccessible en JavaScript côté client ;
- `SameSite=Lax` — jamais envoyé sur une requête cross-site ;
- `Secure` si `TESTPILOT_COOKIE_SECURE=true` (obligatoire derrière HTTPS en production) ;
- durée de vie `TESTPILOT_SESSION_DAYS` jours (30 par défaut).

Un client HTTP doit conserver et renvoyer ce cookie sur chaque appel suivant — pas construire de
jeton lui-même. Il n'existe **pas** de mode d'authentification par en-tête pour un usage normal :
`access.utilisateur_de()` accepte un en-tête `X-TestPilot-User` en repli, mais il ne fait que
*nommer* l'auteur d'une action pour l'audit (`created_by`…) — il ne fournit **aucune**
authentification et n'est jamais suffisant seul pour passer le middleware d'accès.

### Ce que porte le jeton, et ce qu'il ne porte pas

Le cookie signe `expiration.user_id.session_version.username.signature` — **jamais le rôle**. À
chaque requête, le serveur relit en base le rôle, l'état actif et `session_version`. Une
déconnexion, un changement de mot de passe, de rôle ou d'état incrémente cette version : toute
copie d'un ancien cookie est immédiatement refusée. Un compte désactivé ou une session
invalide/expirée/révoquée reçoit un **401**.

### Vérifier l'état de la session

```
GET /api/auth/session
→ {"authenticated": true, "name": "...", "role": "...", "lock_enabled": true}
```

Utile pour qu'un frontend sache s'il doit afficher l'écran de connexion, sans provoquer de 401.

### Se déconnecter

```
POST /api/auth/logout
```

Cette route reste accessible même à un compte en lecture seule (voir §3). Elle efface le cookie et
révoque côté serveur tous les jetons précédemment émis pour ce compte.

### Limitation des tentatives

Après 5 échecs de connexion pour un même couple (adresse IP, identifiant) dans une fenêtre de 15
minutes, l'API répond **429** avec un en-tête `Retry-After`. La réponse d'échec ne distingue
jamais « identifiant inconnu » de « mot de passe faux » — un message trop précis faciliterait la
découverte d'identifiants valides par tâtonnement. Les échecs sont persistés dans la base : la
limite reste commune aux processus et ne disparaît pas lors d'un redémarrage.

### Premier compte

Une base neuve n'a aucun compte. Si `TESTPILOT_ADMIN_USERNAME` et `TESTPILOT_ADMIN_PASSWORD` sont
renseignées au démarrage **et** que la table des comptes est encore vide, un premier compte Admin
est créé automatiquement (`api/app.py::_amorcer_premier_admin`) — une seule fois, jamais rejoué si
un Admin existe déjà.

## 3. Rôles et ce qu'ils autorisent

Quatre rôles globaux, en hiérarchie strictement croissante — chacun hérite de tout ce que le
précédent permet (`api/access.py`, `ROLES`) :

| Rôle | Peut faire |
|---|---|
| `lecture_seule` | Consulter uniquement — aucune écriture nulle part. |
| `testeur` | + créer/éditer des cas, lancer des exécutions et campagnes, saisir des résultats manuels. |
| `dev` | + éditer directement le Gherkin/Python généré d'un cas (onglet Script). |
| `admin` | + gérer les comptes (créer, changer un rôle, activer/désactiver), réglages réservés. |

Deux couches de contrôle, appliquées côté serveur (jamais fait confiance à ce que renvoie
l'écran) :

1. **Le rôle global**, vérifié par le middleware `verrou_acces` (`api/app.py`) sur *toute* requête
   sous `/api/` : une méthode d'écriture (`POST`/`PUT`/`PATCH`/`DELETE`) est refusée en **403** si
   le rôle global est sous `testeur`.
2. **Le rôle effectif par projet** (`access.role_effectif_projet`), qui peut surclasser ou
   restreindre le rôle global sur un projet donné (accès par utilisateur, par groupe, ou un accès
   par défaut du projet). Toute route qui touche une ressource rattachée à un projet — directement
   (`project_id` dans le chemin) ou en profondeur (un cas, un module, une exécution, une pièce
   jointe, un job de génération) — vérifie ce rôle effectif, pas seulement le rôle global. Un
   compte sans accès à un projet reçoit **404** sur ses ressources, jamais 403 : un projet sans
   accès doit se comporter comme s'il n'existait pas, exactement comme un identifiant de connexion
   erroné ne doit pas révéler s'il correspond à un compte existant.

Un intégrateur qui obtient un 403 sur une écriture doit vérifier le rôle global du compte utilisé ;
un 404 inattendu sur une ressource qui existe doit faire vérifier l'accès par projet de ce compte,
pas seulement son rôle global.

## 4. Format d'erreur

Toutes les erreurs suivent RFC 9457 (`application/problem+json`), défini dans
`src/testpilot/api/erreurs.py` :

```json
{
  "type": "https://testpilot.local/erreurs/connexion_incomplete",
  "title": "La connexion du projet est incomplète",
  "status": 409,
  "detail": "La connexion du projet « Recette » est incomplète : le mot de passe.",
  "instance": "/api/v1/modules/3/cases",
  "code": "connexion_incomplete"
}
```

Le champ à tester dans le code d'un client est **`code`**, pas `detail` : `detail` est une phrase
destinée à un humain, libre d'évoluer sans préavis. `code` est un contrat stable — un catalogue
fermé (`CATALOGUE` dans `erreurs.py`) que seul le code source du serveur peut faire grandir, jamais
route par route. Exemples de codes du catalogue : `introuvable` (404), `nom_deja_pris` (409),
`connexion_incomplete` (409, la connexion du projet vers l'application testée est incomplète),
`relecture_requise` (409, un cas attend une relecture avant de pouvoir être exécuté),
`fichier_trop_gros` (413), `type_de_fichier_refuse` (415), `campagne_en_cours` (409). La liste
complète et à jour vit dans `erreurs.py` — c'est la seule source qui fait foi, puisqu'un nouveau
code ne peut être introduit qu'à cet endroit.

Toute `HTTPException` FastAPI qui n'est pas encore convertie individuellement passe malgré tout par
ce même format (repli par code de statut HTTP : 404 → `introuvable`, 409 → `etat_incompatible`,
422 → `requete_invalide`, sinon `non_gere`) — un client n'a donc jamais deux formats d'erreur
différents à gérer selon la route appelée.

## 5. Plafond de charge : une tâche peut attendre en file

Les actions qui démarrent un traitement long — générer un cas (`POST /api/modules/{id}/cases`),
lancer une exécution ou une campagne, démarrer une exploration — répondent immédiatement (**202**,
avec un identifiant de job/run) mais **le travail réel (appel LLM, navigateur Playwright) peut ne
pas démarrer tout de suite**.

Ces tâches passent par un admission-control en mémoire, borné, partagé par tout le processus
(`src/testpilot/guardrails/concurrency.py`) : au plus `TESTPILOT_MAX_CONCURRENT_JOBS` tâches (3 par
défaut) s'exécutent réellement en même temps ; au-delà, une tâche attend son tour dans une file
FIFO. Ce plafond existe parce qu'une tâche de génération ou d'exécution ouvre potentiellement un
navigateur Playwright réel et/ou un appel à l'API Anthropic — sans lui, des déclenchements
simultanés démarraient autant de navigateurs et d'appels LLM en parallèle, sans limite ni
visibilité.

Ce que ça veut dire pour un intégrateur :

- Un **202** ne garantit pas que le traitement a commencé — seulement qu'il a été accepté et mis en
  file. Il faut interroger le statut du job/run pour savoir où il en est (par exemple
  `GET /api/modules/jobs/{job_id}` pour une génération), pas déduire l'avancement du seul code 202.
- `GET /api/modules/jobs/queue/status` donne une photo de la file **partagée** à l'instant présent
  (`max_concurrent`, `running`, `waiting`) — malgré son préfixe `/modules/jobs`, elle couvre bien
  toutes les tâches de fond plafonnées par ce mécanisme (génération, exécution, exploration), pas
  seulement la génération : c'est l'endpoint de suivi de job déjà existant le plus proche, étendu
  plutôt que dupliqué.
- Le plafond d'exécution vit dans le processus, mais chaque tâche acceptée est d'abord inscrite
  dans `background_job`. Une tâche encore en attente au redémarrage est rejouée. Une tâche déjà
  active est marquée en échec et rendue relançable : elle n'est pas rejouée aveuglément, car un
  navigateur ou une application externe ne peut pas participer à une transaction exactement-une-
  fois. Sur plusieurs processus, chaque processus aurait encore son propre plafond ; ce mode reste
  donc réservé au déploiement mono-processus.
- Le plafond est un **frein sur un seul poste/serveur**, pas un ordonnanceur multi-instance : il
  n'a de sens que tant que TestPilot tourne en un seul processus.

## 6. Ce que ce document ne couvre pas

- La liste exhaustive des routes et leurs schémas de requête/réponse : `/api/docs` et `/api/redoc`, générés
  à jour à chaque démarrage du serveur.
- Le modèle de données (colonnes, contraintes) : `src/testpilot/store/schema.sql` et les migrations
  de `src/testpilot/store/db.py`.
- L'architecture générale (conteneurs, composants, décisions) : `docs/ARCHITECTURE.md`.
