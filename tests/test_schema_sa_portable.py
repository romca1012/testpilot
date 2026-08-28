"""Garde-fou anti-dérive — `store/schema_sa.py` (modèle portable PostgreSQL) doit rester
SYNCHRONISÉ avec le VRAI schéma SQLite (`store/db.py` : `schema.sql` + 37 migrations).

Fondation portable PostgreSQL, phase 1/3 (voir docs/POSTGRES-MIGRATION.md). Ce lot est 100 %
additif : `db.py`/`repositories.py` n'ont pas bougé, `schema_sa.py` n'est branché sur AUCUN
runtime. Mais un fichier de modèle qui se contente d'être écrit une fois, puis jamais revérifié,
DÉRIVE en silence — exactement le mode de défaillance que la migration 19 a démontré dans `db.py`
(« mes tests exerçaient la dérivation du verdict, jamais la persistance de la nouvelle valeur »).

Ce fichier compare, table par table, colonne par colonne :
- le VRAI schéma — obtenu en appelant `get_initialized_db()` sur une base SQLite neuve, donc en
  traversant `schema.sql` PUIS les 37 migrations réellement appliquées, comme au démarrage du
  serveur (même discipline que `test_migration_28.py` : jamais une fixture SQL reconstruite à la
  main, aveugle à un défaut né dans `schema.sql` lui-même) ;
- le schéma PORTABLE — obtenu en appliquant `schema_sa.metadata.create_all()` sur une AUTRE base
  SQLite neuve.

Une migration future (38, 39…) ajoutée à `db.py` SANS son équivalent dans `schema_sa.py` fait
échouer ce test au lieu de laisser le futur portage PostgreSQL dériver en silence — c'est tout
l'objet de ce fichier.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from testpilot.store import schema_sa
from testpilot.store.db import _SCHEMA_VERSION, get_initialized_db


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def _colonnes(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    """`{nom_colonne: {"not_null": bool, "pk": bool}}` — assez pour détecter une dérive de
    structure sans être fragile au formatage exact d'une valeur DEFAULT (SQLAlchemy et SQLite
    ne rendent pas toujours `0`/`0.0`/`''` de façon identique, ce qui n'est PAS une dérive de
    schéma qui nous intéresse ici)."""
    return {
        r["name"]: {"not_null": bool(r["notnull"]), "pk": bool(r["pk"])}
        for r in conn.execute(f"PRAGMA table_info({table})")
    }


@pytest.fixture(scope="module")
def vrai_schema(tmp_path_factory) -> sqlite3.Connection:
    """Le VRAI schéma : `get_initialized_db()` — `schema.sql` PUIS les 37 migrations, comme au
    démarrage réel du serveur."""
    chemin = tmp_path_factory.mktemp("vrai_schema") / "reel.db"
    conn = get_initialized_db(chemin)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def schema_portable() -> sqlite3.Connection:
    """Le schéma PORTABLE : `schema_sa.metadata.create_all()`, sur une base SQLite SÉPARÉE —
    jamais celle du VRAI schéma, pour ne comparer que des bases fraîches et indépendantes."""
    engine = create_engine("sqlite:///:memory:")
    schema_sa.metadata.create_all(engine)
    conn = engine.raw_connection().driver_connection
    conn.row_factory = sqlite3.Row
    yield conn
    engine.dispose()


def test_la_version_de_reference_du_modele_portable_est_a_jour():
    """Le marqueur `ALIGNED_WITH_SCHEMA_VERSION` de `schema_sa.py` DOIT suivre `_SCHEMA_VERSION`
    (`db.py`). ⚠️ Ce test ne PROUVE pas que le contenu a été mis à jour — seulement que quelqu'un
    l'a délibérément déclaré à jour. Les tests suivants vérifient le contenu réel."""
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == _SCHEMA_VERSION, (
        "store/db.py a avancé (_SCHEMA_VERSION) sans que store/schema_sa.py ne suive"
        " (ALIGNED_WITH_SCHEMA_VERSION) — mets à jour le modèle portable ET son marqueur."
    )


