"""Le taux d'erreurs TECHNIQUES baisse-t-il grâce aux correctifs du jour ? — mesure réelle.

Question du porteur (2026-07-17) : *« sort-on de la phase "on répare l'outil" pour entrer dans
la phase "l'outil répare/diagnostique l'application" ? »*

Le ratio qui compte n'est PAS « combien de tests passent » — un test rouge peut être une réussite
de l'outil (il a trouvé un vrai défaut). C'est la répartition entre :

- ``technical_error`` → **l'outil n'a pas pu juger**. Il parle de lui-même. C'est le coût.
- ``success/conforme`` ou ``success/non_conforme`` → **l'outil a tranché** sur l'application.
  `non_conforme` est un SUCCÈS de l'outil : il a produit un constat.

Ce script rejoue pour de vrai les cas dont la version courante est approuvée, contre l'Odoo du
projet, boucle de réparation comprise (`0014`), puis compare à l'état d'avant.

⚠️ Écrit en base : chaque rejeu crée une exécution (§2.10 — on ne supprime jamais un run), et la
réparation peut créer des versions. Sauvegarde faite avant (`--backup`).

Usage : PYTHONUTF8=1 python scripts/measure_taux_erreurs_techniques.py [--cases 1,2,6]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from testpilot import config  # noqa: E402
from testpilot.store.db import connect  # noqa: E402

TRANCHE = ("success",)          # l'outil a produit un verdict sur l'application
COUT = ("technical_error", "not_executed")   # l'outil parle de lui-même


def etat_par_cas(conn) -> dict:
    """Dernière exécution de chaque cas — l'état AVANT rejeu."""
    etat = {}
    for row in conn.execute(
            "SELECT e.* FROM execution e JOIN (SELECT test_case_id, MAX(id) m FROM execution"
            " GROUP BY test_case_id) d ON d.m = e.id ORDER BY e.test_case_id"):
        etat[row["test_case_id"]] = dict(row)
    return etat


def _verdict(row) -> str:
    return f"{row['execution_status']}/{row['functional_status']}"


def _derniere_execution(case_id: int) -> int:
    """Dernier run du cas — la réparation (`0014`) en crée un APRÈS celui qu'on a déclenché."""
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute("SELECT MAX(id) m FROM execution WHERE test_case_id=?",
                           (case_id,)).fetchone()
        return int(row["m"])
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="", help="ids séparés par des virgules (défaut : tous)")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    conn = connect(config.DB_PATH)
    cas = [r["id"] for r in conn.execute("SELECT id FROM test_case ORDER BY id")]
    if args.cases:
        cas = [int(x) for x in args.cases.split(",")]
    avant = etat_par_cas(conn)
    conn.close()

    if not args.no_backup:
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        sauvegarde = Path(f"{config.DB_PATH}.pre-mesure-{horodatage}.bak")
        shutil.copy2(config.DB_PATH, sauvegarde)
        print(f"Sauvegarde : {sauvegarde.name}\n")

    from fastapi.testclient import TestClient

    from testpilot.api.app import app
    client = TestClient(app)

    print("=" * 78)
    print("REJEU RÉEL — contre l'Odoo du projet, boucle de réparation comprise")
    print("=" * 78)
    resultats = {}
    for case_id in cas:
        detail = client.get(f"/api/cases/{case_id}").json()
        titre = detail["case"]["title"]
        gate = detail["gate"]
        av = avant.get(case_id)
        print(f"\n— cas {case_id} : {titre[:56]}")
        print(f"  avant : {_verdict(av) if av else 'jamais exécuté'}")
        if not gate["allowed"]:
            # §4.3 : le gate est souverain. On ne l'ouvre PAS pour faire de beaux chiffres.
            print(f"  SAUTÉ — gate fermé : {gate['reason']}")
            continue

        resp = client.post(f"/api/cases/{case_id}/runs")
        if resp.status_code != 202:
            print(f"  ÉCHEC du déclenchement : HTTP {resp.status_code} {resp.text[:200]}")
            continue
        eid = resp.json()["execution_id"]
        # ⚠️ Ne PAS lire l'exécution qu'on vient de déclencher : si la réparation (`0014`) a
        # tourné, elle a rejoué le cas et créé une exécution PLUS RÉCENTE — c'est elle qui porte
        # l'état final. La première version de ce script lisait `eid` et rapportait donc le
        # verdict d'AVANT réparation : elle sous-estimait l'outil (cas 1, mesure du 2026-07-17).
        derniere = _derniere_execution(case_id)
        ex = client.get(f"/api/executions/{derniere}").json()
        resultats[case_id] = ex
        repare = " (après réparation)" if derniere != eid else ""
        print(f"  après : {ex['execution_status']}/{ex['functional_status']}"
              f"  ({ex['scenarios_passed']}/{ex['scenarios_total']} scénarios,"
              f" exec {derniere}{repare}, {ex['duration_seconds']:.0f}s)")
        if ex.get("error_message"):
            print(f"          plantage : {ex['error_message'][:120]}")
        for s in ex.get("scenarios", []):
            if s["execution_status"] != "success" or s["functional_status"] != "conforme":
                print(f"     · {s['scenario_name'][:52]:54} {s['execution_status']}/"
                      f"{s['functional_status']} [{s.get('cause_category') or '—'}]")

    print("\n" + "=" * 78)
    print("RATIO — l'outil tranche-t-il, ou parle-t-il de lui-même ?")
    print("=" * 78)
    for libelle, etat in (("AVANT (dernier run de chaque cas)", avant),
                          ("APRÈS (ce rejeu)", resultats)):
        rows = [r for cid, r in etat.items() if cid in cas]
        if not rows:
            continue
        compte = Counter(r["execution_status"] for r in rows)
        tranche = sum(compte[s] for s in TRANCHE)
        cout = sum(compte[s] for s in COUT)
        total = len(rows)
        print(f"\n  {libelle} — {total} cas")
        print(f"    l'outil a TRANCHÉ (success/*)        : {tranche}/{total}")
        print(f"    l'outil n'a pas pu juger (technique) : {cout}/{total}")
        for r in rows:
            print(f"      cas {r['test_case_id']} : {_verdict(r)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
