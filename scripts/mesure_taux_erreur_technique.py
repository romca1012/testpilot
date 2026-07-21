"""Mesure du TAUX D'ERREUR TECHNIQUE au premier jet, sur des formulaires variés.

    PYTHONUTF8=1 python scripts/mesure_taux_erreur_technique.py

⚠️ DÉPENSE (~0,11 $/cas × N) et écrit dans la vraie base ; EXÉCUTE réellement contre Odoo. Backup
exigé avant. Budget réparation = 0 : on mesure le PREMIER JET, pas le filet.

La question : sur des formulaires différents, quel pourcentage des tests générés TOURNENT sans
erreur technique (axe exécution) ? C'est le chiffre qui dit si « faire les tests sans erreur
technique » est atteint — et il alimente l'onglet Qualité (les runs y sont consignés).

Les cas créés sont des artefacts de mesure (projet 1) — à arbitrer après lecture du résultat.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from testpilot import config  # noqa: E402
from testpilot.api.app import app  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CostRepo, ExecutionRepo  # noqa: E402

MID = 1
SPECS = sorted(Path("specs/mesure").glob("*.md"))


def main() -> int:
    client = TestClient(app)
    resultats = []

    for spec in SPECS:
        nom = spec.stem
        print(f"\n{'=' * 70}\n{nom}\n{'=' * 70}", flush=True)
        t0 = time.time()

        # Passe 4a → 4b (validation métier sans correction : on mesure la génération, pas l'humain)
        r = client.post(f"/api/modules/{MID}/cases",
                        json={"spec_content": spec.read_text(encoding="utf-8"),
                              "title": f"Mesure {nom}"})
        if r.status_code != 202:
            print(f"  démarrage KO : {r.status_code} {r.text[:150]}", flush=True)
            resultats.append((nom, None, "demarrage_ko"))
            continue
        job_id = r.json()["job_id"]
        job = client.get(f"/api/modules/jobs/{job_id}").json()
        if job["status"] != "awaiting_metier":
            print(f"  passe 4a KO : {job.get('error')!r}", flush=True)
            resultats.append((nom, None, "metier_ko"))
            continue
        client.post(f"/api/modules/jobs/{job_id}/metier", json=job["metier"])
        job = client.get(f"/api/modules/jobs/{job_id}").json()
        if job["status"] != "done":
            print(f"  passe 4b KO : {job.get('error')!r}", flush=True)
            resultats.append((nom, None, "gherkin_ko"))
            continue
        case_id = job["case_id"]

        # Gate, budget réparation 0 (premier jet uniquement), puis RUN réel
        client.post(f"/api/cases/{case_id}/review",
                    json={"approved": True, "reviewer": "mesure", "repair_budget": 0})
        client.post(f"/api/cases/{case_id}/runs")

        conn = get_initialized_db(config.DB_PATH)
        execs = ExecutionRepo(conn).list_for_case(case_id)
        prem = min(execs, key=lambda e: e["id"]) if execs else None
        conn.close()
        if prem is None:
            resultats.append((nom, None, "aucun_run"))
            print("  aucun run", flush=True)
            continue
        es, fs = prem["execution_status"], prem["functional_status"]
        resultats.append((nom, es, fs))
        print(f"  cas {case_id} → {es} / {fs} — {time.time() - t0:.0f}s", flush=True)
        if prem.get("error_message"):
            print(f"    {prem['error_message'][:160]}", flush=True)

    # ── Le verdict ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}\nTAUX D'ERREUR TECHNIQUE AU PREMIER JET\n{'=' * 70}", flush=True)
    tourne = sum(1 for _, es, _ in resultats if es == "success")
    erreur = sum(1 for _, es, _ in resultats if es == "technical_error")
    autre = len(resultats) - tourne - erreur
    for nom, es, fs in resultats:
        marque = "OK " if es == "success" else ("ERR" if es == "technical_error" else "?? ")
        print(f"  [{marque}] {nom:<16} {es or '—'} / {fs or '—'}", flush=True)
    print(f"\n  ONT TOURNÉ (succès technique)  : {tourne}/{len(resultats)}", flush=True)
    print(f"  ERREUR TECHNIQUE               : {erreur}/{len(resultats)}", flush=True)
    if autre:
        print(f"  autre (job échoué, etc.)       : {autre}/{len(resultats)}", flush=True)
    if resultats:
        print(f"  → taux de réussite technique   : {tourne / len(resultats) * 100:.0f} %", flush=True)

    conn = get_initialized_db(config.DB_PATH)
    print(f"\n  (onglet Qualité mis à jour — vérifiable dans l'interface)", flush=True)
    q = ExecutionRepo(conn).quality_summary(project_id=1)
    print(f"  agrégat projet 1 : {q['ran']} ont tourné / {q['total']} au total, "
          f"taux={q['ran_rate'] and round(q['ran_rate']*100)}%", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
