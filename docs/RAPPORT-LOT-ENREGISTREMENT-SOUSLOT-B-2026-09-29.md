## Lot « Enregistrement assisté du chemin de connexion » — sous-lot B — jeton d'accès à une session live — terminé (en attente de fusion)

Décisions utilisées : aucune décision `D#` du registre du chantier `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — ce lot est
hors de ce chantier, donné directement par le porteur en session (même remarque que le rapport du sous-lot A).

**Décision de plancher de rôle, tranchée avec le porteur en session** (pas dans un registre, faute d'un chantier
existant pour ce lot — voir Écarts ci-dessous) : la consigne du lot (ÉTAPE 2, citée telle quelle dans la transcription
de session) dit « Nouvel endpoint protégé par le même niveau d'accès que le démarrage d'une exploration (rôle
admin/dev) ». En vérifiant le code réel, `start_exploration` n'exige aujourd'hui que `admin` seul — écart signalé au
porteur avant de coder, via deux options présentées explicitement :
  - **Admin seul** — cohérent avec le code réel de `start_exploration` aujourd'hui.
  - **Admin + dev** — suit le texte littéral de la consigne, mais un compte `dev` pourrait alors déclencher l'ouverture
    d'un navigateur réel piloté à distance sur l'infrastructure du projet, un droit qu'il n'a pour aucune autre
    opération de ce type aujourd'hui (exploration, accès projet).

Le porteur a choisi **Admin + dev**, en connaissance de cet écart et du risque nommé. `require_project_role` est donc
`ROLE_DEV` (admin reste inclus, plus haut dans la hiérarchie des rôles), pas `ROLE_ADMIN`.

### Ce que le sous-lot change, en clair

Ce sous-lot pose uniquement les **fondations d'accès** d'une future session en direct — rien n'ouvre encore de
navigateur ni de connexion WebSocket (sous-lot C, pas commencé) :

- Un jeton d'accès à usage unique, courte durée de vie (5 minutes), sur le modèle d'un lien de réinitialisation de mot
  de passe : jamais stocké en clair (seul son hash SHA-256 l'est), consommé en une seule écriture SQL conditionnelle
  pour fermer la fenêtre de course entre deux tentatives simultanées.
- Une route API qui l'émet, réservée à `admin`/`dev`.
- Une extension du plafond de concurrence existant (`guardrails/concurrency.py`) : `JobQueue.held()`, une variante
  bloc `with` de `run()` qui garde la place tenue pour la durée d'une session live entière plutôt qu'un seul appel
  bloquant — pas encore câblée sur la route (à faire au sous-lot C, quand le navigateur s'ouvrira réellement).

### Changements

- `src/testpilot/store/db.py` — migration 54 `_migrate_54_live_session_token` (idempotente) : table `live_session_token`
  (`project_id`, `created_by_user_id` en FK NOT NULL vers `project`/`user`, `token_hash` unique, `created_at`,
  `expires_at`, `used_at`).
- `alembic/versions/d8a3f5c1e947_live_session_token.py` — révision chaînée sur `b3f7d4a291ec`.
- `src/testpilot/store/schema_sa.py` — table miroir, `ALIGNED_WITH_SCHEMA_VERSION = 54`.
- `src/testpilot/store/portable_connection.py` — `ALEMBIC_HEAD` mis à jour.
- `src/testpilot/store/live_session_tokens.py` (nouveau) — `creer`/`consommer` : jeton `secrets.token_urlsafe(32)`,
  hash SHA-256, consommation atomique `UPDATE ... WHERE token_hash=? AND used_at='' AND expires_at>?`. Pas de
  comparaison Python en temps constant (`hmac.compare_digest`) : la correspondance passe par un `WHERE` SQL sur une
  colonne indexée, jamais une comparaison octet à octet d'un secret devinable.
- `src/testpilot/guardrails/concurrency.py` — `JobQueue.held(label)`, context manager `with` réutilisant les
  primitives privées `_acquire`/`_release` déjà éprouvées par `run()`.
- `src/testpilot/api/routes/projects.py` — `POST /{project_id}/live-session`, `require_project_role(ROLE_DEV)`, émet
  le jeton et le rend en clair une seule fois dans la réponse.
- `src/testpilot/api/schemas.py` — `LiveSessionOut` (`token`, `expires_at`).

### Tests ajoutés

- `tests/test_migration_live_session_token.py` (6) — table neuve, idempotence, FK projet/utilisateur (`ON DELETE
  CASCADE` vérifié), unicité du hash.
- `tests/test_session_live.py` (11) :
  - dépôt : jeton jamais stocké en clair, consommation rend projet/auteur.
  - **3 falsifiabilités séparées**, chacune vérifiée rouge avant garde / verte après : jeton déjà consommé refusé une
    deuxième fois, jeton expiré refusé, jeton inventé (jamais émis) refusé.
  - API : admin obtient un jeton (201), **dev aussi** (201, conforme à la décision ci-dessus), testeur et lecture_seule
    refusés (403, falsifiable), projet inconnu (404), le jeton émis par la route est bien celui que `consommer()`
    accepte (bout en bout minimal dépôt ↔ API).
- `tests/test_concurrency.py` (+3) — `held()` : place tenue tout le bloc `with`, refus d'une deuxième place tant que la
  première n'est pas rendue (preuve sous VRAIE concurrence, thread réel), place rendue même sur exception.
- `tests/test_schema_sa_portable.py` — vert après mise à jour du marqueur d'alignement (test déjà existant, pas
  ajouté).

### Critères d'acceptation

- [x] Nouvel endpoint protégé par le même niveau d'accès que l'exploration selon le texte de la consigne (admin/dev) —
      décision documentée ci-dessus, volontairement plus permissive que le code réel de `start_exploration`.
- [x] Le navigateur ne s'ouvre qu'à la demande — sans objet à ce stade, aucun navigateur n'est encore ouvert par ce
      sous-lot (sous-lot C).
- [x] Passe par la même file d'attente que génération/exécution/exploration — fondation posée (`held()`), pas encore
      câblée sur cette route faute de navigateur à tenir pour l'instant ; câblage prévu au sous-lot C.
- [x] Test obligatoire : une personne sans les droits requis ne peut pas ouvrir cette session — prouvé (testeur,
      lecture_seule refusés, falsifiable).
- [x] Jeton à usage unique, courte durée de vie, invalidé immédiatement après usage.
- [x] Les trois tests de falsifiabilité (déjà utilisé, expiré, inventé) échouent avant correctif, réussissent après.

### Mesures

- `pytest -q tests/test_session_live.py tests/test_migration_live_session_token.py tests/test_concurrency.py
  tests/test_schema_sa_portable.py` : 48 passed.
- `pytest -q` (suite complète) : 2882 passed, 16 skipped, 87 deselected — aucune régression.
- `ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts` : vert.
- CI GitHub (4 checks requis) : en cours de re-vérification sur le dernier commit (`4ebcc15`) au moment de ce rapport.
- Aucun appel LLM dans ce sous-lot — coût nul, hors périmètre du §9 du brief.

### Écarts constatés avec le plan

- **Plancher de rôle admin/dev plutôt qu'admin seul** — voir « Décisions utilisées » ci-dessus : le texte littéral de
  la consigne l'emporte sur ce que `start_exploration` applique aujourd'hui dans le code, décision explicite du
  porteur après que le risque a été nommé.
- **Aucun registre de décisions pour ce lot** : contrairement au chantier `docs/PLAN-FIABILITE-VERDICT-2026-09.md`, ce
  lot « Enregistrement assisté du chemin de connexion » n'a pas d'entrée correspondante sous `docs/`. La décision
  ci-dessus n'est donc traçable que dans ce rapport et dans l'historique de la session — signalé au porteur par le
  sous-agent verdict-reviewer lors de sa revue, retenu comme la meilleure trace disponible tant qu'aucun registre
  formel n'existe pour ce chantier.
- Un docstring de la migration 54, écrit avant que le module `live_session_tokens.py` ne soit réellement construit,
  promettait encore une classe `LiveSessionTokenRepo` et une comparaison `hmac.compare_digest` — ni l'une ni l'autre
  n'existent dans le code livré. Corrigé (commit `c3cbf8a`) pour que le commentaire décrive le code tel qu'il est,
  trouvé par le sous-agent verdict-reviewer.

### Risques / points à surveiller

- `held()` n'est câblée nulle part encore — fondation posée, sans effet tant que le sous-lot C ne l'utilise pas pour
  tenir la place du navigateur pendant la session live.
- Le plancher `admin`/`dev` élargit qui peut déclencher, à terme, l'ouverture d'un navigateur réel piloté à distance
  sur l'application du projet (potentiellement en production du client) — un compte `dev` compromis ou mal intentionné
  aura ce chemin d'accès dès que le sous-lot C sera câblé. Risque nommé et accepté par le porteur, pas un oubli.
- Le jeton (durée de vie 5 minutes) est le temps disponible pour OUVRIR la connexion WebSocket, pas la durée de la
  session elle-même — le sous-lot C devra poser ses propres limites de durée de session (deux niveaux de timeout déjà
  spécifiés par le porteur : inactivité 5 minutes avec avertissement, plafond absolu 20 minutes).

### Suggestions hors périmètre

- Ajouter une entrée de registre de décisions dédiée à ce chantier (rôle plancher, durée de vie du jeton, périmètre
  production/non-production) avant le sous-lot C, pour que la capacité « navigateur réel piloté en direct » ne se
  construise pas incrément par incrément sans jamais passer par un point d'arrêt tracé dans le dépôt — suggestion du
  sous-agent verdict-reviewer, transmise telle quelle.
