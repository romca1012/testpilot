# Lot 07e — Oracle backend HTTP optionnel (C5, D7) — terminé

Branche `lot-07e-oracle-http` (worktree neuf depuis `origin/master`, commit `89c5615`), **poussée
SANS PR** conformément à la consigne du porteur pour cette session (aucune PR, aucune fusion,
aucun push sur `master`/`dev`/`staging` tant qu'il n'a pas validé lui-même à son retour).

Décisions utilisées : D7 (validée le 2026-09-25 — périmètre HTTP seulement ; l'oracle SQL en
lecture seule reste un sous-lot séparé, non traité ici).

## Changements

- `src/testpilot/store/db.py` — migration SQLite `_migrate_53_oracle` (idempotente) : quatre
  colonnes sur `project` (`oracle_type`, `oracle_base_url`, `oracle_auth`, `oracle_queries`), vide
  par défaut, `_SCHEMA_VERSION` → 53.
- `alembic/versions/d6e29a4f8c31_oracle_backend.py` — révision Alembic chaînée sur `c92f4a80e6b3`
  (tête précédente), mêmes quatre colonnes + `CHECK`.
- `src/testpilot/store/schema_sa.py` — colonnes + `ck_project_oracle_type` alignés,
  `ALIGNED_WITH_SCHEMA_VERSION` → 53.
- `src/testpilot/store/portable_connection.py` — `ALEMBIC_HEAD` → `d6e29a4f8c31`.
- `src/testpilot/connectors/oracle_config.py` (nouveau) — module PUR : validation de forme
  (`erreurs`), noms de requêtes déclarées (`noms_declares`) — la seule chose que la génération lit.
- `src/testpilot/connectors/oracle_http.py` (nouveau) — client HTTP (`urllib`, comme
  `_web_helpers.http_probe`) : `verifier_joignable` distingue « injoignable » (réseau) de « répond
  en erreur » (HTTP 4xx/5xx, qui prouve que le serveur existe) ; `executer` ne résout QUE des
  requêtes nommées déclarées ; `compte_resultats`/`champ` pour les steps.
- `src/testpilot/store/repositories.py` — `ProjectRepo.create`/`update_connection`/`_en_clair`
  portent les quatre champs (`oracle_auth` chiffré, même règle que `totp_secret`) ;
  `_avec_libelles_de_comptes` ajoute `oracle_requetes_disponibles` (noms seulement).
- `src/testpilot/connectors/runtime_env.py` — `project_env` transmet la config décodée au
  sous-processus (`TESTPILOT_ORACLE`), **quel que soit le connecteur** (un projet Odoo peut aussi
  vouloir un oracle tiers) ; `verifier_connexion` refuse (`ConnexionIncomplete`) si l'oracle
  configuré est injoignable, avant tout run.
- `behave_runtime/environment.py` — lit `TESTPILOT_ORACLE`, pose `context.oracle`/
  `context.oracle_erreur` dans `before_all` via `construire_oracle`.