def test_les_deux_schemas_portent_exactement_les_memes_tables(vrai_schema, schema_portable):
    reel = _tables(vrai_schema)
    portable = _tables(schema_portable)
    manquantes_dans_schema_sa = reel - portable
    en_trop_dans_schema_sa = portable - reel
    assert not manquantes_dans_schema_sa, (
        f"Table(s) du VRAI schéma absente(s) de schema_sa.py : {sorted(manquantes_dans_schema_sa)}"
    )
    assert not en_trop_dans_schema_sa, (
        f"Table(s) déclarée(s) dans schema_sa.py mais absente(s) du VRAI schéma :"
        f" {sorted(en_trop_dans_schema_sa)} (une table supprimée par une migration doit aussi"
        f" être retirée du modèle portable)"
    )


def test_chaque_table_porte_exactement_les_memes_colonnes(vrai_schema, schema_portable):
    """Le cœur du garde-fou : une migration future qui ajoute/retire/renomme une colonne dans
    `db.py` sans toucher `schema_sa.py` fait échouer CE test, table par table."""
    echecs = []
    for table in sorted(_tables(vrai_schema)):
        reel = _colonnes(vrai_schema, table)
        portable = _colonnes(schema_portable, table)
        if reel.keys() != portable.keys():
            manquantes = set(reel) - set(portable)
            en_trop = set(portable) - set(reel)
            echecs.append(
                f"{table} : colonnes manquantes dans schema_sa.py {sorted(manquantes)},"
                f" colonnes en trop {sorted(en_trop)}"
            )
    assert not echecs, "Dérive de colonnes détectée :\n" + "\n".join(echecs)


def test_les_cles_primaires_concordent(vrai_schema, schema_portable):
    for table in sorted(_tables(vrai_schema)):
        reel = {nom for nom, info in _colonnes(vrai_schema, table).items() if info["pk"]}
        portable = {nom for nom, info in _colonnes(schema_portable, table).items() if info["pk"]}
        assert reel == portable, (
            f"{table} : clé primaire réelle {sorted(reel)} != clé primaire portable"
            f" {sorted(portable)}"
        )


def test_la_nullabilite_concorde(vrai_schema, schema_portable):
    """NOT NULL est une partie du contrat que le modèle portable doit tenir, colonne par colonne
    — c'est ce qui détermine si Postgres acceptera les mêmes lignes que SQLite.

    ⚠️ **Exclut les colonnes de clé primaire.** SQLite ne pose PAS le drapeau `notnull` sur une
    colonne `PRIMARY KEY` dans `PRAGMA table_info` — un vieux comportement documenté de SQLite
    (« Unless the column is an INTEGER PRIMARY KEY... SQLite allows NULL values in a PRIMARY KEY
    column »), présent aussi bien dans le VRAI schéma que si on le retapait à l'identique. Le
    modèle portable, lui, déclare `primary_key=True` — SQLAlchemy en déduit `nullable=False`, ce
    qui est le comportement RÉELLEMENT voulu (et celui de PostgreSQL). Comparer cette colonne
    précise donnerait un FAUX POSITIF perpétuel, pas une dérive réelle ; l'unicité de la clé
    primaire est déjà vérifiée par `test_les_cles_primaires_concordent` ci-dessus."""
    echecs = []
    for table in sorted(_tables(vrai_schema)):
        reel = _colonnes(vrai_schema, table)
        portable = _colonnes(schema_portable, table)
        for col in reel.keys() & portable.keys():
            if reel[col]["pk"] or portable[col]["pk"]:
                continue
            if reel[col]["not_null"] != portable[col]["not_null"]:
                echecs.append(
                    f"{table}.{col} : NOT NULL réel={reel[col]['not_null']} "
                    f"vs portable={portable[col]['not_null']}"
                )
    assert not echecs, "Dérive de nullabilité détectée :\n" + "\n".join(echecs)
