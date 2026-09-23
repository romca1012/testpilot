# Rapport de fin de lot — format CLAUDE.md §10

## Lot 01 — Comptages cloisonnés au scénario (F1) — terminé

**Décisions utilisées** : D10 (validée le 2026-09-23) — résidu de faux PASSED accepté sur un
scénario de création SANS marqueur de tentative (`docs/PLAN-FIABILITE-VERDICT-2026-09.md` §4).

**Changements**

- `behave_runtime/steps_library/_base_helpers.py` — `memorize_record_count` relève désormais
  aussi l'id maximal du modèle (`_max_id_attr`, `active_test=False`) ; nouveaux `_require_max_id`
  (`RuntimeError` [code de test]) et `_crees_par_ce_scenario` (domaine `id > max_id`, affiné par
  le marqueur de tentative quand il existe) ; `check_count_increased_by_one` et
  `check_count_not_increased` réécrits pour prouver via `_crees_par_ce_scenario` au lieu de
  `search_count([])` (qui reste affiché en diagnostic seul) ; `_capturer_dernier_enregistrement`
  reçoit désormais les ids déjà prouvés au lieu de re-requêter le plus récent ; suppression de
  `record_count_not_increased` (0 appelant dans tout le dépôt, confirmé par grep).
- `behave_runtime/steps_library/generic/_generic_steps.py` — `step_fill_unique` pose
  `context._tp_derniere_valeur_unique = (champ, jeton)` pour que `_crees_par_ce_scenario` puisse
  affiner.
