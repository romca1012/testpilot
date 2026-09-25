## Filtre de chemins du banc (`banc.yml`) — terminé (en attente de fusion)

PR séparée de celle du lot 07c, à la demande du porteur (ne pas mélanger les deux sujets dans un même diff).

### Ce qui s'est passé

Le lot 07c (contexte navigateur figé) modifie `behave_runtime/environment.py`, `src/testpilot/connectors/odoo.py` et `src/testpilot/connectors/runtime_env.py`. La mesure du
banc lance un vrai Behave contre Odoo : ces trois fichiers changent ce qu'elle mesure (`environment.py` crée les contextes de navigateur de chaque scénario). Le workflow `banc.yml`
ne s'est pourtant **pas déclenché** sur la PR : son filtre `pull_request.paths` listait des **fichiers** (`_adaptive_resolution.py`, `_base_helpers.py`, `status.py`…) et non les
**répertoires** que le banc exerce. Rattrapé **à la main** (déclenchement manuel, `workflow_dispatch`, avant la fusion) : banc vert sur 16.0, 17.0 et 18.0.

### Changements

- `.github/workflows/banc.yml` — le filtre surveille désormais `behave_runtime/**` (sauf `behave_runtime/generated/**`, artefacts d'exécution), `src/testpilot/connectors/**`,
  `src/testpilot/execution/**` et `src/testpilot/verdict/**`, en plus des fichiers propres au banc. Les trois entrées par fichier qu'ils recouvrent sont retirées (redondantes).
- `tests/test_banc_filtre_chemins.py` — échoue si un de ces répertoires quitte le filtre ; vérifie que les trois fichiers manqués par le lot 07c sont couverts (falsifiabilité) et que
  le coût de CI reste borné.

### Coût de CI vérifié

Les quatre répertoires contiennent 32 fichiers suivis, **tous du Python** sauf un `.gitkeep` (`behave_runtime/generated/`, exclu). Aucun fichier de documentation ni de frontend ne
déclenchera le banc pour rien ; le test le garde (pas de `.md`, `.vue`, `.ts`, `.css`, `.html` sous un répertoire surveillé). Une modification de `connectors/generic_web.py` (web seul) déclenche
le banc Odoo — surcoût accepté : ce répertoire contient des fichiers partagés avec Odoo, et affiner par fichier réintroduirait la liste qui a échoué.

### Fait à consigner : le trou existait depuis le lot 04

Ce filtre par fichiers date de la création de `banc.yml` au **lot 04**. Tous les lots fusionnés depuis — **05** (confiance du verdict) et **F17/F21** (navigation par menu), ainsi que 07a — auraient pu passer sous silence le même
risque si leurs fichiers modifiés avaient touché ces répertoires sans que le filtre le voie, et sans que personne s'en rende compte : ici, c'est une relecture de la PR qui l'a révélé,
pas un mécanisme. Les lots 05 et F17/F21 modifiaient eux-mêmes des fichiers déjà listés (`_base_helpers.py`, `status.py`, `banc.yml`), donc le banc s'est bien exécuté pour eux ; **aucune
réouverture rétroactive** n'est nécessaire — le déclenchement manuel a fait le travail cette fois. C'est un fait à retenir : un filtre par fichiers protège contre ce qu'on a pensé à lister.

### Risques / points à surveiller

- Le banc dure 6 à 8 minutes par version (3 jobs) : toute PR touchant ces répertoires paie ce coût (acceptable, le banc est la garde contre les faux PASSED).
- Le motif d'exclusion `!behave_runtime/generated/**` doit rester après `behave_runtime/**` (GitHub applique les motifs dans l'ordre) — gardé par le test.
