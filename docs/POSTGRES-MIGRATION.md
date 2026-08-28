# Fondation portable PostgreSQL — phase 1/3

> **Statut : phase 1 (fondation) terminée, 2026-08-28. Rien n'est branché sur le runtime.**
> `db.py`, `repositories.py` et l'application qui tourne n'ont **pas changé de comportement** à
> l'issue de ce lot — c'est la contrainte qui définissait la tâche, et elle a été tenue de bout en
> bout. Ce document décrit ce qui a été posé, la preuve qu'il fonctionne sur les deux moteurs, et
> ce qu'il reste à faire **avant** de pouvoir prononcer le mot « bascule ».

## Le plan en trois temps

1. **Fondation** (ce document, ce lot) — un modèle de schéma portable et la preuve qu'il se
   recrée identiquement sur SQLite et sur PostgreSQL. Purement additif.
2. **Double-run de vérification** (à venir) — faire tourner l'application contre SQLite (comme
   aujourd'hui) ET contre PostgreSQL en parallèle, sur des données réelles ou proches du réel,
   et comparer les résultats ligne à ligne avant de faire confiance au second moteur.
3. **Bascule réelle** (à venir) — décider comment et quand `db.py`/le déploiement basculent
   effectivement sur PostgreSQL en production, migrer les données existantes, retirer (ou garder,
   à trancher) le chemin SQLite.

**Ce lot ne fait QUE la phase 1.** Rien ci-dessous ne doit être lu comme une promesse sur les
phases 2 et 3 — voir « Ce qui n'est PAS prouvé » en fin de document.

## Pourquoi une fondation séparée, et pourquoi maintenant

`schema.sql` se prétend « SQL portable vers PostgreSQL » depuis l'Incrément 0, mais utilise
`INTEGER PRIMARY KEY AUTOINCREMENT` — un mot-clé propre à SQLite, invalide tel quel sous
PostgreSQL. Les 37 migrations de `db.py` ont ensuite fait évoluer le schéma réel loin de ce que
`schema.sql` décrit seul (voir son commentaire de fin : plusieurs tables n'existent QUE par
migration). Toute tentative de porter ce schéma « à l'œil », en relisant les 37 migrations une par
une, est exactement le mode de défaillance que ce projet a déjà mesuré une fois : la migration 19
de `db.py` a dû être corrigée parce qu'un CHECK avait été oublié pendant que le code Python
évoluait — « mes tests exerçaient la dérivation du verdict, jamais la persistance de la nouvelle
valeur ». Reproduire cette erreur sur un portage de moteur entier serait bien plus coûteux à
détecter.

## Ce qui a été fait

### 1. Dépendances (`pyproject.toml`)

`sqlalchemy>=2.0` et `alembic>=1.13` sont dans les dépendances **principales** — elles serviront
au runtime après la bascule (phase 3), pas seulement à générer des migrations en développement.
`psycopg[binary]>=3.1` (pilote PostgreSQL) est dans `dev` : il ne sert qu'à PROUVER la migration
sur un vrai PostgreSQL (ce lot) et au double-run (phase 2) ; le faire monter en dépendance
principale est une décision qui appartient à la phase 3, pas à celle-ci.

### 2. Introspection du VRAI schéma (`scripts/introspect_schema.py`)

Un script d'inspection, pas de génération automatique : il appelle
`testpilot.store.db.get_initialized_db()` sur une base SQLite **temporaire** — donc `schema.sql`
PUIS les 37 migrations, dans l'ordre réel, exactement le chemin qu'emprunte le serveur au
démarrage — puis interroge SQLite lui-même (`sqlite_master`, `PRAGMA table_info`,
`PRAGMA foreign_key_list`, `PRAGMA index_list`/`index_info`, et le SQL de création stocké pour en
extraire les `CHECK`, que `PRAGMA` n'expose pas). Sa sortie (24 tables, colonnes, FK, index,
triggers) est la vérité terrain à partir de laquelle `schema_sa.py` a été écrit, colonne par
colonne, CHECK par CHECK — jamais retranscrite les yeux sur les migrations.

```
PYTHONUTF8=1 python scripts/introspect_schema.py            # affichage lisible
PYTHONUTF8=1 python scripts/introspect_schema.py --json out.json
```

### 3. Le modèle portable (`src/testpilot/store/schema_sa.py`)

