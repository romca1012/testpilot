"""PREUVE de la contrainte champs requis (1)+(2) — re-génération sur la MÊME spec que v20.

Double verdict attendu :
  A. le nouveau Gherkin remplit-il les 8 champs requis ET soumet-il explicitement ?
  B. le filet du gate (smoke-check) ne signale-t-il plus rien dessus ?

Le cas 9 (v20, `test_a_reparer`) est CONSERVÉ : la comparaison côte à côte EST la preuve.
Dépense réelle (~$0,16, plafonnée). Usage : PYTHONUTF8=1 python scripts/regeneration_preuve_contrainte.py
"""
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.generation import domain_model, smoke_check
from testpilot.store.repositories import CostRepo

MODULE_ID = 1
SPEC = Path("specs/demande_materiel.md").read_text(encoding="utf-8")
REQUIS = ["name", "types_demandes", "partner_name", "partner_email",
          "destinataire_name", "street", "city", "zip"]


def main() -> None:
    client = TestClient(app)
    t0 = time.perf_counter()

    print("Génération sur la MÊME spec que v20 (cas 9 conservé à côté)…")
    r = client.post(f"/api/modules/{MODULE_ID}/cases",
                    json={"spec_content": SPEC,
                          "title": "Demande de matériel (contrainte champs requis)",
                          "author": "preuve-contrainte"})
    if r.status_code != 202:
        print("ÉCHEC:", r.status_code, r.text[:400]); return
    job = client.get(f"/api/modules/jobs/{r.json()['job_id']}").json()
    if job["status"] != "done":
        print("ÉCHEC job:", (job.get("error") or "")[:600]); return
    case_id = job["case_id"]
    duree = time.perf_counter() - t0
    print(f"case_id = {case_id} | généré en {duree:.1f} s\n")

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    v = conn.execute("SELECT id, feature_content FROM test_case_version WHERE test_case_id=?"
                     " ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
    feature = v["feature_content"]

    # ── A. Le Gherkin remplit-il les requis et soumet-il ? ────────────────────
    print("=" * 68)
    print("A. LE NOUVEAU GHERKIN")
    scenarios = smoke_check._scenarios(feature)
    creations = 0
    for titre, _ligne, lignes in scenarios:
        corps = "\n".join(lignes)
        cree = any(m.search(corps) for m in smoke_check._AFFIRME_CREATION)
        remplis = {(smoke_check._extraire_champ_valeur(l) or (None,))[0] for l in lignes} - {None}
        soumet = any(any(m.search(l) for m in smoke_check._SOUMET)
                     and not smoke_check._ATTENTE_PASSIVE.search(l) for l in lignes)
        marque = "CRÉE" if cree else "     "
        if cree:
            creations += 1
        manquants = sorted(set(REQUIS) - remplis)
        print(f"  [{marque}] {titre[:52]:52} | {len(remplis & set(REQUIS))}/8 requis "
              f"| soumet: {'OUI' if soumet else 'NON'}")
        if cree and manquants:
            print(f"           manquants : {', '.join(manquants)}")
    print(f"  ({len(scenarios)} scénarios, dont {creations} affirmant une création)")

    # ── B. Le filet signale-t-il encore quelque chose ? ───────────────────────
    modele = domain_model.charger_modele("odoo")
    ws = smoke_check.smoke_check(feature, "", modele=modele)
    cibles = [w for w in ws if w["kind"] in ("champs_requis_manquants", "soumission_absente")]

    print("\n" + "=" * 68)
    print("B. LE FILET DU GATE (smoke-check)")
    print(f"  avertissements 'champs requis / soumission' : {len(cibles)}")
    for w in cibles:
        print(f"    - {w['kind']} | {w['step'][:48]}")
        print(f"      {w['message'][:160]}")
    autres = [w for w in ws if w not in cibles]
    if autres:
        print(f"  (autres avertissements, hors périmètre de ce lot : {len(autres)})")
        for w in autres:
            print(f"    - {w['kind']} | {w['step'][:48]}")

    # ── Comparaison avec v20 + coût ──────────────────────────────────────────
    v20 = conn.execute("SELECT feature_content FROM test_case_version WHERE id=20").fetchone()
    ws20 = [w for w in smoke_check.smoke_check(v20["feature_content"], "", modele=modele)
            if w["kind"] in ("champs_requis_manquants", "soumission_absente")]
    cout = CostRepo(conn).creation_cost_usd(case_id)
    conn.close()

    print("\n" + "=" * 68)
    print("VERDICT")
    print(f"  v20 (avant la contrainte) : {len(ws20)} avertissement(s)")
    print(f"  nouveau cas {case_id}          : {len(cibles)} avertissement(s)")
    print(f"  A. Gherkin complet + soumission : {'✅' if not cibles else '❌'}")
    print(f"  B. Filet muet sur le nouveau    : {'✅' if not cibles else '❌'}")
    print(f"  Coût de création : ${cout:.4f} (§9 : ${config.BUDGET_PER_CASE_USD:.2f}) "
          f"{'✅' if cout < config.BUDGET_PER_CASE_USD else '❌'}")
    print(f"  Temps de génération : {duree:.1f} s")


if __name__ == "__main__":
    main()
