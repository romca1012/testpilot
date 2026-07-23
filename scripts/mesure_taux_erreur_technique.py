"""Mesure du TAUX D'ERREUR TECHNIQUE au premier jet, sur des formulaires variés.

    PYTHONUTF8=1 python scripts/mesure_taux_erreur_technique.py

⚠️ DÉPENSE (~0,11 $/cas × N) et écrit dans la vraie base ; EXÉCUTE réellement contre Odoo. Backup
exigé avant. Budget réparation = 0 : on mesure le PREMIER JET, pas le filet.

La question : sur des formulaires différents, quel pourcentage des tests générés TOURNENT sans
erreur technique (axe exécution) ? C'est le chiffre qui dit si « faire les tests sans erreur
technique » est atteint — et il alimente l'onglet Qualité (les runs y sont consignés).

Les cas créés sont des artefacts de mesure (projet 1) — à arbitrer après lecture du résultat.
"""

import json
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
# Les cas créés par la mesure précédente, pour pouvoir REJOUER le banc.
ARTEFACTS = Path("specs/mesure/.artefacts.json")


def _nettoyer_mesure_precedente(client) -> None:
    """Supprime les cas créés par la mesure PRÉCÉDENTE.

    ⚠️ Sans ça, le banc n'est **pas rejouable** : l'IA regénère les mêmes titres métier, et
    l'unicité par spécification (§2.9) fait échouer la persistance — la mesure s'arrête sur une
    erreur qui n'a rien à voir avec ce qu'elle mesure. Or un banc qu'on ne peut pas rejouer ne
    sert à rien pour suivre une évolution.

    On ne supprime QUE ce que la mesure a créé (ids tracés dans `.artefacts.json`) — jamais un
    balayage par titre, qui emporterait des cas légitimes du référentiel.
    """
    if not ARTEFACTS.exists():
        return
    try:
        ids = json.loads(ARTEFACTS.read_text(encoding="utf-8"))
    except Exception:
        return
    supprimes = 0
    for cid in ids:
        if client.delete(f"/api/cases/{cid}").status_code == 204:
            supprimes += 1
    print(f"  nettoyage : {supprimes}/{len(ids)} cas de la mesure précédente supprimés", flush=True)


def _raison_de_l_echec(conn, execution_id: int) -> str:
    """La RAISON de l'échec, là où elle vit réellement.

    ⚠️ Le banc lisait `execution.error_message` — **vide pour un échec fonctionnel** : le détail
    (message, cause, step fautif) est porté par `scenario_result`. Le banc n'a donc jamais montré
    *pourquoi* un scénario échouait ; il fallait aller le chercher en base à la main après coup.

    C'est le même motif que celui qu'on traque partout ailleurs : **la donnée existait, personne
    ne la transmettait**. Un instrument de mesure qui tait la cause oblige à re-diagnostiquer à
    chaque campagne ce qu'il savait déjà.
    """
    lignes = conn.execute(
        "SELECT error_summary FROM scenario_result"
        " WHERE execution_id=? AND functional_status <> 'conforme'", (execution_id,)).fetchall()
    for ligne in lignes:
        texte = " ".join((ligne["error_summary"] or "").split())
        if texte:
            return texte[:300]
    return ""