24 tables en `sqlalchemy.Table` (Core, pas l'ORM déclaratif — cohérent avec le choix déjà pris de
garder les repositories en SQL brut / `sqlite3.Row`). Conventions reprises **telles quelles** de
`schema.sql`, jamais réinventées :
- timestamps en `Text` (ISO-8601 UTC), jamais un type date/heure natif du moteur ;
- booléens en `Integer` 0/1 (`is_active`, `is_archived`, `auto_enveloppe`…), jamais `Boolean` ;
- enums en `Text` + `CheckConstraint`, jamais un ENUM natif — un administrateur peut ajouter une
  valeur `type`/`etat` sans migration de schéma, exactement comme aujourd'hui.

Les **27 `CHECK`** du schéma réel (`origin`, `priority`, les deux axes de statut, `role`,
`selection_mode`, le XOR de `test_result`…) sont tous repris, nommés (`ck_<table>_<colonne>`), pas
perdus en route.

### 4. La preuve AUTOINCREMENT

Chaque clé primaire entière est déclarée une seule fois :

```python
Column("id", Integer, primary_key=True, autoincrement=True)
```

avec `sqlite_autoincrement=True` au niveau de la table (nécessaire pour que SQLAlchemy émette
littéralement `AUTOINCREMENT` sous SQLite — sans ce drapeau de table, `INTEGER PRIMARY KEY` suffit
au sens SQLite mais ne produit pas le mot-clé, une nuance vérifiée en pratique pendant ce lot).
**Aucun DDL de dialecte n'est écrit à la main.** Extrait exact, `project.id`, obtenu en compilant
`CreateTable(schema_sa.project)` sous chaque dialecte :

```sql
-- SQLite (sqlalchemy.dialects.sqlite)
CREATE TABLE project (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	...

-- PostgreSQL (sqlalchemy.dialects.postgresql)
CREATE TABLE project (
	id SERIAL NOT NULL,
	...
	PRIMARY KEY (id)
```

Et sur le VRAI conteneur PostgreSQL de la preuve (§5), la colonne réellement créée :

```
 column_name |           column_default
-------------+-------------------------------------
 id          | nextval('project_id_seq'::regclass)
```

— la séquence PostgreSQL équivalente, générée sans qu'aucun `CREATE SEQUENCE` n'ait été écrit.

### 5. Alembic (`alembic.ini`, `alembic/env.py`, `alembic/versions/`)

