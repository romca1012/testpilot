# Correctif — dépendance `websockets` manquante (bug trouvé en test réel sur staging)

## Symptôme

Testé en direct sur staging après le déploiement du frontend (PR #43) : ouvrir l'écran
« Enregistrer la connexion » affichait immédiatement « Session terminée — la connexion avec le
serveur a été interrompue », sans jamais recevoir la moindre image du flux vidéo.

## Diagnostic (mené avec le porteur, en direct sur le serveur)

1. Écarté d'abord l'hypothèse la plus probable a priori (reverse proxy qui ne relaie pas l'upgrade
   WebSocket) : les autres appels HTTP passent très bien par le même Traefik + `stripprefix`, et
   Traefik v3 gère l'upgrade nativement sans configuration spéciale.
2. `docker logs staging-app` a montré la vraie cause :
   ```
   WARNING:  No supported WebSocket library detected. Please use "pip install 'uvicorn[standard]'",
             or install 'websockets' or 'wsproto' manually.
   INFO:     GET /api/projects/4/live-session/ws?token=... HTTP/1.1" 404 Not Found
   ```
   `pyproject.toml` déclare `uvicorn>=0.32` **sans l'extra `[standard]`** — `websockets`/`wsproto`
   n'a donc jamais fait partie des dépendances verrouillées, alors que la route WebSocket existe
   depuis le sous-lot C de ce chantier. Sans bibliothèque WebSocket, Uvicorn démarre sans erreur
   bloquante (l'avertissement reste dans son propre log, jamais remonté à l'appelant) mais traite
   toute tentative d'upgrade comme une requête HTTP normale — qui retombe en 404 faute de route
   HTTP à cette adresse (seule une route `@router.websocket(...)` existe, qui n'enregistre aucune
   route HTTP).

## Pourquoi aucun test ne l'a détecté

`tests/test_live_session_ws.py` (et tous les tests du chantier) passent par
`starlette.testclient.TestClient.websocket_connect`, qui parle directement à l'application ASGI
**en mémoire**, sans jamais passer par un vrai serveur Uvicorn ni un vrai protocole WebSocket
réseau. C'est un angle mort structurel : aucune revue de code, aucune mesure en CI n'aurait pu le
voir — il fallait un vrai déploiement, avec un vrai Uvicorn, pour qu'il se manifeste. Signalé
explicitement ici plutôt que laissé implicite, conformément au principe « mesurer avant de
supposer » de ce dépôt.

## Correctif

`pyproject.toml` : ajout de `"websockets>=13"` comme dépendance principale (pas un extra groupé —
`uvicorn[standard]` embarquerait aussi `uvloop`/`httptools`/`watchfiles`/`python-dotenv`/`pyyaml`,
inutiles ici, ajoutés pour du rechargement à chaud ou des perfs qu'on ne recherche pas en
production). `requirements.lock` : ajout manuel de la seule ligne `websockets==17.1` — une
régénération complète via `pip-compile` a été essayée puis écartée (elle faisait aussi disparaître
`tzdata==2026.3 # via psycopg`, une différence de résolution propre à l'environnement local de
vérification, sans rapport avec ce correctif — gardée pour ne pas élargir le diff au-delà de ce qui
est réellement nécessaire).

## Vérification (avec un VRAI Uvicorn, pas `TestClient`)

- Environnement neuf (`python3.12 -m venv`, `pip install -r requirements.lock`), serveur réel lancé
  (`python -m uvicorn testpilot.api.app:app`).
- Avant correctif (bibliothèque désinstallée) : reproduit exactement le symptôme observé sur
  staging — `WARNING: No supported WebSocket library detected`, la tentative de connexion aboutit
  à un statut HTTP classique (401/404 selon l'authentification du client de test — la différence
  de code entre les deux ne change rien au mécanisme : dans les deux cas, la requête traverse tout
  le pipeline HTTP au lieu de basculer en WebSocket).
- Après correctif : aucun avertissement au démarrage ; une tentative de connexion WebSocket réelle
  échoue désormais **au niveau du protocole WebSocket lui-même** (statut 403 à la bascule, jeton
  invalide correctement rejeté par la route) — la bascule a réellement lieu.

## Mesures

`pytest -q` (suite complète) : voir le rapport de fin de lot pour le résultat consigné.
`ruff check --select E9,F63,F7,F82` : vert.

## Ce que ça implique pour dev et staging

Une fois ce correctif fusionné et l'image reconstruite (dev automatiquement à la CI verte,
staging manuellement comme d'habitude), la fonctionnalité « Enregistrement assisté du chemin de
connexion » redevient réellement utilisable en conditions réelles — elle ne l'a jamais été depuis
sa mise en ligne initiale sur ces deux environnements, malgré tous les tests verts.