- `tests/test_comptage_falsifiable.py` — doublures (`_FakeModel`/`_FakeEnv`/`_FakeOdoo`/`_Context`)
  migrées vers `with_context()` + `search(domain, order, limit)` qui filtre réellement
  `id > x` / `champ like jeton` (au lieu d'un simple `search_count`) ; deux assertions mises à
  jour au nouveau format de message (« 2 créations détectées » / « créé … malgré l'attente
  d'aucune création » plutôt que « devrait être N, obtenu M »).
- `tests/test_comptage_cloisonne.py` (nouveau) — 9 tests prouvant le cloisonnement.
- `tests/test_reponse_serveur_3a.py`, `tests/test_comptage_attente_active.py`,
  `tests/test_refus_champ_teste.py`, `tests/test_diagnostic_soumission.py` — doublures migrées
  vers la même interface cloisonnée (`with_context`/`search` par domaine), sans quoi
  `_require_max_id` levait un `RuntimeError` non attendu (ces fichiers posaient
  `_initial_count_*` à la main sans jamais appeler `memorize_record_count`) ; quelques assertions
  au format de message périmé mises à jour ; un test adapté dans son mécanisme de panne simulée
  (voir Écarts, point 5).
- `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — décision D10 ajoutée et validée ; F1, I1, la ligne du
  lot 01 et son suivi mis à jour.
- `.claude/commands/lot-01-comptages.md` — ligne « décision requise » mise à jour pour refléter
  D10, apparue en cours de lot.

**Tests ajoutés** (`tests/test_comptage_cloisonne.py`)

- `test_GARDE_tiers_cree_pendant_que_le_scenario_echoue_ne_passe_pas_a_tort` — LE test du défaut :
  prouve que F1 est fermé quand un marqueur existe (rejoué sur l'ancien code, il passait à tort).
- `test_scenario_cree_1_tiers_cree_1_avec_marqueur_isole_le_bon_id` — le marqueur isole le bon id
  parmi deux candidats.
- `test_scenario_cree_1_tiers_cree_1_sans_marqueur_echoue_avec_2_creations` — sans marqueur, deux
  créations restent une ambiguïté signalée, jamais un succès par défaut.
- `test_not_increased_tiers_cree_1_sans_marqueur_echoue_avec_ids_liste` — le négatif liste les ids.
- `test_not_increased_avec_marqueur_et_tiers_NON_marque_passe` — le marqueur disculpe le scénario.
- `test_un_enregistrement_archive_par_laction_testee_est_compte` — `active_test=False` tient.
- `test_memorize_et_crees_appellent_bien_with_context_active_test_false` — garde du motif.
- `test_controle_sans_aucun_relevé_leve_AssertionError_historique` — `_require_snapshot` intact.
- `test_max_id_absent_alors_que_le_compte_est_present_leve_RuntimeError` — point 5 du lot.

**Critères d'acceptation**

- [x] Plus aucun `search_count([])` servant de preuve de création/non-création dans les helpers —
      vérifié : `search_count` n'apparaît plus que pour le diagnostic affiché (`global_actuel`),
      jamais dans une condition qui décide du verdict.
- [x] Le test « tiers crée pendant que le scénario échoue » passe à tort sur l'ancien code et
      échoue correctement sur le nouveau — preuve ci-dessous (avant/après).
- [x] `python -m pytest -q` et ruff critique verts — voir Mesures.

**Mesures**

Avant/après sur le scénario exact du défaut F1 (ancien code rejoué via `git show
b0223eb:behave_runtime/steps_library/_base_helpers.py`, exécuté dans un espace de noms isolé
contre la même doublure) :

```
=== ANCIEN CODE (avant le lot 01, commit b0223eb) ===
RESULTAT : aucune exception levée — le scénario est déclaré CONFORME À TORT (faux PASSED, F1)
alors qu'il n'a lui-même RIEN créé.

=== NOUVEAU CODE (après le lot 01) ===
RESULTAT : AssertionError levée (correct) -> Aucune création détectée dans 'helpdesk.ticket'
depuis id > 10 (domaine [('id', '>', 10)]) ; 0 trouvée(s) au lieu d'une. Comptage global
(diagnostic, inclut l'activité concurrente) : 11.
```

Suite de tests :

```
python -m pytest -q tests/test_comptage_falsifiable.py tests/test_comptage_cloisonne.py \
    tests/test_valeur_unique_par_tentative.py tests/test_behave_harness.py
→ 31 passed

python -m pytest -q tests/test_reponse_serveur_3a.py tests/test_comptage_attente_active.py \
    tests/test_refus_champ_teste.py tests/test_diagnostic_soumission.py
→ 44 passed

python -m pytest -q
→ 2101 passed, 13 skipped, 17 deselected (0:34:05)

python -m ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts
→ All checks passed!
```

**Écarts constatés avec le plan**

1. `record_count_not_increased` supprimé plutôt que corrigé : 0 appelant dans tout le dépôt
   (confirmé par grep sur `src/`, `behave_runtime/`, `tests/`) — code mort, pas une fonction à
   migrer.
2. Réconciliation `RuntimeError`/`AssertionError` : `_require_snapshot` (historique,
   `AssertionError`, appelé en premier) conservé séparé de `_require_max_id` (nouveau,
   `RuntimeError`) plutôt que fusionné, pour ne pas casser le contrat déjà éprouvé par
   `tests/test_comptage_falsifiable.py`.
3. Affinage « le marqueur fait foi » : quand un marqueur existe, il tranche même s'il réduit à
   zéro candidat (pas seulement pour départager plusieurs candidats) — un peu au-delà de la
   lecture littérale « si et seulement si len>1 » de la consigne, mais nécessaire pour fermer le
   vrai défaut F1 (voir `test_GARDE_…`).
4. Quatre fichiers de test voisins non listés par la consigne du lot (`test_reponse_serveur_3a.py`,
   `test_comptage_attente_active.py`, `test_refus_champ_teste.py`, `test_diagnostic_soumission.py`)
   ont dû être migrés vers la même interface de doublure — trouvé par le sous-agent
   `verdict-reviewer` (leurs `context` posaient `_initial_count_*` à la main sans jamais appeler
   `memorize_record_count`, donc `_max_id_attr` n'existait jamais), corrigé, revérifié par un
   second passage du même sous-agent.
5. `tests/test_refus_champ_teste.py::test_une_capture_IMPOSSIBLE_ne_fait_PAS_echouer_le_comptage`
   (renommé `test_registre_de_nettoyage_impossible_ne_fait_PAS_echouer_le_comptage`) a dû changer
   de MÉCANISME de panne simulée : avant, la RPC pouvant échouer était la relecture de l'id dans
   l'ancienne `_capturer_dernier_enregistrement` ; cette relecture n'existe plus (les ids arrivent
   déjà prouvés), donc seul `register_created` (l'enregistrement pour nettoyage) peut encore
   échouer — comportement strictement plus robuste (`last_record_ids` reste posé même si le
   nettoyage échoue). Vérifié explicitement par le sous-agent de revue comme une adaptation
   honnête du changement de point de défaillance réel, pas un masquage de régression.
6. Décision D10 : le plan indiquait « Décision requise : aucune » pour ce lot ; une décision
   structurante (résidu de faux PASSED sans marqueur) est apparue pendant l'exécution, trouvée par
   le sous-agent de revue, et a dû être soumise et validée par le porteur en cours de lot plutôt
   que d'être anticipée dans le registre initial.

**Risques / points à surveiller**

- Résidu D10 : sur un scénario de création sans marqueur, la coïncidence (tiers actif sur le même
  modèle + même fenêtre de quelques secondes + échec réel du scénario) reste un faux PASSED
  possible. Rare, mais pas nul — à surveiller via l'indicateur I1 une fois le banc de mesure du
  lot 04 disponible.
- `check_count_not_increased` reste exposé, de façon asymétrique et moins grave (faux
  `non_conforme`, jamais faux PASSED), à une création tierce non marquée pendant qu'un scénario
  négatif réussit réellement à ne rien créer. Hors périmètre de la décision D10 (qui portait sur
  le faux PASSED) ; signalé ici pour transparence, pas corrigé dans ce lot.
- `tests/test_comptage_falsifiable.py` + `tests/test_comptage_cloisonne.py` prennent ~35 s réelles
  (plusieurs tests tombent sur le chemin où `_poll_until` n'est jamais satisfait et attendent le
  `COUNT_SETTLE_TIMEOUT` réel du module, faute d'y injecter `_clock`/`_sleep` comme le fait déjà
  `test_comptage_attente_active.py`). Non bloquant, mais à corriger si la suite ciblée ralentit
  davantage.

**Suggestions hors périmètre**

- Généraliser le marqueur de tentative à TOUT scénario de création (pas seulement les champs à
  contrainte d'unicité) pour fermer le résidu D10 à zéro — changerait le contrat de génération
  (`technical_plan.py`/prompts). À traiter comme un lot séparé si le résidu se matérialise en
  pratique (mesuré par I1, lot 04+).
- Injecter `_clock`/`_sleep` dans les tests de `test_comptage_cloisonne.py` qui attendent la
  fenêtre réelle, sur le modèle de `test_comptage_attente_active.py`, pour accélérer la suite
  ciblée.