- `behave_runtime/steps_library/_base_helpers.py` — `construire_oracle`, `_resoudre_oracle`,
  `_executer_oracle` (convertit une panne réseau EN COURS de run en `PreconditionNonRemplieError` →
  `blocked` ; laisse une réponse HTTP d'erreur remonter telle quelle, signal potentiellement
  significatif de l'oracle lui-même), `oracle_renvoie_n_resultats`, `oracle_champ_vaut`.
  **`constater(condition, message)` a perdu tout paramètre `source`** : la source d'un constat
  (`""` ordinaire / `"oracle"` recoupé) est portée par une variable de contexte
  (`_SOURCE_CONSTAT`/`_source_du_constat`), posée UNIQUEMENT par les deux helpers d'oracle autour de
  leur propre appel — voir « Écarts » ci-dessous, ce choix vient de la revue, pas du plan initial.
- `behave_runtime/steps_library/generic/_generic_steps.py` — deux `@then` :
  `l'oracle "<nom>" renvoie <n> résultat(s)`, `le champ "<chemin>" de l'oracle "<nom>" vaut
  "<valeur>"`.
- `src/testpilot/execution/behave_result.py` — `BehaveScenario.oracle_verifie` (bool), calculé par
  `rattacher_constats` depuis le sidecar (`source == "oracle"`, `step_type == "then"`, réussi OU
  échoué — un écart TROUVÉ par l'oracle est aussi une preuve qu'il a tourné).
- `src/testpilot/verdict/status.py` — `_ground_truth_pour(connector_type, oracle_utilise)` :
  `backend_verified` pour `web` seulement si **TOUS** les scénarios du cas ont interrogé l'oracle
  (unanimité, pas un seul scénario qui « prêterait » la garantie aux autres — voir « Écarts »).
- `src/testpilot/generation/tools/write.py` — `write_steps_file` refuse désormais TOUTE la racine
  `testpilot` dans un import de step généré (pas seulement ses sous-modules d'oracle : ferme aussi
  bien l'import nommé direct qu'un import du paquet parent suivi d'un accès par attribut) ; refuse
  un `source=` littéral sur `constater(...)` (message précoce, la garantie réelle tient à la
  signature de `constater`).
- `src/testpilot/generation/prompt.py` / `agent.py` — `_section_oracle` expose les NOMS de requêtes
  déclarées (jamais l'adresse ni l'authentification), même garantie structurelle que D8.
- `src/testpilot/api/schemas.py` / `routes/projects.py` — réglages d'oracle sur `ProjectIn`/
  `ProjectPatch`/`ProjectSummary` (`oracle_auth` write-only, `has_oracle_auth` en sortie),
  validation 422 (`oracle_config.erreurs`) à la création ET à l'édition — y compris un PATCH qui ne
  touche QUE l'authentification (bug trouvé et corrigé en cours de lot, cf. tests).
- `tests/test_bibliotheque_falsifiable.py`, `tests/test_constater_helpers.py`,
  `tests/test_steps_reuse.py` — ajustés au nouveau champ `source` du sidecar, au nouveau head
  Alembic, et enrichis de tests de falsifiabilité pour la nouvelle garde et la nouvelle signature
  de `constater`.
- `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — suivi du lot 07b-e mis à jour (07b-1/07b-2/07e
  terminés ; plus rien à faire sous 07b-e).

## Tests ajoutés

87 tests dans 8 fichiers dédiés, plus falsifiabilité ajoutée à 3 fichiers existants. Points
notables :

- `tests/test_oracle_config.py`, `tests/test_oracle_http.py` — module pur et client HTTP (serveur
  `http.server` LOCAL, aucun réseau externe ni mock du transport).
- `tests/test_migration_oracle.py` — idempotence, valeurs d'enum, reprise d'une base pré-53.
- `tests/test_ground_truth_oracle.py::test_falsifiable_un_seul_scenario_sur_plusieurs_ne_suffit_pas`
  — preuve que l'unanimité est bien exigée (un seul scénario oracle-vérifié sur deux → `ui_only`).
- `tests/test_oracle_steps.py::test_falsifiable_une_panne_reseau_en_cours_de_run_est_un_prerequis_manquant_pas_une_erreur_technique`
  — vraie panne réseau (port fermé), vrai serveur HTTP local pour le cas HTTP 4xx.
- `tests/test_constater_helpers.py::test_falsifiable_un_troisieme_argument_positionnel_leve_typeerror`
  (+ 3 autres) — preuve que `source` ne peut plus être forgé sous AUCUNE forme d'appel.
- `tests/test_steps_reuse.py::test_falsifiable_write_steps_file_refuse_l_import_du_paquet_puis_l_acces_par_attribut`
  — reproduit l'exploit trouvé en revue (import du paquet parent + accès par attribut).
- `tests/test_oracle_generation_structure.py` — garantie structurelle D7 (grep du code source de
  `generation/`, comme le test D8 existant) + contenu exact du message de prompt.
- `tests/test_oracle_projet_api.py::test_falsifiable_patch_qui_ne_touche_que_l_authentification_est_valide`
  — bug de validation PATCH trouvé et corrigé en cours de lot (démontré par retrait temporaire du
  correctif : le test échoue sans lui).

Suite complète : **2825 tests verts**, 16 ignorés (inchangé), `ruff check --select
E9,F63,F7,F82` vert.

## Critères d'acceptation

- [x] Réglage `oracle` (`type: "http"`, `base_url`, `auth`), secrets via `store/secrets.py`.
- [x] `verifier_connexion` refuse si l'oracle configuré est injoignable.
- [x] Steps `l'oracle "<nom>" renvoie <n> résultat(s)` / `le champ "<chemin>" de l'oracle "<nom>"
  vaut "<valeur>"`.
- [x] Requêtes nommées déclarées dans les réglages du projet, jamais écrites par l'agent — garde
  structurelle vérifiée par **quatre passages** du sous-agent `verdict-reviewer` (voir « Risques »).
- [ ] Oracle SQL en lecture seule — **hors périmètre explicite de D7** (« sous-lot séparé, plus
  tard »), non traité.
- [~] `ground_truth = backend_verified` si un constat d'oracle a tourné — implémenté avec une
  précision qui n'était pas dans le texte du lot : **unanimité sur tous les scénarios du cas**, pas
  « le scénario » au singulier. Voir « Écarts ».
- [ ] « L'exploration et l'exécution utilisent le même code de connexion et le même contexte » —
  critère du lot 07b-e dans son ensemble (connexion applicative), sans objet pour un oracle qui
  n'est jamais utilisé pendant l'exploration.
- [x] Chaque nouveau step affirmatif a un test de falsifiabilité.

## Mesures

Aucune mesure de coût (§8/§9 du brief) : cet environnement n'a pas d'accès à un budget LLM réel
(pas d'appel `scripts/mesure_cout_cas.py` possible ici). Impact attendu **négligeable** — le prompt
ne grossit que si un oracle est configuré sur le projet, de quelques lignes listant des noms courts
— mais non mesuré, à faire lors d'une prochaine campagne par le porteur.

Pas de banc Odoo disponible dans ce cloud (Docker absent) — sans objet ici, l'oracle HTTP ne touche
pas Odoo.

## Écarts constatés avec le plan

1. **`ground_truth` : unanimité, pas « le scénario »** (D7 dit « si le scénario a exécuté un
   constat d'oracle », au singulier). `CaseVerdict.ground_truth` est un champ de CAS, pas de
   scénario — un premier jet (`any()`, un seul scénario suffit) a été trouvé, en revue, comme
   pouvant prêter `backend_verified` à des scénarios du même cas jamais recoupés côté serveur.
   Corrigé en `all()` (TOUS les scénarios doivent avoir un constat d'oracle), symétrique à
   `functional_status = conforme` qui exige déjà l'unanimité. **Décision structurante non
   pré-validée** (D7 ne tranchait pas ce niveau de détail) : proposition retenue et testée,
   **à confirmer par le porteur** avant fusion — l'alternative (afficher `ground_truth` par
   scénario) changerait le schéma de persistance et l'écran, hors périmètre de ce lot.
2. **`constater()` a perdu son paramètre `source`** — n'était pas prévu par le plan, mais imposé
   par la revue (3 passes ont trouvé 3 formes de contournement successives : import nommé direct,
   import du paquet + attribut, puis forgeage de `source=` par argument positionnel/déballage/alias
   sur `constater`). La solution finale déplace la garantie de « garde par AST » (jamais exhaustive
   face à un texte généré) à « restriction de signature » (un `TypeError` à l'exécution, quelle que
   soit la forme d'appel). Documenté dans le code et testé.
3. **Aucune interface (frontend)** pour éditer les réglages d'oracle — seulement l'API. Cohérent
   avec un lot backend, mais à signaler : le porteur devra passer par l'API directement (ou un
   futur écran) pour configurer un oracle sur un projet réel.
4. **Bug de validation trouvé en cours de lot** (pas dans le plan, découvert en écrivant les
   tests) : un PATCH qui ne touche QUE `oracle_auth` sans retoucher type/adresse/requêtes
   échappait à la validation 422 — corrigé, testé en falsifiabilité (le test échoue sans le
   correctif, vérifié explicitement).

## Risques / points à surveiller

- **Trois passes de revue ont été nécessaires** avant qu'un point bloquant soit définitivement
  fermé (l'agent ne doit jamais pouvoir forger `ground_truth = backend_verified`) — chaque
  correctif intermédiaire semblait suffisant et ne l'était pas. La 4ᵉ passe conclut « bon pour
  validation » avec un point théorique résiduel, explicitement accepté comme hors périmètre par le
  reviewer : un step généré qui importerait le nom privé `_source_du_constat` depuis
  `_base_helpers` (jamais enseigné par le prompt système, jamais suggéré) pourrait encore forger
  une source. Aucun chemin plus simple qu'« deviner un nom interne non documenté » ne l'exploite.
  **Suggestion hors périmètre** : refuser, dans `write.py`, tout import depuis `_base_helpers` d'un
  nom commençant par `_` — durcissement simple, non fait ici pour ne pas élargir le lot sans
  arbitrage.
- Une réponse HTTP d'erreur de l'oracle EN COURS de run (après que `verifier_connexion` l'a jugé
  joignable au démarrage) atterrit dans la taxonomie générique existante (`WRONG_NAVIGATION` →
  `TEST_A_REPARER`, `defect_taxonomy.py`, non touchée par ce lot) — jamais un faux `conforme`, mais
  pourrait déclencher un cycle de réparation inapproprié (coût §9). Signalé par la revue, non
  corrigé ici (hors périmètre).
- Le hotfix 07b-2 (branche `hotfix-07b2-connexion-initiale`) reste, comme avant cette session, en
  attente de validation et de PR par le porteur — non touché par ce lot.

## Suggestions hors périmètre

- Durcir `write.py` contre l'import de tout nom privé (`_...`) depuis `_base_helpers` (cf.
  « Risques » ci-dessus).
- Mesurer le coût du prompt avec oracle configuré (`scripts/mesure_cout_cas.py`) dès qu'un budget
  LLM réel est disponible.
- Une interface d'édition des réglages d'oracle (écran Projets), sur le modèle de l'écran des
  comptes secondaires (D8).
- L'oracle SQL en lecture seule (sous-lot séparé, D7 le prévoit déjà).

## Sous-agent verdict-reviewer

Quatre passages avant de déclarer ce lot terminé (consigne explicite du porteur, contrairement au
lot 07b-2) :
1. 1ʳᵉ passe : **BLOQUANT** (import direct du client oracle contournable) + point à corriger
   (`ground_truth` en `any()`) — les deux traités.
2. 2ᵉ passe : **BLOQUANT** persistant sous une forme différente (import du paquet parent + accès
   par attribut) — traité par un bannissement de toute la racine `testpilot`.
3. 3ᵉ passe : **BLOQUANT** persistant sur `source=` (3 formes de contournement de la garde AST) —
   traité par le retrait du paramètre `source` de `constater` (garantie par signature, pas par
   AST).
4. 4ᵉ passe : **bon pour validation**, un point résiduel théorique noté en « Risques » et
   « Suggestions hors périmètre », non bloquant.

## Prochaine étape

Aucune PR, aucune fusion — branche `lot-07e-oracle-http` poussée seule sur origin, en attente de
validation du porteur à son retour, conformément à la consigne de cette session. Une fois validé,
plus rien ne reste à faire sous le lot 07b-e (07a, 07b-1, 07b-2, 07c, 07d, 07e tous terminés).
Ordre confirmé restant : 06 (nettoyage/profils), 08 (Odoo ERP), 09 (agents — dépend
structurellement de 06), 10 (campagne finale).
