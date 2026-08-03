# TestPilot

Outil de test management piloté par IA : il **génère** des tests fonctionnels à partir d'une
spécification, fait **valider le métier par un humain**, les **exécute réellement** contre
l'application cible, et produit un **verdict honnête** — le statut « testé » n'est jamais une case
cochée, toujours la conséquence d'une exécution réelle.

- **🆕 Vous arrivez sur le projet ?** `docs/ONBOARDING.md` — ce que fait le produit, la stack
  technique, la carte du code et les pièges. Commencez par là.
- **Vision et périmètre** : `docs/brief-produit-outil-test-management-ia.md` (seule source de
  vérité, avec son journal d'amendements).
- **État réel et route** : `docs/PLAN.md`.
- **Installer sur un serveur** : `docs/DEPLOIEMENT.md`.

## Ce que le produit fait aujourd'hui

```
Créer un projet  →  saisir sa connexion (l'application testée)
   →  EXPLORER l'application (crawl déterministe, aucun LLM) → sa cartographie
   →  créer un module, puis un cas :
        • « Ajouter un cas de test »  = saisie MANUELLE (métier, sans IA)
             puis « Automatiser avec l'IA » → son test technique
        • « Générer des cas de test » = l'IA depuis une spec (texte ou fichier)
             → pause : l'IA rédige le métier, l'humain corrige → puis le Gherkin
   →  regrouper des cas en CAMPAGNE (run) — transverse, multi-modules
   →  LANCER la campagne → verdict par cas × campagne
   →  CLÔTURER (lecture seule, réversible)
   →  suivre la qualité de génération et les coûts dans le temps
```

Chaque maillon est **prouvé en réel**, pas seulement testé. Coût mesuré : **~0,08 à 0,11 $ par
cas** — la cible du brief est à 1 €.

## Le verdict, en quatre issues

| Ce qui s'est passé | Issue |
|---|---|
| le test n'a pas pu tourner | **erreur technique** |
| le test a tourné, l'application est conforme | **conforme** |
| le test a tourné, l'application ne l'est pas | **non conforme** |
| le test a tourné, ce sont **ses données** qui ont été refusées | **donnée du test invalide** |

Et une règle qui prime sur tout : **l'outil n'accuse jamais sans preuve.** Si l'application ne crée
rien *et* n'affiche rien, il nomme ce **refus silencieux** au lieu de le convertir en défaut.

## Structure

```
src/testpilot/
  config.py         source unique de configuration
  analysis/         spec → plan de test
  generation/       plan → .feature + steps (boucle ReAct, résolveur déterministe)
  execution/        dry-run + exécution réelle (Behave/Playwright)
  verdict/          les deux axes, la taxonomie, l'origine du défaut, le gate
  guardrails/       plafonds de coût par cas, disjoncteur de réparation
  connectors/       cible + connecteur Odoo (l'abstraction viendra au 2ᵉ connecteur)
  reporting/        rapport JSON/HTML à deux axes
  store/            SQLite (schéma portable PostgreSQL) + chiffrement des secrets
  api/              FastAPI : l'API et, en production, le frontend compilé
frontend/           interface Vue 3 (disposition inspirée de TestRail)
behave_runtime/     harnais Behave + bibliothèque de steps partagée + tests générés
tests/              tests de l'outil
```

## Développement

```bash
pip install -e ".[dev]"
python -m playwright install chromium
pytest                                   # 915 tests
cd frontend && npm install && npm test   # 110 tests
```

Deux processus en développement :

```bash
uvicorn testpilot.api.app:app --reload    # API sur :8000
cd frontend && npm run dev                # interface sur :5173
```

En production, `npm run build` suffit : l'API sert l'interface compilée sur le même port.

## Sécurité — à lire avant de l'exposer sur un réseau

- `TESTPILOT_ACCESS_PASSWORD` : **le verrou d'instance**. Vide = aucune protection : quiconque
  atteint le port lance des tests contre votre application et lit vos rapports.
- `TESTPILOT_SECRET_KEY` : chiffre les mots de passe de connexion stockés en base.
- **Pas de comptes, pas de rôles** : hors V1 (§8 du brief), à traiter avant tout usage par un
  client externe. Le nom saisi à la connexion est une **signature déclarée**, pas une identité.
- Le garde-fou anti-production reste intact : `ODOO_ENV=prod` **bloque toute exécution**.

## Persistance

SQLite (`data/testpilot.db`), schéma en SQL portable (`store/schema.sql`), migrations automatiques
et idempotentes à l'ouverture. La base et les artefacts générés ne sont pas versionnés — **sauf**
la cartographie du domaine (`data/domain/*.json`), qui est une **référence** dont la revue passe
par le diff git.

`data/regles-apprises/*.jsonl` porte ce que l'application a **refusé pour de vrai** pendant un run,
pour que l'outil ne réécrive plus une valeur invalide (`docs/decisions/0023`). C'est le seul angle
d'attaque sur les règles de validation écrites en JavaScript, qu'aucun crawl statique ne verra.
Non versionné — c'est une mesure d'exécution, pas une référence — mais **à sauvegarder**.
