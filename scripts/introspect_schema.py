"""Introspection du VRAI schéma SQLite — la vérité terrain pour la fondation PostgreSQL.

Fondation portable PostgreSQL, phase 1/3 (voir docs/POSTGRES-MIGRATION.md). Ce script ne
retranscrit RIEN à la main depuis les 37 migrations de `store/db.py` : il appelle
`get_initialized_db()` sur une base SQLite TEMPORAIRE (donc `schema.sql` PUIS les 37 migrations
réellement appliquées, dans l'ordre réel), puis interroge SQLite lui-même — `sqlite_master`,
`PRAGMA table_info`, `PRAGMA foreign_key_list`, `PRAGMA index_list`/`index_info` — pour obtenir
l'état RÉEL et complet de chaque table : colonnes (type, NOT NULL, défaut, clé primaire), clés
étrangères, index (dont les UNIQUE partiels), et les contraintes CHECK (extraites du SQL de
création stocké par SQLite lui-même dans `sqlite_master.sql` — PRAGMA ne les expose pas).

C'est délibérément un script d'INSPECTION, pas de génération automatique : `store/schema_sa.py`
est écrit à la main à partir de sa sortie, colonne par colonne, pour que chaque CHECK et chaque
choix de type reste un choix RELU par un humain plutôt qu'un texte re-parsé aveuglément — mêmes
enjeux que `_sql_sans_colonne` dans `db.py`, qui se méfie déjà d'un bête découpage sur la virgule.

Usage :
    PYTHONUTF8=1 python scripts/introspect_schema.py            # affichage lisible
    PYTHONUTF8=1 python scripts/introspect_schema.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot.store.db import _SCHEMA_VERSION, get_initialized_db


def _tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _create_sql(conn, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row["sql"] if row else ""


def _colonnes(conn, table: str) -> list[dict]:
    cols = []
    for r in conn.execute(f"PRAGMA table_info({table})"):
        cols.append(
            {
                "nom": r["name"],
                "type": r["type"],
                "not_null": bool(r["notnull"]),
                "defaut": r["dflt_value"],
                # `pk` > 0 = position dans la clé primaire composite ; 1 seul == PK simple.
                "pk": r["pk"],
            }
        )
    return cols


def _cles_etrangeres(conn, table: str) -> list[dict]:
    fks = []
    for r in conn.execute(f"PRAGMA foreign_key_list({table})"):
        fks.append({"colonne": r["from"], "table_cible": r["table"], "colonne_cible": r["to"]})
    return fks


def _index(conn, table: str) -> list[dict]:
    idx = []
    for r in conn.execute(f"PRAGMA index_list({table})"):
        nom = r["name"]
        if nom.startswith("sqlite_autoindex_"):
            continue  # généré par une contrainte UNIQUE/PK de colonne, pas un index déclaré
        colonnes = [c["name"] for c in conn.execute(f"PRAGMA index_info({nom})")]
        # Le SQL de création porte la clause WHERE d'un index PARTIEL — absente de PRAGMA.
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (nom,)
        ).fetchone()
        idx.append(
            {
                "nom": nom,
                "colonnes": colonnes,
                "unique": bool(r["unique"]),
                "sql": sql_row["sql"] if sql_row else None,
            }
        )
    return idx


def _triggers(conn, table: str) -> list[dict]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)
    ).fetchall()
    return [{"nom": r["name"], "sql": r["sql"]} for r in rows]


def introspecter() -> dict:
    """Ouvre une base SQLite neuve dans un répertoire temporaire, la fait traverser
    `get_initialized_db()` (schema.sql + les 37 migrations), puis introspecte le résultat.

    Le répertoire temporaire est nettoyé automatiquement (`TemporaryDirectory`) : ce script ne
    laisse jamais de fichier `.db` derrière lui, et ne touche jamais `data/testpilot.db`.
    """
    with tempfile.TemporaryDirectory(prefix="testpilot_introspect_") as tmp:
        db_path = Path(tmp) / "introspection.db"
        conn = get_initialized_db(db_path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            resultat: dict = {"schema_version": version, "tables": {}}
            for table in _tables(conn):
                resultat["tables"][table] = {
                    "create_sql": _create_sql(conn, table),
                    "colonnes": _colonnes(conn, table),
                    "cles_etrangeres": _cles_etrangeres(conn, table),
                    "index": _index(conn, table),
                    "triggers": _triggers(conn, table),
                }
            return resultat
        finally:
            conn.close()


def _afficher(resultat: dict) -> None:
    print(f"PRAGMA user_version = {resultat['schema_version']} "
          f"(attendu : {_SCHEMA_VERSION})")
    print(f"{len(resultat['tables'])} table(s)\n")
    for nom, table in resultat["tables"].items():
        print(f"── {nom} " + "─" * max(0, 60 - len(nom)))
        for c in table["colonnes"]:
            pk = " PK" if c["pk"] else ""
            nn = " NOT NULL" if c["not_null"] else ""
            defaut = f" DEFAULT {c['defaut']}" if c["defaut"] is not None else ""
            print(f"  {c['nom']:<24} {c['type']:<10}{nn}{defaut}{pk}")
        for fk in table["cles_etrangeres"]:
            print(f"  FK {fk['colonne']} -> {fk['table_cible']}.{fk['colonne_cible']}")
        for i in table["index"]:
            u = "UNIQUE " if i["unique"] else ""
            print(f"  INDEX {u}{i['nom']} ({', '.join(i['colonnes'])})")
        for t in table["triggers"]:
            print(f"  TRIGGER {t['nom']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None,
                        help="Écrit l'introspection complète en JSON dans ce fichier.")
    args = parser.parse_args()

    resultat = introspecter()
    _afficher(resultat)
    if args.json:
        args.json.write_text(json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nÉcrit : {args.json}")


if __name__ == "__main__":
    main()
