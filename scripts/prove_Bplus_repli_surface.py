"""Preuve en conditions réelles des phases B et B+ (décision 0007), par une EXÉCUTION du cas 2.

Deux questions, une seule exécution :

B  — le step UI du cas 2 est paramétré au LIBELLÉ (« Raison de la demande ») là où le helper
     résout par `[name=…]`. Avant B : TimeoutError sur le champ (ui_timeout → wrong_field_name).
     Après B : `resolve_field_name` doit le résoudre vers `name` et laisser le scénario avancer.

B+ — ce repli doit être VISIBLE : capté du log behave → `execution.field_fallbacks` → API →
     bandeau + pastille d'historique. Sans ça, un champ réellement renommé côté Odoo serait
     retrouvé par son libellé et la régression absorbée en silence (verdict 0007 n°2).

⚠️ Le cas 2 a été approuvé DÉLIBÉRÉMENT au gate lors d'une session antérieure (geste de test
assumé, tracé en base) : c'est le seul moyen d'exécuter un cas qu'on sait cassé.

Base sauvegardée : data/testpilot.db.pre-preuve-Bplus.bak
Usage : PYTHONUTF8=1 python scripts/prove_Bplus_repli_surface.py
"""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app

CASE_ID = 2
LIBELLE_FAUTIF = "Raison de la demande"


def main() -> None:
    db = Path(config.DB_PATH)
    if db.exists():
        backup = db.with_suffix(".db.pre-preuve-Bplus.bak")
        shutil.copy2(db, backup)
        print("backup base ->", backup.name)

    client = TestClient(app)

    print("=" * 72)
    print("0. Le cas 2 est-il exécutable (gate ouvert par l'approbation délibérée) ?")
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    print("   cas          :", detail["case"]["title"])
    print("   gate.allowed :", detail["gate"]["allowed"], "|", detail["gate"]["reason"])
    if not detail["gate"]["allowed"]:
        print("   ÉCHEC : gate fermé — voir scripts/confirm_ecart_parametres_steps.py")
        return

    # Le step UI fautif est-il toujours là ? (la preuve n'a de sens que si oui)
    feature = detail["versions"][-1]["feature_content"]
    steps_ui = [ln.strip() for ln in feature.splitlines()
                if "champ" in ln and LIBELLE_FAUTIF in ln]
    print()
    print(f"   Steps UI paramétrés au libellé {LIBELLE_FAUTIF!r} (ce que B doit rattraper) :")
    for ln in steps_ui or ["   (aucun — la preuve serait sans objet)"]:
        print("     ", ln)

    print()
    print("=" * 72)
    print("1. POST /api/cases/%s/runs — exécution réelle contre Odoo" % CASE_ID)
    resp = client.post(f"/api/cases/{CASE_ID}/runs")
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ÉCHEC :", resp.text[:400]); return
    eid = resp.json()["execution_id"]
    ex = client.get(f"/api/executions/{eid}").json()
    print("   execution_id      :", eid)
    print("   execution_status  :", ex.get("execution_status"))
    print("   functional_status :", ex.get("functional_status"))
    print("   scénarios         : %s total / %s ok / %s ko"
          % (ex.get("scenarios_total"), ex.get("scenarios_passed"), ex.get("scenarios_failed")))

    print()
    print("=" * 72)
    print("2. PHASE B — le champ bloque-t-il encore le scénario ?")
    blob = " ".join((s.get("error_summary") or "") for s in ex.get("scenarios", []))
    timeout_sur_le_champ = f'[name=\'{LIBELLE_FAUTIF}\']' in blob or f'[name="{LIBELLE_FAUTIF}"]' in blob
    print(f"   Timeout sur [name='{LIBELLE_FAUTIF}'] : {timeout_sur_le_champ}")
    print("   =>", "ÉCHEC : la barrière de résolution est de retour (régression de B)"
          if timeout_sur_le_champ else
          "OK : plus aucun timeout sur le champ — le repli de B a résolu le libellé.")
    for s in ex.get("scenarios", []):
        print(f"   — {s['scenario_name'][:60]:62} {s['execution_status']}/{s['functional_status']}"
              f"  {s.get('failure_type') or '—'}")

    print()
    print("=" * 72)
    print("3. PHASE B+ — le repli est-il VISIBLE ?")
    fallbacks = ex.get("field_fallbacks") or []
    print("   GET /api/executions/%s → field_fallbacks : %s entrée(s)" % (eid, len(fallbacks)))
    for f in fallbacks:
        print("     •", f)

    # Source de la pastille d'historique (et du bandeau du dernier résultat).
    case = client.get(f"/api/cases/{CASE_ID}").json()
    recent = sorted(case.get("executions", []), key=lambda e: e["id"], reverse=True)
    print()
    print("   Historique du cas (source de la pastille — uniquement sur les runs concernés) :")
    for e in recent[:5]:
        n = len(e.get("field_fallbacks") or [])
        print(f"     exec {e['id']:>3} : {e['execution_status']:<16} pastille={'OUI' if n else 'non'}"
              f" ({n} repli(s))")

    print()
    print("=" * 72)
    print("VERDICT")
    if fallbacks:
        print("   REPLI DÉCLENCHÉ ET SURFACÉ : le libellé a été résolu vers le nom technique,")
        print("   et le run le dit à l'écran au lieu de l'absorber en silence (verdict 0007 n°2).")
    else:
        print("   AUCUN REPLI REMONTÉ. Deux lectures possibles, à départager :")
        print("     - le step UI n'a pas été atteint (scénario coupé en amont) → relire le §2 ;")
        print("     - la capture du marqueur ne fonctionne pas en run réel → B+ est aveugle.")


if __name__ == "__main__":
    main()
