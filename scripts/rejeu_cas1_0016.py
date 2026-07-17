"""Rejeu réel du cas 1 — prouver le chemin positif de `0016`, et MESURER le coût du cas.

    PYTHONUTF8=1 python scripts/rejeu_cas1_0016.py

⚠️ **DÉPENSE DE L'ARGENT et écrit dans la VRAIE base.** Sauvegarder avant.

**Chemin : l'ÉCRAN** (`POST /api/cases/1/runs`, la vraie route HTTP, `TestClient` exécutant la
tâche de fond de façon synchrone). C'est le parcours réel d'un utilisateur, et c'est celui qu'on
vient de fiabiliser côté mesure (migration 12 + branchement du ledger). La CLI mesurerait un
chemin que personne n'emprunte.

CE QU'ON PROUVE, EN UN SEUL RUN :

1. **Le chemin positif de `0016`** — une réparation qui rend le test EXÉCUTABLE est adoptée, même
   si le test révèle ensuite un vrai bug applicatif. Le chemin négatif est prouvé depuis
   longtemps ; le positif ne l'a jamais été (3 rejeux, 3 causes distinctes : `404` →
   `TimeoutError` d'auth → step `undefined`).

2. **Le coût RÉEL d'un cas réparé**, mesuré et non extrapolé — le ledger le dira. Le $0,2895 en
   vigueur est **périmé à la baisse** : il a été mesuré avec `dry_runner=None`, donc 2 appels LLM
   par tentative (l'écriture + un tour perdu). Le fix P0 en supprime un sur le chemin heureux.

CE QUI A CHANGÉ DEPUIS LE DERNIER REJEU (et pourquoi celui-ci peut se passer autrement) :
  • **le dry-run est branché** (`3a744a4`) — c'est LA cause du dernier échec : l'agent avait
    supprimé son step d'auth sans toucher au `.feature`, et rien ne le lui a dit. Il reçoit
    désormais la liste des steps `undefined` et corrige dans la MÊME session ;
  • le plafond de coût borne le CAS et non plus l'appel (`edc4002`) ;
  • l'annotation « ne réimplémente jamais l'auth » et la garde détective du rayon d'explosion
    sont en place (`c1ee857`).

⚠️ **Consigne du porteur, tenue** : en cas d'échec, on NE relance PAS à l'aveugle. On documente la
cause et on remonte pour arbitrage avant tout nouveau code.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from testpilot import config  # noqa: E402
from testpilot.api.app import app  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CostRepo  # noqa: E402

CASE_ID = 1


def _etat(conn, titre):
    print(f"\n-- {titre} " + "-" * (70 - len(titre)))
    c = conn.execute(
        "SELECT current_version_id, validation_status, last_execution_status,"
        " last_functional_status FROM test_case WHERE id=?", (CASE_ID,)).fetchone()
    print(f"  version courante  : v{c['current_version_id']}")
    print(f"  validation        : {c['validation_status']}")
    print(f"  derniers statuts  : {c['last_execution_status']} / {c['last_functional_status']}")
    return dict(c)


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    print("=" * 78)
    print("REJEU RÉEL DU CAS 1 — chemin ÉCRAN (POST /api/cases/1/runs)")
    print("=" * 78)

    avant = _etat(conn, "AVANT")
    execs_avant = {r["id"] for r in conn.execute(
        "SELECT id FROM execution WHERE test_case_id=?", (CASE_ID,))}
    cout_avant = CostRepo(conn).total_for_case_usd(CASE_ID)
    print(f"  coût cumulé du cas : ${cout_avant:.4f}")
    conn.close()

    print("\nLancement (peut durer plusieurs minutes : runs réels contre Odoo)...")
    client = TestClient(app)
    resp = client.post(f"/api/cases/{CASE_ID}/runs")
    print("  HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("  ÉCHEC :", resp.text[:400])
        return
    print("  exécution déclenchée :", resp.json())

    conn = get_initialized_db(config.DB_PATH)
    apres = _etat(conn, "APRÈS")

    print("\n-- Exécutions produites par ce rejeu " + "-" * 41)
    nouvelles = [dict(r) for r in conn.execute(
        "SELECT id, version_id, execution_status, functional_status, scenarios_total,"
        " scenarios_passed, scenarios_failed, trigger, error_message FROM execution"
        " WHERE test_case_id=? ORDER BY id", (CASE_ID,)) if r["id"] not in execs_avant]
    for e in nouvelles:
        print(f"  exec {e['id']:<3} v{e['version_id']:<3} "
              f"{e['execution_status']:<16} {e['functional_status']:<12} "
              f"{e['scenarios_passed']}/{e['scenarios_total']} passés  ({e['trigger']})")
        if e["error_message"]:
            print(f"        erreur : {e['error_message'][:150]}")

    print("\n-- Versions créées par la réparation " + "-" * 41)
    versions = [dict(r) for r in conn.execute(
        "SELECT id, version_number, created_by, LENGTH(steps_content) n,"
        " substr(change_summary, 1, 100) resume FROM test_case_version"
        " WHERE test_case_id=? ORDER BY version_number", (CASE_ID,))]
    for v in versions[-3:]:
        print(f"  v{v['version_number']} (id {v['id']}, {v['created_by']}, {v['n']} car.)")
        if v["resume"]:
            print(f"        « {v['resume']} »")

    print("\n-- Diagnostics " + "-" * 63)
    for r in conn.execute(
            "SELECT ra.execution_id, ra.cause_category, ra.defect_origin, ra.confirmation_status,"
            " substr(ra.what_was_tried, 1, 120) t FROM repair_attempt ra"
            " JOIN execution e ON e.id = ra.execution_id WHERE e.test_case_id=?"
            " ORDER BY ra.id DESC LIMIT 3", (CASE_ID,)):
        print(f"  exec {r['execution_id']} : {r['cause_category']} → {r['defect_origin']}"
              f" ({r['confirmation_status']})")
        if r["t"]:
            print(f"        tenté : {r['t']}")

    # ── LE COÛT, mesuré ───────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("COÛT MESURÉ — lu au ledger, pas extrapolé")
    print("=" * 78)
    repo = CostRepo(conn)
    for r in repo.breakdown_for_case(CASE_ID):
        print(f"  {r['phase']:<11} {r['model']:<28} ${r['cost_usd']:.4f}  ({r['calls']} appel(s))")

    # ⚠️ DEUX MÉTRIQUES, DEUX QUESTIONS — arbitrage du porteur (2026-07-17).
    # Ce script comparait `total_for_case_usd` au seuil du §9 et affichait « ⚠️ DÉPASSE » : c'est
    # EXACTEMENT la fausse alarme qu'on a bannie, et je l'avais laissée ici. Le §9 dit « nouveau
    # cas de test » : il mesure une CRÉATION, une fois. Le cas 1 cumule 6 sessions de débogage de
    # l'outil et 10 versions — son total ne se compare à RIEN.
    creation = repo.creation_cost_usd(CASE_ID)
    total = repo.total_for_case_usd(CASE_ID)
    depense = total - cout_avant
    print(f"\n  CRÉATION du cas (§9)  : ${creation:.4f}  = "
          f"{100 * creation / config.BUDGET_PER_CASE_USD:.1f} % du §9  "
          f"[{'OK' if creation <= config.BUDGET_PER_CASE_USD else 'DÉPASSE LE §9'}]")
    print(f"  dépensé par CE rejeu  : ${depense:.4f}")
    print(f"  total vie du cas      : ${total:.4f}   (télémétrie de debug — AUCUN seuil, "
          f"ne pas comparer au §9)")

    reps = [r for r in repo.breakdown_for_case(CASE_ID) if r["phase"] == "repair"]
    if reps:
        n = reps[0]["calls"]
        print(f"\n  Réparations : {n} appel(s), ${reps[0]['cost_usd']:.4f} "
              f"→ ${reps[0]['cost_usd'] / n:.4f}/tentative")
        print(f"  (référence d'avant le fix P0 : $0,2895/tentative, avec un tour LLM perdu)")

    # ── LES VERDICTS : 0018 et 0016 sont DEUX questions distinctes ────────────
    # ⚠️ Ce script les confondait : il titrait « CHEMIN POSITIF DE 0016 » et lisait l'adoption —
    # or depuis `0018` l'adoption a DEUX voies. Un progrès partiel adopté prouve `0018`, PAS
    # `0016`. Les mélanger ferait passer une décision livrée pour un échec, ou l'inverse.
    print("\n" + "=" * 78)
    print("VERDICT 0018 — le PROGRÈS partiel est-il gardé (au lieu de rembobiner) ?")
    print("=" * 78)
    adopte = apres["current_version_id"] != avant["current_version_id"]
    echecs_avant = sum(1 for e in nouvelles[:1] for _ in range(e["scenarios_failed"]))
    dernier = nouvelles[-1] if nouvelles else None
    print(f"  version courante : v{avant['current_version_id']} → v{apres['current_version_id']}"
          f"   {'✔ ADOPTÉE — le progrès est GARDÉ' if adopte else '✘ inchangée — rembobinée'}")
    if nouvelles and dernier:
        print(f"  scénarios passés : {nouvelles[0]['scenarios_passed']}/{nouvelles[0]['scenarios_total']}"
              f" (départ) → {dernier['scenarios_passed']}/{dernier['scenarios_total']} (final)")
    if adopte:
        print("\n  ✅ 0018 PROUVÉE EN RÉEL : la boucle garde un test à moitié réparé au lieu de le")
        print("     jeter. Le prochain rejeu repartira d'ICI, pas de v1 — plus de rachat du même")
        print(f"     travail. Le cas est à '{apres['validation_status']}' : le gate ratifie (§4.3).")

    print("\n" + "=" * 78)
    print("VERDICT 0016 — le test tourne-t-il ENTIÈREMENT (chemin positif) ?")
    print("=" * 78)
    if dernier:
        tourne = dernier["execution_status"] == "success"
        print(f"  dernier run      : {dernier['execution_status']} / "
              f"{dernier['functional_status']}   "
              f"{'✔ LE TEST TOURNE' if tourne else '✘ le test ne tourne pas encore entièrement'}")
    if dernier and dernier["execution_status"] == "success":
        print("\n  ✅ CHEMIN POSITIF PROUVÉ : la réparation rend le test exécutable et elle est")
        print("     adoptée — même si l'axe fonctionnel révèle un vrai bug (c'est le but).")
    else:
        print("\n  ❌ CHEMIN POSITIF NON PROUVÉ — le test ne tourne pas encore entièrement.")
        print("     Cause à documenter. Consigne du porteur : NE PAS relancer à l'aveugle,")
        print("     remonter pour arbitrage avant tout code.")

    conn.close()


if __name__ == "__main__":
    main()