`alembic/env.py` résout l'URL de connexion dans cet ordre :
1. `TESTPILOT_DB_URL` (variable d'environnement) ;
2. à défaut, repli sur `testpilot.config.DB_PATH` — le chemin SQLite **actuel** de l'application.
   Quiconque n'a jamais entendu parler de cette fondation obtient exactement le même
   comportement qu'avant ce lot.

`target_metadata = schema_sa.metadata`. Une seule migration existe :
`alembic/versions/adc3e4b5c1bb_baseline_schema_portable_phase_1_.py` — la **baseline**, générée
par `alembic revision --autogenerate` contre une base vide. **C'est ainsi que les 37 migrations
SQLite se traduisent en Alembic aujourd'hui : en UNE seule migration qui recrée l'état final**, pas
37 migrations Alembic parallèles à celles de `db.py`. Les deux historiques ne cherchent pas à se
répondre ligne par ligne — Alembic part de l'état CIBLE (celui que `get_initialized_db()` produit
aujourd'hui), pas de l'historique qui y a mené. Une base SQLite pré-existante n'est de toute façon
pas concernée par Alembic dans cette phase : lui appliquer la baseline sur une base déjà remplie
échouerait (les tables existent déjà) — Alembic sait aujourd'hui créer un schéma NEUF, sur les deux
moteurs ; migrer des données réelles est un problème de la phase 2/3, pas de celui-ci.

### 6. Garde-fou anti-dérive (`tests/test_schema_sa_portable.py`)

Compare, à chaque exécution de la suite : le VRAI schéma (`get_initialized_db()` sur une base
neuve) et le schéma portable (`schema_sa.metadata.create_all()` sur une autre base neuve) — mêmes
tables, mêmes colonnes par table, mêmes clés primaires, même nullabilité. Une migration future (38,
39…) ajoutée à `db.py` sans son équivalent dans `schema_sa.py` fait échouer ce test au lieu de
laisser le futur portage PostgreSQL dériver en silence. Un test séparé vérifie aussi que le
marqueur `schema_sa.ALIGNED_WITH_SCHEMA_VERSION` suit `db._SCHEMA_VERSION` — un rappel explicite,
pas seulement une comparaison structurelle silencieuse.

## Preuve réelle — les deux moteurs

**SQLite, base neuve :**
```
TESTPILOT_DB_URL="sqlite:///./preuve_sqlite_tmp.db" python -m alembic upgrade head
```
→ succès, 24 tables créées, `alembic_version` posée sur `adc3e4b5c1bb`. Fichier temporaire
supprimé après vérification (jamais commité — `*.db` est dans `.gitignore`).

**PostgreSQL, conteneur JETABLE et ISOLÉ** (port 5433, distinct du conteneur Odoo existant sur
5431 — `repo_v17-db-1`, non touché) :

```bash
docker run -d --rm --name testpilot-pg-foundation-test \
  -e POSTGRES_PASSWORD=testpilot -e POSTGRES_USER=testpilot -e POSTGRES_DB=testpilot \
  -p 5433:5432 postgres:16

TESTPILOT_DB_URL="postgresql+psycopg://testpilot:testpilot@localhost:5433/testpilot" \
  python -m alembic upgrade head

docker stop testpilot-pg-foundation-test   # --rm : suppression automatique à l'arrêt
```

Résultat : **succès sans aucune erreur de syntaxe PostgreSQL.** 24 tables applicatives +
`alembic_version` (vérifié par `\dt`), **27 contraintes `CHECK` nommées** retrouvées telles quelles
dans `pg_constraint` (`ck_test_case_priority`, `ck_test_result_mode_coherence`, …), les clés
étrangères `ON DELETE CASCADE` de `project_group_access`/`user_group_member` posées correctement,
l'index unique partiel `uq_project_name` recréé avec sa clause `WHERE deleted_at = ''::text`. Le
conteneur a été arrêté et supprimé à la fin de la vérification ; les conteneurs Odoo
(`repo_v17-odoo17-1`, `repo_v17-db-1`, port 5431) n'ont à aucun moment été touchés.

## Ce qui n'est PAS prouvé — limites honnêtes

- **Rien n'a été prouvé sur de VRAIES données de production.** Toute la preuve ci-dessus porte sur
  un schéma **vide**. Un `CREATE TABLE` qui réussit ne dit rien sur la MIGRATION de lignes
  réelles (encodages, valeurs qui violeraient un `CHECK` ajouté après coup, volumétrie) — c'est
  exactement l'objet de la phase 2 (double-run).
- **`COLLATE NOCASE`** (utilisé par SQLite sur `uq_project_name`, `uq_module_project_name`,
  `uq_group_module_title`, `uq_case_group_title` pour une unicité insensible à la casse ASCII)
  n'est **pas traduit**. Les index correspondants sont recréés dans `schema_sa.py` avec la même
  clause `WHERE` mais SANS collation particulière : sous PostgreSQL, deux noms qui ne diffèrent
  que par la casse ne seraient PAS bloqués par cet index tel quel. À trancher en phase 2/3
  (`citext`, une expression d'index `lower(...)`, ou une garde applicative renforcée — les repos
  Python ont déjà une garde `casefold` en première ligne de défense, documentée dans `db.py`).
- **Le trigger `trg_resultat_suit_le_mode_de_sa_campagne`** (migration 27, sur `test_result` — il
  refuse d'insérer un résultat dont le mode ne concorde pas avec celui de sa campagne) n'est **pas
  reproduit**. Un déclencheur SQL n'est pas portable via SQLAlchemy Core sans réécrire son corps
  par moteur ; ce lot ne le fait pas. L'invariant qu'il protège devra être réaffirmé explicitement
  en phase 2/3.
- **Aucune donnée n'a été migrée d'un moteur à l'autre.** La baseline Alembic crée un schéma NEUF ;
  elle ne sait pas (et n'essaie pas) de copier le contenu d'une base SQLite existante vers
  PostgreSQL. C'est un chantier à part entière de la phase 2/3.
- **Le double-run (phase 2) n'a pas commencé.** Cette fondation ne dit rien sur les différences de
  comportement RUNTIME entre les deux moteurs (verrouillage, transactions, types numériques REAL
  vs `double precision`, tri de texte sans `COLLATE NOCASE`…) — seulement que le DDL se recrée sur
  les deux sans erreur.

## Pour rejouer la preuve

```bash
# SQLite (fichier jetable)
TESTPILOT_DB_URL="sqlite:///./verif.db" python -m alembic upgrade head
rm verif.db

# PostgreSQL (conteneur jetable, port 5433 — jamais 5431)
docker run -d --rm --name testpilot-pg-foundation-test \
  -e POSTGRES_PASSWORD=testpilot -e POSTGRES_USER=testpilot -e POSTGRES_DB=testpilot \
  -p 5433:5432 postgres:16
TESTPILOT_DB_URL="postgresql+psycopg://testpilot:testpilot@localhost:5433/testpilot" \
  python -m alembic upgrade head
docker stop testpilot-pg-foundation-test

# Garde-fou anti-dérive
pytest tests/test_schema_sa_portable.py -v
```
