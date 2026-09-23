# CLAUDE.md — Instructions permanentes pour Claude Code sur TestPilot

Ce fichier est lu à chaque session. Il dit **comment travailler** sur ce dépôt. Le **quoi**
(le chantier en cours) est dans `docs/PLAN-FIABILITE-VERDICT-2026-09.md`, découpé en lots
exécutables via les commandes `/lot-01-…` à `/lot-10-…` (`.claude/commands/`).

## 1. Ce qu'est TestPilot, en cinq lignes

Outil de test management piloté par IA : une spec devient un `.feature` Gherkin (+ steps Python)
écrit par un agent LLM (`src/testpilot/generation/`), relu par un humain (gate obligatoire),
puis exécuté **réellement** par Behave + Playwright dans un sous-processus
(`src/testpilot/execution/`, `behave_runtime/`). Le verdict est calculé de façon déterministe
sur **deux axes qui ne fusionnent jamais** : exécution et fonctionnel (`src/testpilot/verdict/`).
Connecteurs : `odoo` (RPC + UI) et `web` générique (UI seule) — `src/testpilot/connectors/`.

## 2. Hiérarchie des sources de vérité

1. `docs/brief-produit-outil-test-management-ia.md` — le brief produit. Seule source de vérité.
2. `docs/PRINCIPES.md` — ce qu'on ne re-débat plus.
3. `docs/CONTINUITE.md` §4 — **invariants à ne jamais régresser** (lis-les avant chaque lot).
4. `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — le chantier courant et son **registre de décisions**.

En cas de conflit entre ces documents et une consigne de lot : **arrête-toi et signale-le**.

## 3. Le principe qui fonde tout le projet

> **Le texte écrit par l'agent n'est jamais une source de vérité.**

Un verdict, une cause, une décision de réparation s'appuient sur un **signal du runtime** : type
d'exception, statut Behave, structure AST, réponse RPC, état du DOM. Jamais sur le libellé d'un
step, un commentaire, ou ce que l'agent « dit » avoir fait. Toute modification qui lirait le texte
de l'agent pour décider est refusée (décision 0015).

## 4. Règles de verdict — non négociables

- **Faux PASSED = pire défaut possible.** Un changement qui peut rendre `conforme` un scénario qui
  n'a rien prouvé est refusé, même s'il améliore un autre indicateur.
- Un échec technique ne vaut **jamais** `conforme` (CONTINUITE §4.5).
- Tu ne modifies **jamais** une assertion, un seuil, un `expect`, un `constater` pour faire passer
  un test au vert. Si un test du dépôt échoue après ton changement, c'est ton changement qu'on
  interroge d'abord.
- Toute nouvelle assertion de la bibliothèque de steps est livrée avec un test **de
  falsifiabilité** : il prouve qu'elle échoue quand l'application se comporte mal (modèle :
  `tests/test_comptage_falsifiable.py`, `tests/test_bibliotheque_falsifiable.py`).
- Le garde-fou anti-production (`ODOO_ENV=prod`) n'est jamais contourné ni affaibli.

## 5. Méthode de travail

1. **Lis avant d'écrire.** Chaque lot liste ses fichiers « à lire d'abord ». Lis-les en entier.
2. **Mesure avant de supposer.** Si une consigne repose sur un comportement de Behave, Playwright
   ou Odoo (ex. le champ `step_type` du JSON Behave), vérifie-le dans la source ou sur un run réel
   et note le résultat dans ton rapport.
3. **Décisions structurantes = arrêt.** Modèle de données, nouvelle valeur d'enum, sémantique d'un
   statut à l'écran, comportement bloquant vs détectif : si le lot dépend d'une décision `D#` du
   registre non marquée « validée », **tu t'arrêtes** et tu présentes une proposition courte.
4. **Plan d'abord pour tout lot non trivial** : liste des fichiers modifiés, fonctions touchées,
   tests ajoutés. Puis exécution.
5. **Un lot = une branche = des commits atomiques** par brique logique. Tests verts avant chaque
   commit. **Aucune mention de Claude ni co-auteur IA dans les messages de commit.**
6. **Signale les écarts** au lieu de les arrondir : si le code ne correspond pas à ce que dit le
   plan (numéro de ligne décalé, fonction renommée, comportement différent), dis-le.
