## Lot « Enregistrement assisté du chemin de connexion » — sous-lot C — relais WebSocket, capture, confirmation, fermeture garantie — terminé (en attente de revue verdict-reviewer, de CI, et de fusion)

Décisions utilisées : aucune décision `D#` du registre du chantier `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — ce lot est
hors de ce chantier (voir rapports des sous-lots A et B). Deux décisions structurantes tranchées avec le porteur en
session avant de coder :
- Forme de stockage de la séquence confirmée : **un bloc JSON par projet** (`steps_json`), pas une table à part par
  étape — le rejeu lit toujours la séquence entière dans l'ordre.
- Sous-lot propriétaire de la migration : **sous-lot C** (qui écrit, à la confirmation), pas le sous-lot D (qui ne
  fera que lire pour le rejeu).

### Ce que le sous-lot change, en clair

Ce sous-lot construit la session en direct elle-même : un vrai navigateur, piloté à distance par WebSocket, qui
capture le chemin de clics avant qu'un champ mot de passe ne redevienne visible, avec confirmation explicite et
fermeture garantie.

### Changements

- Migration 55 (`project_login_recording`) : une seule séquence active par projet (JSON), créée par ce sous-lot.
- `src/testpilot/api/services/live_session_service.py` (nouveau) — `SessionLive` : navigateur Playwright **synchrone**
  dans un **thread dédié**, jamais mélangé à la boucle asyncio. Relais vidéo par CDP (`Page.startScreencast`) complété
  d'une capture explicite initiale (`page.screenshot()`) — **découverte mesurée, pas supposée** : le mode headless
  « nouveau » (défaut de Chromium/Playwright) ne délivre **jamais** d'événement `Page.screencastFrame` (0 frame reçue
  en 2 s sur une page qui change activement) ; `--headless=old` est nécessaire, et même ainsi, CDP n'émet une frame
  qu'au moment d'un changement visuel réel — une page chargée puis immobile n'envoie spontanément aucune image.
  Clics appliqués sur le vrai navigateur via `Input.dispatchMouseEvent`. À chaque clic : `accname.calculer` (sous-lot
  A) est appelé **avant** le clic réel (capture l'état du DOM tel qu'il était au moment du clic, pas après ses
  effets). Capture arrêtée automatiquement dès qu'un champ mot de passe redevient visible (détection dupliquée de
  `behave_runtime/steps_library/_base_helpers.py::_mot_de_passe_visible`, même convention de duplication
  cross-paquet que `accname.ElementIntrouvableError`). La place dans la file de concurrence (`held()`, sous-lot B)
  est tenue pour la durée ENTIÈRE du thread.
- `src/testpilot/api/routes/live_session.py` (nouveau) — route WebSocket, authentifiée par le jeton dans l'URL
  (`@app.middleware("http")` ne s'exécute jamais sur une connexion WebSocket, vérifié). Jeton consommé **avant**
  `websocket.accept()`. Timeout à deux niveaux, indépendants : inactivité (repart à chaque clic, avertissement 1 min
  avant fermeture) et plafond absolu (filet de sécurité, mord même sous activité continue). `confirmer` écrit dans
  `project_login_recording` ; `annuler` n'écrit rien ; `recommencer` vide la liste en mémoire. Fermeture garantie dans
  un `finally` qui s'exécute aussi sur `WebSocketDisconnect`.
- `src/testpilot/store/project_login_recordings.py`, `.github/workflows/generation-quality.yml`, `api/app.py`
  (routeur enregistré).

### Tests ajoutés

- `tests/test_migration_project_login_recording.py` (6), `tests/test_project_login_recordings.py` (6) — migration et
  dépôt, mêmes conventions que les sous-lots précédents.
- `tests/test_live_session_ws.py` (10, marqueur `conformance`, **vrai Chromium + vraie route WebSocket** via
  `TestClient`) :
  - jeton inventé refusé avant ouverture ; jeton déjà consommé refusé une deuxième fois.
  - relais vidéo reçoit une vraie image.
  - un clic réel capture le bon rôle/nom (vérifié contre le contenu réel de la page).
  - un champ mot de passe qui redevient visible arrête la capture.
  - confirmer écrit la séquence exacte ; annuler n'écrit rien ; recommencer vide la liste avant confirmation.
  - **falsifiable, exigé par l'étape 7** : coupure brutale (fermeture du transport sans `annuler`/`confirmer`) →
    la place de la file de concurrence est bien libérée dans les 10 s.
  - **falsifiable, exigé par l'addendum timeout** : inactivité seule ferme la session avec avertissement préalable ;
    une activité continue (clics répétés) n'empêche PAS le plafond absolu de fermer la session.

### Critères d'acceptation

- [x] WebSocket dans l'application existante, même port, authentification par jeton (étape 4).
- [x] Relais vidéo + clics appliqués via CDP (étape 4).
- [x] Capture du rôle/nom à chaque clic réel, en mémoire (étape 5).
- [x] Arrêt automatique dès qu'un champ mot de passe redevient visible (étape 5).
- [x] Rien n'est sauvegardé sans confirmation explicite ; annulation possible (étape 6).
- [ ] « Recommencer » : implémenté (vide la liste), mais aucun écran ne montre encore la liste capturée à la personne
      — aucun frontend n'existe pour ce sous-lot (voir Écarts).
- [x] Fermeture garantie même sur coupure brutale, testé et falsifié (étape 7).
- [x] Timeout à deux niveaux (addendum) : inactivité avec avertissement, plafond absolu indépendant, tous deux
      testés et falsifiés séparément.

### Mesures

- `pytest -q -m conformance tests/test_live_session_ws.py` : 10 passed (~19 s, vrai Chromium).
- `pytest -q` (suite par défaut) : en cours de vérification finale au moment de ce rapport (lancée sur ce SHA, à
  confirmer avant PR — voir le message de suivi de session).
- `ruff check --select E9,F63,F7,F82 src tests` : vert.
- Aucun appel LLM — coût nul.

### Écarts constatés avec le plan

- **Aucun frontend construit.** Ce sous-lot est strictement backend (WebSocket, navigateur, persistance) — aucun
  écran ne permet encore à une personne de réellement se connecter à une session, voir le flux vidéo dans un
  navigateur, ou cliquer dessus. Les tests le prouvent via `TestClient` (client WebSocket de test), pas via un vrai
  navigateur humain. C'est un écart de PÉRIMÈTRE assumé (le lot ne mentionne pas explicitement un écran dédié dans
  ses étapes 4-7), mais à signaler clairement : sans écran, ce sous-lot n'est pas utilisable par une personne réelle
  telle quelle.
- **Coordonnées de clic non mises à l'échelle.** `maxWidth`/`maxHeight` du relais vidéo sont fixées à la taille
  RÉELLE du viewport (pas de downscaling) : les coordonnées `(x, y)` qu'un client envoie doivent correspondre 1:1 aux
  pixels de la page. Un écran client plus petit que le viewport devra downscaler l'affichage ET retraduire ses clics
  avant de les envoyer — non implémenté ici, aucun frontend n'existe encore pour l'exercer.
- **Découverte non prévue par le plan initial** : le mode headless « nouveau » ne délivre aucune frame CDP — mesuré
  en écrivant les tests, pas anticipé dans le plan ÉTAPE 0. `--headless=old` + capture initiale explicite corrigent
  le problème, documentés dans le code.

### Risques / points à surveiller

- Un clic ambigu (`accname.ElementIntrouvableError`) pendant la capture est signalé (`clic_ambigu`) mais ne bloque ni
  n'interrompt la session — l'étape correspondante est simplement absente de la liste capturée. Une personne qui ne
  regarderait pas la liste avant de confirmer pourrait valider une séquence INCOMPLÈTE sans s'en rendre compte —
  risque atténué par l'étape 6 (revue explicite avant sauvegarde) mais dépend qu'un écran affiche clairement les
  trous, ce qui n'existe pas encore (voir Écarts).
- `--headless=old` est un mode Chromium plus ancien — son maintien à long terme par les futures versions de Chromium
  n'est pas garanti ; à surveiller si Playwright met à jour son Chromium embarqué.
- Guaranteed teardown vérifié via l'état de la file de concurrence (`held()` release) et la fin du thread dédié — pas
  via un comptage de processus OS bas niveau (aucune dépendance nouvelle type `psutil` ajoutée pour ça). Preuve
  jugée suffisante (ce sont exactement les deux ressources que ce module gère lui-même), mais signalé comme un choix
  de méthode, pas une vérification au niveau du système d'exploitation.

### Suggestions hors périmètre

- Construire l'écran qui affiche le flux vidéo, envoie les clics, montre la liste capturée et propose
  confirmer/annuler/recommencer — sans lui, ce sous-lot reste un backend prouvé mais inutilisable par une personne.
- Traduire les coordonnées de clic si un jour le relais vidéo est affiché à une échelle différente de la taille
  réelle du viewport.
