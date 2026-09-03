# TestPilot

Outil de test management piloté par IA : il **génère** des tests fonctionnels à partir d'une
spécification, fait **valider le métier par un humain**, les **exécute réellement** contre
l'application cible, et produit un **verdict honnête** — le statut « testé » n'est jamais une case
cochée, toujours la conséquence d'une exécution réelle.

## Documentation

| Besoin | Document |
|---|---|
| Comprendre le système (contexte, conteneurs, composants, décisions) | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Utiliser l'API (auth, rôles, format d'erreur, plafond de charge) | [`docs/API.md`](docs/API.md) |
| Installer / déployer (SQLite ou PostgreSQL) | [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md) |
| Exploiter au quotidien (santé, sauvegardes, pannes courantes) | [`docs/EXPLOITATION.md`](docs/EXPLOITATION.md) |
| Vision et périmètre produit (seule source de vérité, journal d'amendements) | [`docs/brief-produit-outil-test-management-ia.md`](docs/brief-produit-outil-test-management-ia.md) |
| Carte du code et pièges connus, au fil de l'eau | [`docs/ONBOARDING.md`](docs/ONBOARDING.md) |

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

## Le verdict, en quatre issues

| Ce qui s'est passé | Issue |
|---|---|
| le test n'a pas pu tourner | **erreur technique** |
| le test a tourné, l'application est conforme | **conforme** |
| le test a tourné, l'application ne l'est pas | **non conforme** |
| le test a tourné, ce sont **ses données** qui ont été refusées | **donnée du test invalide** |

Et une règle qui prime sur tout : **l'outil n'accuse jamais sans preuve.** Si l'application ne crée
rien *et* n'affiche rien, il nomme ce **refus silencieux** au lieu de le convertir en défaut.

## Pile technique

Backend — Python ≥ 3.10 (`pyproject.toml`) :

- **FastAPI** ≥ 0.115 + **Uvicorn** ≥ 0.32 — API et serveur.
- **Behave** ≥ 1.2.6 + **Playwright** ≥ 1.40 — exécution réelle des scénarios.
- **Anthropic** ≥ 0.40 — génération et réparation des tests (API Claude).
- **OdooRPC** ≥ 0.9 — connecteur vers l'application testée (Odoo, aujourd'hui le seul connecteur).
- **SQLAlchemy** ≥ 2.0 + **Alembic** ≥ 1.13 + **psycopg** ≥ 3.1 — runtime PostgreSQL réel, optionnel
  (`TESTPILOT_DB_URL` vide = SQLite, comportement inchangé ; voir `docs/ARCHITECTURE.md` §4 et
  `docs/DEPLOIEMENT.md` pour la bascule).
- **cryptography** ≥ 42.0 — chiffrement au repos des secrets de connexion.

Frontend — `frontend/package.json` :

- **Vue** 3.5 + **vue-router** 4.5 + **@tanstack/vue-query** 5.101 — interface et état serveur.
- **Vite** 6 + **TypeScript** 5.6 — outillage et build.
- **Tailwind CSS** 3.4 — styles.

## Structure

```
src/testpilot/
  config.py         source unique de configuration
  analysis/         spec → plan de test
  generation/        plan → .feature + steps (boucle ReAct, résolveur déterministe)
  execution/         dry-run + exécution réelle (Behave/Playwright)
  verdict/           les deux axes, la taxonomie, l'origine du défaut, le gate
  guardrails/        plafonds de coût par cas, disjoncteur de réparation, plafond de charge
  connectors/        interface + connecteur Odoo (l'abstraction attend un 2ᵉ connecteur)
  reporting/         rapport JSON/HTML à deux axes
  store/             SQLite (défaut) ou PostgreSQL réel (TESTPILOT_DB_URL) + secrets
  api/               FastAPI : routes, services, l'API et, en production, le frontend compilé
frontend/           interface Vue 3 (disposition inspirée de TestRail)
behave_runtime/     harnais Behave + bibliothèque de steps partagée + tests générés
tests/              tests de l'outil
```

## Démarrage rapide

Prérequis : Python ≥ 3.10, Node.js, accès à l'application testée et à l'API Anthropic.

```bash
pip install -e ".[dev]"
python -m playwright install chromium
cd frontend && npm install && cd ..
```

Deux processus en développement :

```bash
uvicorn testpilot.api.app:app --reload    # API sur :8000
cd frontend && npm run dev                # interface sur :5173
```

En production, `npm run build` (dans `frontend/`) suffit : l'API sert l'interface compilée sur le
même port dès que `frontend/dist/` existe (`api/app.py`).

Tests :

```bash
pytest                                    # suite backend
cd frontend && npm test                   # suite frontend (Vitest)
```

## Sécurité — à lire avant de l'exposer sur un réseau

- La connexion par compte est obligatoire ; les rôles globaux et les rôles par projet sont
  contrôlés par le serveur (détail dans `docs/API.md`).
- `TESTPILOT_SECRET_KEY` chiffre les mots de passe de connexion des projets stockés en base.
- `TESTPILOT_SESSION_SECRET` signe les sessions et doit être distincte de la clé ci-dessus.
- `TESTPILOT_COOKIE_SECURE=true` est obligatoire derrière HTTPS en production.
- Le garde-fou anti-production reste intact : `ODOO_ENV=prod` **bloque toute exécution**.

## Persistance

SQLite par défaut (`data/testpilot.db`, réglable via `TESTPILOT_DATA_DIR`/`TESTPILOT_DB_PATH`),
schéma construit et mis à jour automatiquement à l'ouverture (`store/db.py`) — une sauvegarde
horodatée est créée AVANT toute migration réellement en attente, dans ce même code de démarrage.
PostgreSQL réel en option (`TESTPILOT_DB_URL`) : voir `docs/DEPLOIEMENT.md` pour la bascule et la
migration des données existantes.

La base et les artefacts générés ne sont pas versionnés — **sauf** la cartographie du domaine
(`data/domain/*.json`), qui est une **référence** dont la revue passe par le diff git (voir
`docs/ARCHITECTURE.md` §4).

`data/regles-apprises/*.jsonl` porte ce que l'application a **refusé pour de vrai** pendant un run,
pour que l'outil ne réécrive plus une valeur invalide. Non versionné — c'est une mesure
d'exécution, pas une référence — mais à sauvegarder.
