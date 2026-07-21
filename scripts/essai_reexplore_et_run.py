"""Ré-exploration (machine réveillée) + génération 2 passes + RUN RÉEL.

    PYTHONUTF8=1 python scripts/essai_reexplore_et_run.py

⚠️ DÉPENSE (~0,11 $ génération + réparations éventuelles ~0,20 $/tentative), écrit dans la VRAIE
base, explore et EXÉCUTE réellement contre Odoo. Backup exigé avant.

But : le précédent essai avait une carto tronquée (machine en veille pendant le crawl) et n'a
jamais lancé le test — la route inventée `/your-ticket-has-been-submitted` restait une hypothèse.
Ici on va au bout : carto propre, cas frais, puis RUN pour voir le verdict réel.

Le cas créé est un artefact d'essai (projet 1, module 1) — à arbitrer.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from testpilot import config  # noqa: E402
from testpilot.api.app import app  # noqa: E402
from testpilot.generation import domain_model  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CostRepo, ExecutionRepo, VersionRepo  # noqa: E402

PID = 1
MID = 1
SPEC = Path("specs/validation_champ_requis.md")
TITRE = "Essai reexplore et run"


def _p(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}", flush=True)


def main() -> int:
    client = TestClient(app)

    _p("1. RÉ-EXPLORER LE PROJET 1 (machine réveillée)")
    t0 = time.time()
    r = client.post(f"/api/projects/{PID}/exploration")
    print(f"  POST → {r.status_code}", flush=True)
    etat = client.get(f"/api/projects/{PID}/exploration").json()
    print(f"  {etat['pages']} routes · {etat['transitions']} transitions · "
          f"{etat['champs']} champs — {time.time() - t0:.0f}s", flush=True)
    if etat.get("error"):
        print(f"  ERREUR : {etat['error']}", flush=True)
    if not etat["explored"]:
        print("  ÉCHEC — pas de carto")
        return 1
    chemin = domain_model.chemin_du_modele(PID)
    print(f"  rangée : {chemin.name}", flush=True)

    _p("2. GÉNÉRER UN CAS FRAIS (2 passes)")
    t0 = time.time()
    r = client.post(f"/api/modules/{MID}/cases",
                    json={"spec_content": SPEC.read_text(encoding="utf-8"), "title": TITRE})
    job_id = r.json()["job_id"]
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    if job["status"] != "awaiting_metier":
        print(f"  ÉCHEC passe 4a : {job.get('error')!r}")
        return 1
    print(f"  4a OK ({time.time() - t0:.0f}s) — validation sans correction", flush=True)
    t0 = time.time()
    client.post(f"/api/modules/jobs/{job_id}/metier", json=job["metier"])
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    if job["status"] != "done":
        print(f"  ÉCHEC passe 4b : {job.get('error')!r}")
        return 1
    case_id = job["case_id"]
    print(f"  4b OK ({time.time() - t0:.0f}s) — cas {case_id}", flush=True)

    # La route inventée est-elle toujours là avec une carto propre ?
    conn = get_initialized_db(config.DB_PATH)
    v = VersionRepo(conn).get(client.get(f"/api/cases/{case_id}").json()["current_version_id"])
    steps = v["steps_content"] or ""
    conn.close()
    inventee = "/your-ticket-has-been-submitted" in steps
    print(f"  route inventée /your-ticket-has-been-submitted encore présente : {inventee}",
          flush=True)

    _p("3. APPROUVER AU GATE (budget réparation = 2) puis LANCER LE RUN RÉEL")
    r = client.post(f"/api/cases/{case_id}/review",
                    json={"approved": True, "reviewer": "essai", "repair_budget": 2})
    print(f"  gate approuvé : {r.status_code}", flush=True)
    t0 = time.time()
    r = client.post(f"/api/cases/{case_id}/runs")
    print(f"  run lancé : {r.status_code} — {r.json()}", flush=True)
    # Le run tourne en tâche de fond ; TestClient l'a exécuté synchroniquement au POST.

    _p("4. VERDICT DU RUN RÉEL")
    conn = get_initialized_db(config.DB_PATH)
    execs = ExecutionRepo(conn).list_for_case(case_id)
    for e in execs:
        print(f"  exécution {e['id']} : {e['execution_status']} / {e['functional_status']} — "
              f"{e['scenarios_passed']}/{e['scenarios_total']} scénarios — "
              f"{e.get('duration_seconds', '?')}s", flush=True)
        if e.get("error_message"):
            print(f"    message : {e['error_message'][:200]}", flush=True)
        for sr in ExecutionRepo(conn).list_scenario_results(e["id"]):
            print(f"      → {sr['scenario_name'][:50]} : {sr['execution_status']}/"
                  f"{sr['functional_status']}  {sr.get('error_summary') or ''}"[:130], flush=True)

    _p("COÛT TOTAL DU CAS")
    total = CostRepo(conn).total_for_case_usd(case_id)
    for l in CostRepo(conn).breakdown_for_case(case_id):
        print(f"  {l['phase']:<12} {l['cost_usd']:.4f} $  ({l['model']})", flush=True)
    print(f"  {'TOTAL':<12} {total:.4f} $ = {total / 1.08 * 100:.0f} % du §9", flush=True)
    conn.close()

    print(f"\nArtefact d'essai : cas {case_id} (projet 1, module 1) — à arbitrer.", flush=True)
    print(f"TEMPS TOTAL run : {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