def main() -> int:
    client = TestClient(app)
    resultats = []
    crees: list[int] = []

    print("=" * 70, flush=True)
    print("NETTOYAGE DU BANC (mesure précédente)", flush=True)
    print("=" * 70, flush=True)
    _nettoyer_mesure_precedente(client)

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
        crees.append(case_id)

        # Gate, budget réparation 0 (premier jet uniquement), puis RUN réel
        client.post(f"/api/cases/{case_id}/review",
                    json={"approved": True, "reviewer": "mesure", "repair_budget": 0})
        client.post(f"/api/cases/{case_id}/runs")

        conn = get_initialized_db(config.DB_PATH)
        execs = ExecutionRepo(conn).list_for_case(case_id)
        prem = min(execs, key=lambda e: e["id"]) if execs else None
        raison = _raison_de_l_echec(conn, prem["id"]) if prem else ""
        conn.close()
        if prem is None:
            resultats.append((nom, None, "aucun_run"))
            print("  aucun run", flush=True)
            continue
        es, fs = prem["execution_status"], prem["functional_status"]
        resultats.append((nom, es, fs, raison))
        print(f"  cas {case_id} → {es} / {fs} — {time.time() - t0:.0f}s", flush=True)
        if raison:
            print(f"    {raison}", flush=True)

    # Trace des cas créés : la PROCHAINE mesure les supprimera (banc rejouable).
    ARTEFACTS.write_text(json.dumps(crees), encoding="utf-8")

    # ── Le verdict ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}\nTAUX D'ERREUR TECHNIQUE AU PREMIER JET\n{'=' * 70}", flush=True)
    tourne = sum(1 for r in resultats if r[1] == "success")
    erreur = sum(1 for r in resultats if r[1] == "technical_error")
    autre = len(resultats) - tourne - erreur
    for nom, es, fs, *reste in resultats:
        marque = "OK " if es == "success" else ("ERR" if es == "technical_error" else "?? ")
        print(f"  [{marque}] {nom:<20} {es or '—'} / {fs or '—'}", flush=True)
        if reste and reste[0]:
            print(f"          ↳ {reste[0][:200]}", flush=True)
    print(f"\n  ONT TOURNÉ (succès technique)  : {tourne}/{len(resultats)}", flush=True)
    print(f"  ERREUR TECHNIQUE               : {erreur}/{len(resultats)}", flush=True)
    if autre:
        print(f"  autre (job échoué, etc.)       : {autre}/{len(resultats)}", flush=True)
    if resultats:
        print(f"  → taux de réussite technique   : {tourne / len(resultats) * 100:.0f} %", flush=True)

    # ── À QUI la faute ? — désormais lu sur le VERDICT, plus sur le texte ──
    # ⚠️ §2bis 4ᵉ verdict. « notre donnée refusée » a maintenant son propre statut fonctionnel
    # (`donnee_invalide`) : on ne le devine plus dans le message, on le LIT. Un `non_conforme` qui
    # subsiste est donc un constat instruit — soit un refus applicatif expliqué, soit un silence
    # indécidable (que la vérification par l'état, 3a, doit encore lever).
    invalide = sum(1 for r in resultats if len(r) >= 3 and r[2] == "donnee_invalide")
    familles = {"refus applicatif EXPLIQUÉ": 0, "refus SILENCIEUX — indécidable": 0}
    for _, _, fs, *reste in resultats:
        if fs != "non_conforme":
            continue
        raison = (reste[0] if reste else "") or ""
        if "L'APPLICATION A REFUSÉ" in raison:
            familles["refus applicatif EXPLIQUÉ"] += 1
        else:
            familles["refus SILENCIEUX — indécidable"] += 1
    if invalide or any(familles.values()):
        print(f"\n  RÉPARTITION DES VERDICTS NON VERTS :", flush=True)
        if invalide:
            print(f"    {invalide} × donnée du test invalide (à corriger — l'app n'est PAS en "
                  f"cause)", flush=True)
        for libelle, n in familles.items():
            if n:
                print(f"    {n} × {libelle}", flush=True)
    # Cible §2bis : 0 « notre donnée » cachée en non_conforme, 0 silence indécidable.

    conn = get_initialized_db(config.DB_PATH)
    print(f"\n  (onglet Qualité mis à jour — vérifiable dans l'interface)", flush=True)
    q = ExecutionRepo(conn).quality_summary(project_id=1)
    print(f"  agrégat projet 1 : {q['ran']} ont tourné / {q['total']} au total, "
          f"taux={q['ran_rate'] and round(q['ran_rate']*100)}%", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
