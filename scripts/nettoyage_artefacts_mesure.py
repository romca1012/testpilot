"""Retire les cas 7 et 8 — artefacts de la mesure de coût du chemin écran (2026-07-17).

    PYTHONUTF8=1 python scripts/nettoyage_artefacts_mesure.py [--dry-run]

**Décision du porteur, explicite.** Ce sont des cas générés pour MESURER le coût réel du chemin
écran, pas des cas du référentiel : les garder fausserait toute analyse future portant sur les
cas de test réels (couverture, statuts, coûts par cas). C'est la leçon du ménage du 2026-07-16 —
les scripts de preuve écrivent dans la vraie base, c'est ce qui rend leurs preuves réelles, et ça
laisse des déchets.

⚠️ **L'exception étroite du §2.10, et elle est remplie ici.** La règle est « on n'efface JAMAIS un
run — on annote ». Ces cas n'ont **aucun run** (0 exécution, 0 relecture, `never_executed`,
`author='mesure-cout'`) : il n'y a aucune trace d'exécution à préserver. Et la suppression est
**décidée explicitement par le porteur**, jamais par défaut.

⚠️ **Les lignes de `cost_ledger` partent avec.** C'était le point délicat : ce sont les seules
mesures brutes du chemin écran. Elles partent quand même, parce qu'un coût rattaché à un cas
supprimé est un **mensonge** (« le cas 7 a coûté $0,12 » alors que le cas 7 n'existe plus) — et
parce que le chiffre, lui, **survit là où il compte** :
  • `tests/test_repair_cost_cap.py` — `GENERATION_ECRAN = 0.1050`, `ANALYSE_ECRAN = 0.0157`,
    **vérifiés par des tests** (donc gardés contre la dérive) ;
  • `src/testpilot/config.py` — le calibrage et son calcul ;
  • `docs/CONTINUITE.md` — le tableau des mesures ;
  • `scripts/mesure_generation_chemin_ecran.py` — **reproductible** (~$0,12).

Backups pris avant : `data/testpilot.db.pre-migration12.bak`, `…pre-mesure-generation.bak`.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402

# Les artefacts, nommément. Pas de suppression « par critère » : un critère trop large
# emporterait un vrai cas. On nomme ce qu'on retire.
ARTEFACTS = (7, 8)
AUTEUR_ATTENDU = "mesure-cout"


def main() -> None:
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    print("=" * 74)
    print("NETTOYAGE des artefacts de mesure" + ("  [DRY-RUN]" if dry else ""))
    print("=" * 74)

    for cid in ARTEFACTS:
        row = conn.execute("SELECT id, title, author, validation_status FROM test_case WHERE id=?",
                           (cid,)).fetchone()
        if row is None:
            print(f"  cas {cid} : déjà absent — rien à faire")
            continue

        # ⚠️ GARDE-FOU : on refuse de supprimer autre chose qu'un artefact. Un id est un chiffre ;
        # une base restaurée depuis un backup pourrait le réattribuer à un VRAI cas. On vérifie
        # donc l'identité, pas seulement le numéro.
        runs = conn.execute("SELECT COUNT(*) FROM execution WHERE test_case_id=?", (cid,)).fetchone()[0]
        if row["author"] != AUTEUR_ATTENDU or runs:
            print(f"  ⛔ cas {cid} « {row['title']} » : auteur={row['author']!r}, {runs} run(s) — "
                  f"CE N'EST PAS UN ARTEFACT. Abandon, rien n'est supprimé.")
            conn.close()
            sys.exit(1)

        couts = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(cost_usd),0) t FROM cost_ledger"
                             " WHERE test_case_id=?", (cid,)).fetchone()
        versions = conn.execute("SELECT COUNT(*) FROM test_case_version WHERE test_case_id=?",
                                (cid,)).fetchone()[0]
        print(f"\n  cas {cid} « {row['title']} »")
        print(f"    auteur           : {row['author']}  ({row['validation_status']}, {runs} run)")
        print(f"    versions         : {versions}")
        print(f"    lignes de coût   : {couts['n']}  (${couts['t']:.4f})")

        if dry:
            print("    → [dry-run] non supprimé")
            continue

        conn.execute("DELETE FROM cost_ledger WHERE test_case_id=?", (cid,))
        conn.execute("DELETE FROM test_case_version WHERE test_case_id=?", (cid,))
        conn.execute("DELETE FROM test_case WHERE id=?", (cid,))
        conn.commit()
        print("    → SUPPRIMÉ (cas + versions + lignes de coût)")

    print("\n" + "-" * 74)
    print("Référentiel après nettoyage :")
    for r in conn.execute("SELECT id, title, validation_status FROM test_case ORDER BY id"):
        print(f"  cas {r['id']:<3} {r['title']:<32} {r['validation_status']}")

    print("\nLedger après nettoyage :")
    for r in conn.execute("SELECT id, test_case_id, phase, cost_usd FROM cost_ledger ORDER BY id"):
        print(f"  #{r['id']:<3} cas {str(r['test_case_id'] or '?'):<3} {r['phase']:<11} "
              f"${r['cost_usd']:.4f}")

    conn.close()


if __name__ == "__main__":
    main()
