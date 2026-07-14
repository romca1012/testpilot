# TestPilot

Outil de test management piloté par IA : il **génère** des tests fonctionnels à partir
d'une spécification, les fait **relire par un humain**, les **exécute réellement** contre
l'application cible, et produit un **verdict honnête** — le statut « testé » n'est jamais
une case cochée, toujours la conséquence d'une exécution réelle.

Voir `docs/brief-produit-outil-test-management-ia.md` pour la vision complète.

## Périmètre actuel — Incrément 0 (preuve de concept)

Un seul module Odoo, un cas de test généré de bout en bout :

```
spec → Gherkin/script (IA) → relecture humaine obligatoire → exécution → rapport
```

avec, dès ce socle, les deux invariants critiques du brief :

- **Deux statuts indépendants** (§5) : *exécution* (a-t-il pu tourner techniquement ?)
  et *fonctionnel* (le comportement est-il conforme au besoin ?), toujours croisés.
- **Gate de relecture** (§4) : la première exécution d'un cas généré par l'IA exige une
  confirmation humaine explicite.

Hors périmètre pour l'instant : gestion de projet, tests de charge/sécurité, CI/CD,
multi-connecteurs au-delà d'Odoo, frontend.

## Structure

```
src/testpilot/
  config.py         source unique de configuration
  analysis/         PILIER 1 — spec → plan de test
  generation/       PILIER 2 — plan → .feature + _steps.py (boucle ReAct)
  execution/        PILIER 3 — dry-run + exécution réelle (Behave/Playwright)
  verdict/          §5 — deux statuts, taxonomie, origine du défaut, gate de relecture
  guardrails/       §6 — cap par-run, budget mensuel, disjoncteur de réparation
  connectors/       abstraction cible + connecteur Odoo
  reporting/        PILIER 4 — rapport JSON/HTML à deux axes
  store/            persistance légère SQLite (portable PostgreSQL)
  cli.py            orchestration bout-en-bout + gate interactif
behave_runtime/     échafaudage Behave + bibliothèque de steps + tests générés
tests/              tests unitaires de l'outil
```

## Persistance

SQLite (`data/testpilot.db`), schéma écrit en SQL portable (`store/schema.sql`) — les
tables migreront telles quelles vers PostgreSQL à l'Incrément 1. La base et les artefacts
générés (`behave_runtime/generated/`) ne sont pas versionnés : la source de vérité de
l'historisation est la table `test_case_version`.

## Développement

```bash
pip install -e ".[dev]"
pytest
```
