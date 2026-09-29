## Sous-lot E — Enregistrement assisté du chemin de connexion — étape 10 (preuve de bout en bout) — terminé

Décisions utilisées : aucune décision structurante nouvelle — ce sous-lot n'introduit ni colonne,
ni enum, ni comportement produit ; il ajoute uniquement le test de bout en bout que l'étape 10 de
la consigne exigeait avant de considérer le chantier terminé.

### Changements

- `tests/test_login_recording_e2e.py` (nouveau) — deux tests, marqueur `conformance`, vrai
  Chromium de bout en bout : aucune brique n'est simulée ou appelée directement avec des
  paramètres inventés à la main.
- `.github/workflows/generation-quality.yml` — `tests/test_login_recording_e2e.py` ajouté à la
  liste des tests `conformance` du job `browser-evidence`.

### Tests ajoutés

- `test_bout_en_bout_capture_confirmation_puis_exploration_automatique` — ouvre une VRAIE session
  en direct (route WebSocket du sous-lot C) contre une application locale à deux écrans (sélection
  de pays par VRAIE navigation serveur, puis formulaire de connexion), envoie un clic réel aux
  coordonnées du bouton « France », vérifie que le clic est capturé avec le bon rôle/nom
  accessible (sous-lot A), confirme (écriture réelle en base, sous-lot C). Relance ensuite une
  VRAIE exploration (`exploration_service.start_exploration` + `run_exploration`, sous-lot D) sur
  ce même projet et vérifie qu'elle atteint `/espace-client` **et** `/espace-client/profil` — deux
  pages qui n'existent QUE derrière l'écran de pré-connexion, atteintes sans qu'aucun humain ne
  reclique nulle part cette seconde fois.
- `test_falsifiable_sans_sequence_enregistree_l_exploration_reste_bloquee` — le test de contrôle
  exigé par l'étape 10 (« ce test doit échouer si un seul maillon est cassé ») : même projet, même
  application, mais sans jamais passer par la session en direct. Prouve que l'écran de test bloque
  RÉELLEMENT l'exploration en l'absence de la fonctionnalité — sans ce contrôle, le test positif ne
  prouverait rien (il pourrait « réussir » même si le rejeu ne faisait jamais rien d'utile).

**Falsifiabilité vérifiée moi-même**, protocole identique au reste du chantier : j'ai neutralisé
temporairement l'appel à `rejouer_sequence_connexion` dans `GenericWebConnector.crawl_relogin_hook`
(`src/testpilot/connectors/generic_web.py`), relancé le test positif seul → échec reproduit
exactement comme attendu (`routes atteintes : ['/']`, l'exploration ne dépasse jamais l'écran de
pays), puis restauré le code et reconfirmé le vert (`git diff` vide avant re-run).

### Démonstration visuelle (à la demande du porteur, hors périmètre du diff)

Script `demo_e2e.py` (non versionné, `/tmp/…/scratchpad/`) qui rejoue exactement le même scénario
et sauvegarde : la première frame vidéo reçue par un client WebSocket réel pendant la session en
direct (écran de sélection de pays), une capture d'écran après le clic réel sur « France »
(formulaire de connexion révélé par une vraie navigation), et le résultat texte de l'exploration
automatique (`/connexion`, `/espace-client`, `/espace-client/profil` — 3 routes, 1 transition).
Envoyé au porteur en session. Note : la première version du script sauvegardait deux frames vidéo
identiques (le CDP screencast n'avait pas encore repeint entre les deux lectures) — corrigé en
prenant les captures d'écran via un `Page.screenshot()` Playwright direct plutôt que via le flux
vidéo pour la démonstration ; n'affecte en rien le test automatisé lui-même, qui ne dépend
d'aucune capture d'écran.

### Critères d'acceptation (étape 10 de la consigne)

- [x] Un test complet, pas seulement morceau par morceau : ouvre une session réelle, simule des
  clics réels à travers le réseau jusqu'au navigateur distant, confirme la séquence, puis relance
  une exploration et vérifie qu'elle franchit bien l'obstacle sans intervention humaine cette fois.
- [x] Le test échoue si un seul maillon de la chaîne est cassé — prouvé par sabotage temporaire
  (voir ci-dessus) et par le test de contrôle dédié.

### Mesures

- `pytest -q -m conformance tests/test_login_recording_e2e.py` : 2 passed en ~9 s (vrai Chromium,
  après le premier lancement à froid).
- `pytest -q` (suite complète) : voir mesure jointe au commit du rapport (lancée en tâche de fond,
  résultat consigné avant la revue verdict-reviewer).
- `ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts` : vert.

### Écarts constatés avec le plan

Aucun. Le test exploite les fonctions de production telles qu'elles existent déjà (sous-lots A à
D) sans aucune modification de code applicatif — seul `generic_web.py` a été temporairement modifié
puis restauré, dans le seul but de vérifier la falsifiabilité du test lui-même.

### Risques / points à surveiller

- Ce test dépend d'un vrai Chromium et d'un vrai crawl BFS (`crawl_domaine.crawler`) — plus lent
  et légèrement plus fragile qu'un test unitaire, comme les autres tests `conformance` du
  chantier. Marqué `conformance`, exclu de `pytest -q` par défaut, exécuté uniquement par le job
  `browser-evidence`.
- Ce sous-lot ne couvre pas l'étape 11 (limites à écrire noir sur blanc dans le rapport FINAL du
  chantier) ni l'étape 12 (revue dédiée chantier-entier cherchant spécifiquement tout chemin vers
  un résultat trompeur) — les deux restent à faire avant de considérer le chantier complet terminé,
  au-delà de ce seul sous-lot.

### Suggestions hors périmètre

Aucune.
