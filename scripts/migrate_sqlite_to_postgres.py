"""Migration sûre des données TestPilot SQLite vers PostgreSQL.

Le fichier source n'est jamais modifié : SQLite produit d'abord un snapshot cohérent via son API
de sauvegarde. La destination doit être vide et déjà migrée par Alembic. Toute la copie se fait
dans une transaction PostgreSQL unique, puis les comptes et empreintes sont comparés avant commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Integer, create_engine, func, select, text

from testpilot.store import schema_sa
from testpilot.store.db import get_initialized_db
from testpilot.store.portable_connection import ALEMBIC_HEAD


def _snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lecture = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    copie = sqlite3.connect(destination)
    try:
        lecture.backup(copie)
    finally:
        copie.close()
        lecture.close()


def _normaliser(valeur):
    if isinstance(valeur, bytes):
        return {"__bytes__": valeur.hex()}
    return valeur


def _empreinte(lignes: list[dict], colonnes: list[str]) -> str:
    h = hashlib.sha256()
    for ligne in lignes:
        payload = [_normaliser(ligne.get(c)) for c in colonnes]
        h.update(json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                            default=str).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _lignes_sqlite(conn: sqlite3.Connection, table) -> list[dict]:
    colonnes = [c.name for c in table.columns]
    ordre = [c.name for c in table.primary_key.columns] or colonnes
    sql = (f'SELECT {", ".join(f"\"{c}\"" for c in colonnes)} '
           f'FROM "{table.name}" ORDER BY {", ".join(f"\"{c}\"" for c in ordre)}')
    return [dict(r) for r in conn.execute(sql)]


def migrer(source: Path, url_postgres: str, snapshot_dir: Path) -> dict:
    if not source.is_file():
        raise RuntimeError(f"base SQLite introuvable : {source}")
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snapshot = snapshot_dir / f"{source.name}.snapshot-migration-{horodatage}"
    _snapshot(source, snapshot)

    # Les migrations SQLite éventuelles s'appliquent au SNAPSHOT, jamais à la source.
    sqlite_conn = get_initialized_db(snapshot)
    sqlite_conn.row_factory = sqlite3.Row
    moteur = create_engine(url_postgres, future=True)
    rapport = {"snapshot": str(snapshot), "tables": {}, "alembic_head": ALEMBIC_HEAD}
    try:
        with moteur.begin() as pg:
            version = pg.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if version != ALEMBIC_HEAD:
                raise RuntimeError(
                    f"PostgreSQL au schéma {version}, attendu {ALEMBIC_HEAD}; lancez Alembic")

            non_vides = []
            for table in schema_sa.metadata.sorted_tables:
                if pg.execute(select(func.count()).select_from(table)).scalar_one():
                    non_vides.append(table.name)
            if non_vides:
                raise RuntimeError(
                    "destination non vide, migration refusée : " + ", ".join(non_vides))

            for table in schema_sa.metadata.sorted_tables:
                colonnes = [c.name for c in table.columns]
                source_rows = _lignes_sqlite(sqlite_conn, table)
                if source_rows:
                    pg.execute(table.insert(), source_rows)
                ordre = list(table.primary_key.columns) or list(table.columns)
                destination_rows = [dict(r) for r in pg.execute(
                    select(table).order_by(*ordre)).mappings()]
                source_hash = _empreinte(source_rows, colonnes)
                destination_hash = _empreinte(destination_rows, colonnes)
                if len(source_rows) != len(destination_rows) or source_hash != destination_hash:
                    raise RuntimeError(f"contrôle d'intégrité échoué pour {table.name}")
                rapport["tables"][table.name] = {
                    "lignes": len(source_rows), "sha256": source_hash,
                }

            # Les INSERT explicites ont conservé les ids : replacer chaque séquence après le max.
            for table in schema_sa.metadata.sorted_tables:
                if ("id" not in table.c or not table.c.id.primary_key
                        or not isinstance(table.c.id.type, Integer)):
                    continue
                nom = table.name.replace('"', '""')
                pg.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{nom}', 'id'), "
                    f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM \"{nom}\""))
    except Exception:
        # Le snapshot est volontairement conservé : il constitue la preuve et le filet de reprise.
        raise
    finally:
        sqlite_conn.close()
        moteur.dispose()
    return rapport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("data/migration-snapshots"))
    parser.add_argument("--report", type=Path, default=Path("data/migration-report.json"))
    args = parser.parse_args(argv)
    try:
        rapport = migrer(args.source, args.target_url, args.snapshot_dir)
    except Exception as exc:
        print(f"MIGRATION REFUSÉE : {exc}", file=sys.stderr)
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(t["lignes"] for t in rapport["tables"].values())
    print(f"Migration validée : {total} lignes, rapport {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
