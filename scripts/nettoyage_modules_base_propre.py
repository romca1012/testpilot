"""Script ponctuel : nettoyage demande le 2026-08-06.

- Met a la corbeille (reversible) les modules encore vivants (1, 10).
- Supprime definitivement la campagne R16 qui geler des cas de ces modules
  (aucune methode de suppression n'existe sur RunRepo : cascade manuelle,
  meme patron que scripts/nettoyage_ne_garder_que_c13.py, deja supprime).
- Purge definitivement les modules deja a la corbeille (4,5,6,7,8,9) et le
  projet "Projet Mistral" (id 7), via les methodes purger() du depot.

A executer une seule fois. Sauvegarde prealable obligatoire (faite manuellement
avant ce script : data/testpilot.db.avant-nettoyage-modules-<horodatage>).
"""
import sqlite3
from pathlib import Path

from testpilot import config
from testpilot.store.db import connect
from testpilot.store.repositories import ModuleRepo, ProjectRepo

RUN_ID = 16
MODULES_A_CORBEILLE = [1, 10]
MODULES_A_PURGER = [4, 5, 6, 7, 8, 9]
PROJET_A_PURGER = 7
PAR = "nettoyage-2026-08-06"


def purger_campagne(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    ex_ids = [r[0] for r in conn.execute("SELECT id FROM execution WHERE run_id=?", (run_id,))]
    res_ids = [r[0] for r in conn.execute("SELECT id FROM test_result WHERE run_id=?", (run_id,))]

    conn.execute("BEGIN")
    if ex_ids:
        q = ",".join("?" * len(ex_ids))
        conn.execute(f"DELETE FROM scenario_result WHERE execution_id IN ({q})", ex_ids)
        conn.execute(f"DELETE FROM repair_attempt WHERE execution_id IN ({q})", ex_ids)
    if res_ids:
        q = ",".join("?" * len(res_ids))
        conn.execute(f"DELETE FROM result_attachment WHERE result_id IN ({q})", res_ids)
    conn.execute("DELETE FROM test_result WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM run_case_assignment WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM test_run_case WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM execution WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM test_run WHERE id=?", (run_id,))

    problemes = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problemes:
        conn.execute("ROLLBACK")
        raise RuntimeError(f"foreign_key_check a echoue, rollback : {problemes}")
    conn.commit()

    for ex_id in ex_ids:
        dossier = Path(config.DATA_DIR) / "executions" / str(ex_id)
        if dossier.exists():
            import shutil
            shutil.rmtree(dossier)
    for res_id in res_ids:
        dossier = Path(config.DATA_DIR) / "results" / str(res_id)
        if dossier.exists():
            import shutil
            shutil.rmtree(dossier)


def main() -> None:
    conn = connect()

    print("--- 1) Corbeille des modules vivants ---")
    modules = ModuleRepo(conn)
    for mid in MODULES_A_CORBEILLE:
        modules.delete(mid, par=PAR)
        print(f"module {mid} -> corbeille")

    print("--- 2) Suppression definitive de la campagne R16 ---")
    purger_campagne(conn, RUN_ID)
    print(f"campagne {RUN_ID} -> supprimee (cascade verifiee par foreign_key_check)")

    print("--- 3) Purge des modules deja a la corbeille ---")
    for mid in MODULES_A_PURGER:
        modules.purger(mid)
        print(f"module {mid} -> purge")

    print("--- 4) Purge du projet Mistral ---")
    ProjectRepo(conn).purger(PROJET_A_PURGER)
    print(f"projet {PROJET_A_PURGER} -> purge")

    print("--- verification finale ---")
    problemes = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("foreign_key_check:", problemes if problemes else "OK, aucun probleme")

    for table in ("project", "module", "case_group", "test_case", "test_run"):
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        vivants = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE deleted_at IS NULL OR deleted_at=''"
        ).fetchone()[0] if table != "test_run" else total
        print(f"{table}: total={total} vivants={vivants}")


if __name__ == "__main__":
    main()