7. **Ne fais pas plus que le lot.** Une amélioration hors périmètre va dans « Suggestions » du
   rapport, pas dans le diff.

## 6. Conventions de code

- Python ≥ 3.10, `ruff` ligne 100. Commentaires et docstrings **en français**, qui disent
  **pourquoi** (le style du dépôt : cause mesurée, date, référence de décision).
- Modules de verdict et de taxonomie **purs** : aucune I/O, aucun réseau, aucun LLM.
- Tout signal produit pendant un run Behave et utile hors du sous-processus passe par un
  **fichier sidecar** (motif existant : `FIELD_FALLBACK_FILE_ENV`, `SELECTOR_TIER_FILE_ENV`…
  dans `behave_runner.py`), jamais par le log (Behave l'avale sur un scénario vert).
- Imports des helpers de steps **au niveau module**, jamais différés dans une fonction
  (bug mesuré le 2026-09-22 : `steps/` sort du `sys.path` après le chargement).
- Rien de spécifique à une instance client (Sapian, SauceDemo…) dans `steps_library/generic/`
  ni dans `behave_runtime/environment.py`.
- Aucune valeur d'enum brute à l'écran : toute nouvelle valeur reçoit un libellé français côté
  serveur **et** frontend (CONTINUITE §4.7).

### Modifier le schéma de données

Une nouvelle colonne ou une nouvelle valeur d'enum exige **les quatre** :
1. une migration SQLite `_migrate_N_...` dans `src/testpilot/store/db.py` (idempotente) ;
2. une révision Alembic dans `alembic/versions/` (PostgreSQL) chaînée sur la tête actuelle ;
3. la mise à jour de `src/testpilot/store/schema_sa.py`, y compris les contraintes `CHECK` ;
4. un test `tests/test_migration_<sujet>.py` + le passage de `tests/test_schema_sa_portable.py`.

## 7. Commandes

```bash
python -m pytest -q                                   # suite par défaut (conformance exclue)
python -m pytest -q tests/test_<sujet>.py             # ciblé
python -m pytest -m conformance -v                    # vrai navigateur, applis publiques
python -m ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts
npm --prefix frontend test                            # vitest
npm --prefix frontend run type-check
alembic upgrade head                                  # uniquement avec TESTPILOT_DB_URL PostgreSQL
python scripts/audit_generation_quality.py --db data/testpilot.db
# À partir du lot 04 :
docker compose -f compose.banc.yml up -d              # instance Odoo de référence
python scripts/banc_mesure.py --version 17.0          # indicateurs de fiabilité du verdict
```

Poste Windows du porteur : l'environnement virtuel est `.venv-v1/` (`.venv-v1\Scripts\python.exe`).

## 8. Contrainte de coût

§9 du brief : **moins de 1 € par nouveau cas** (génération + exécution + réparations). Toute
modification des prompts ou des outils de l'agent (lot 09) rapporte le coût mesuré avant/après
(`scripts/mesure_cout_cas.py`). Un gain de fiabilité qui fait sortir du §9 est à arbitrer, pas à
livrer.

## 9. Définition de « terminé » pour un lot

- Critères d'acceptation du lot tous vérifiés, un par un, dans le rapport.
- `python -m pytest -q` vert, ruff critique vert, frontend vert si touché.
- Documentation touchée à jour (au minimum la ligne du lot dans le plan : statut + date).
- Rapport de fin de lot au format ci-dessous, sans enjoliver.

## 10. Format du rapport de fin de lot

```
## Lot NN — <titre> — <terminé | partiel | bloqué>
Décisions utilisées : D# (validée le …)
Changements : <fichier> — <ce qui change et pourquoi> (une ligne par fichier)
Tests ajoutés : <fichier::test> — <ce qu'il prouve>
Critères d'acceptation : [x] … / [ ] … (+ raison si non coché)
Mesures : <avant → après, avec l'échantillon et la commande>
Écarts constatés avec le plan : …
Risques / points à surveiller : …
Suggestions hors périmètre : …
```

## 11. Sous-agent de revue

Avant de déclarer un lot terminé, lance le sous-agent `verdict-reviewer`
(`.claude/agents/verdict-reviewer.md`) sur ton diff. Traite chaque point bloquant qu'il remonte
ou justifie explicitement pourquoi il ne s'applique pas.
