"""Confirmation par EXÉCUTION RÉELLE de l'écart « sémantique des paramètres de steps ».

Hypothèse à prouver (rapport de continuité §6) : l'agent réutilise le bon step partagé
mais lui passe le LIBELLÉ HUMAIN (« Raison de la demande ») là où le helper attend le
NOM TECHNIQUE du champ HTML (`_base_helpers.fill_field` sélectionne sur `[name="…"]`).
Attendu : TimeoutError → ui_timeout → wrong_field_name → « Champ/sélecteur introuvable »
→ test_a_reparer.

⚠️ Ce script APPROUVE délibérément la version 2 au gate. Ce n'est PAS une validation de
complaisance : c'est un geste de test assumé, seul moyen d'ouvrir le gate pour exécuter
un cas dont on sait qu'il est cassé, afin de prouver le diagnostic par un run plutôt que
par la seule lecture du helper (méthode §8.5 : mesurer plutôt que supposer). La trace en
base le dit explicitement dans le commentaire de relecture.

Base sauvegardée : data/testpilot.db.pre-confirmation-ecart.bak
Usage : PYTHONUTF8=1 python scripts/confirm_ecart_parametres_steps.py
"""

from fastapi.testclient import TestClient

from testpilot.api.app import app

CASE_ID = 2
REVIEW_COMMENT = (
    "Approbation DÉLIBÉRÉE à fin de test — PAS une validation de complaisance. "
    "Version connue comme cassée (libellé humain passé à un step qui attend le nom "
    "technique du champ). Le gate est ouvert uniquement pour prouver l'écart par une "
    "exécution réelle. Voir docs/CONTINUITE.md §6."
)


def main() -> None:
    client = TestClient(app)

    print("=" * 72)
    print("0. État AVANT — le gate doit être fermé")
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    print("   cas          :", detail["case"]["title"])
    print("   gate.allowed :", detail["gate"]["allowed"], "| raison :", detail["gate"]["reason"])

    print()
    print("=" * 72)
    print("1. POST /api/cases/%s/review  (approbation délibérée, geste de test)" % CASE_ID)
    resp = client.post(f"/api/cases/{CASE_ID}/review",
                       json={"approved": True, "reviewer": "confirmation-ecart",
                             "comment": REVIEW_COMMENT})
    print("   HTTP :", resp.status_code)
    if resp.status_code != 200:
        print("   ÉCHEC :", resp.text[:400])
        return
    body = resp.json()
    print("   décision     :", body["decision"])
    print("   gate.allowed :", body["gate"]["allowed"], "(doit être True : gate ouvert)")

    print()
    print("=" * 72)
    print("2. POST /api/cases/%s/runs  (exécution réelle contre Odoo)" % CASE_ID)
    resp = client.post(f"/api/cases/{CASE_ID}/runs")
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ÉCHEC :", resp.text[:400])
        return
    execution_id = resp.json()["execution_id"]
    print("   execution_id :", execution_id, "— run terminé (TestClient exécute la tâche de fond)")

    print()
    print("=" * 72)
    print("3. VERDICT — les 2 axes (invariant §4.1 : ils ne fusionnent jamais)")
    ex = client.get(f"/api/executions/{execution_id}").json()
    print("   execution_status  :", ex.get("execution_status"))
    print("   functional_status :", ex.get("functional_status"))
    print("   scénarios         : %s total / %s ok / %s ko"
          % (ex.get("scenarios_total"), ex.get("scenarios_passed"), ex.get("scenarios_failed")))
    print("   durée (s)         :", ex.get("duration_seconds"))
    print("   coût (USD)        :", ex.get("cost_usd"))

    print()
    print("=" * 72)
    print("4. CLASSIFICATION par scénario — l'écart est-il vu comme attendu ?")
    for s in ex.get("scenarios", []):
        print("   —", s["scenario_name"][:70])
        print("      exécution   :", s["execution_status"], "| fonctionnel :", s["functional_status"])
        print("      failure_type:", s.get("failure_type") or "—")
        print("      cause       :", s.get("cause_category") or "—")
        print("      résumé      :", (s.get("error_summary") or "—")[:200])

    print()
    print("=" * 72)
    print("5. PREUVE — le sélecteur fautif apparaît-il dans les erreurs ?")
    blob = " ".join((s.get("error_summary") or "") for s in ex.get("scenarios", []))
    for needle in ('[name="Raison de la demande"]', "Raison de la demande", "Timeout"):
        print(f"   {needle!r:36} présent ? {needle in blob}")

    print()
    print("   Rapport JSON :", ex.get("report_json_path") or "—")
    print("   Rapport HTML :", ex.get("report_html_path") or "—")


if __name__ == "__main__":
    main()
