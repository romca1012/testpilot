"""RUN DE CONFIRMATION (dépense réelle + instance Odoo épinglée).

Cycle complet, chronométré : spec -> analyse/génération -> gate -> RATIFICATION -> exécution
(+ réparation auto bornée) -> rapport. Sur base propre, module 1 (Demande materiel), instance
`odoo_prod` épinglée par dbfilter.

Répond à : exec 30 est-il réglé (onglet « Ordinateurs ») ? coût réel du cas ? temps du cycle ?
— pour vérifier les 3 critères du §9.

Usage : PYTHONUTF8=1 python scripts/confirmation_run_9.py
"""
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.store.repositories import CostRepo

MODULE_ID = 1
SPEC = Path("specs/demande_materiel.md").read_text(encoding="utf-8")


def _db():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def main() -> None:
    client = TestClient(app)
    t0 = time.perf_counter()

    print("=" * 72)
    print("1. GÉNÉRATION  POST /api/modules/%s/cases  (spec -> analyse -> génération -> gate)" % MODULE_ID)
    r = client.post(f"/api/modules/{MODULE_ID}/cases",
                    json={"spec_content": SPEC, "title": "Demande de matériel",
                          "author": "confirmation-9"})
    if r.status_code != 202:
        print("   ÉCHEC génération:", r.status_code, r.text[:400]); return
    job = client.get(f"/api/modules/jobs/{r.json()['job_id']}").json()
    if job["status"] != "done":
        print("   ÉCHEC job:", job.get("error", "")[:600]); return
    case_id = job["case_id"]
    t_gen = time.perf_counter()
    print(f"   case_id = {case_id} | généré en {t_gen - t0:.1f} s")

    print("\n2. RATIFICATION  POST /api/cases/%s/review  (relecture humaine simulée, budget 2)" % case_id)
    rv = client.post(f"/api/cases/{case_id}/review",
                     json={"approved": True, "reviewer": "confirmation-9",
                           "comment": "ratification run de confirmation §9", "repair_budget": 2})
    print("   gate.allowed :", rv.json()["gate"]["allowed"], "| statut :", rv.json()["validation_status"])

    print("\n3. EXÉCUTION  POST /api/cases/%s/runs  (run réel + réparation auto — peut prendre plusieurs min)" % case_id)
    t_run0 = time.perf_counter()
    rr = client.post(f"/api/cases/{case_id}/runs")
    print("   HTTP :", rr.status_code, "| execution_id initial :", rr.json().get("execution_id"))
    t1 = time.perf_counter()

    # ---- Lecture des faits en base ----
    conn = _db()
    execs = conn.execute(
        "SELECT id, version_id, execution_status, functional_status, scenarios_total,"
        " scenarios_passed, scenarios_failed, duration_seconds, iterations"
        " FROM execution WHERE test_case_id=? ORDER BY id", (case_id,)).fetchall()
    case = conn.execute("SELECT validation_status, current_version_id FROM test_case WHERE id=?",
                        (case_id,)).fetchone()

    print("\n" + "=" * 72)
    print("VERDICT")
    print(f"   statut de validation du cas : {case['validation_status']}")
    print(f"   exécutions ({len(execs)}) :")
    ordinateurs_ko = False
    for e in execs:
        print(f"     exec {e['id']} (v{e['version_id']}) : {e['execution_status']} / "
              f"{e['functional_status']} | {e['scenarios_passed']}/{e['scenarios_total']} scén. "
              f"| {e['duration_seconds'] or 0:.0f}s")
        srs = conn.execute(
            "SELECT scenario_name, execution_status, functional_status, failure_type, error_summary"
            " FROM scenario_result WHERE execution_id=? ORDER BY id", (e["id"],)).fetchall()
        for s in srs:
            tag = f"{s['execution_status']}/{s['functional_status']}"
            err = (s["error_summary"] or "").replace("\n", " ")[:120]
            print(f"        - {s['scenario_name'][:42]:42} {tag:28} {s['failure_type'] or ''}")
            if err:
                print(f"          err: {err}")
            if "Ordinateurs" in err or 'get_by_role("tab"' in err:
                ordinateurs_ko = True

    # ---- exec 30 : réglé ? ----
    print("\n" + "-" * 72)
    print("EXEC 30 (onglet « Ordinateurs » sur /myservices) :")
    if ordinateurs_ko:
        print("   ❌ REPRODUIT — un scénario timeout encore sur l'onglet « Ordinateurs ».")
    else:
        print("   ✅ NON REPRODUIT — aucun scénario ne timeout sur l'onglet « Ordinateurs ».")

    # ---- Coûts ----
    creation = CostRepo(conn).creation_cost_usd(case_id)
    total = CostRepo(conn).total_for_case_usd(case_id)
    ledger = conn.execute(
        "SELECT phase, COUNT(*) n, ROUND(SUM(cost_usd),4) c FROM cost_ledger"
        " WHERE test_case_id=? GROUP BY phase ORDER BY phase", (case_id,)).fetchall()
    conn.close()

    print("\n" + "-" * 72)
    print("COÛT (ledger réel) :")
    for l in ledger:
        print(f"   {l['phase']:12} : {l['n']} appel(s)  ${l['c']}")
    print(f"   CRÉATION (analyse+génération, = KPI §9) : ${creation:.4f}")
    print(f"   TOTAL du cas (création + réparations)    : ${total:.4f}")

    # ---- §9 ----
    seuil = config.BUDGET_PER_CASE_USD
    cycle_s = t1 - t0
    print("\n" + "=" * 72)
    print("CRITÈRES DU §9 :")
    print(f"   1. Temps du cycle          : {cycle_s:.1f} s  ({cycle_s/60:.1f} min)  "
          f"— cible < 5 min : {'✅' if cycle_s < 300 else '❌'}")
    print(f"      (génération {t_gen - t0:.1f}s | exécution {t1 - t_run0:.1f}s)")
    print(f"   2. Coût du cas             : ${total:.4f}  — cible < ${seuil:.2f} (§9) : "
          f"{'✅' if total < seuil else '❌'}")
    print(f"      (création seule = KPI §9 : ${creation:.4f})")
    trad = execs and all(e["execution_status"] for e in execs)
    print(f"   3. Cas « à retester » traité : {'✅ le cas a un verdict' if trad else '❌ resté sans verdict'}")


if __name__ == "__main__":
    main()
