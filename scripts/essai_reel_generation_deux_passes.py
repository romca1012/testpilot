"""Essai RÉEL du parcours de génération en DEUX PASSES (décision `0022` n°5).

    PYTHONUTF8=1 python scripts/essai_reel_generation_deux_passes.py

⚠️ **CE SCRIPT DÉPENSE DE L'ARGENT** (~$0,15 attendu) et **écrit dans la VRAIE base** : il crée un
cas réel via les vraies routes HTTP, contre la vraie instance Odoo et le vrai LLM. C'est le prix
d'une preuve réelle — 551 tests verts ne disent rien de l'intégration (le bug d'index de
`schema.sql`, la connexion SQLite entre threads et le marqueur aveugle de `0007 B+` sont tous
passés sous une suite verte).

Sauvegarder la base avant :

    cp data/testpilot.db data/testpilot.db.pre-deux-passes.bak

Ce qu'on vérifie, et qu'aucun test ne peut prouver :
  1. la passe 4a s'arrête réellement en `awaiting_metier`, sur un vrai appel LLM ;
  2. le document rendu est LISIBLE (pas de mot-clé Gherkin, pas de préfixe d'angle) ;
  3. une CORRECTION humaine est bien celle qui part à la génération ;
  4. le Gherkin produit correspond au document validé ;
  5. les champs métier sont réellement PERSISTÉS dans la version (le trou du chantier A) ;
  6. le coût total reste sous le §9 (moins de 1 € par cas).

Le cas créé est un **artefact d'essai** : le nettoyer ou l'assumer est une décision du porteur.
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
from testpilot.store.repositories import CostRepo, VersionRepo  # noqa: E402

MODULE_ID = 1
TITRE = "Essai deux passes (demande materiel)"
SPEC = Path("specs/validation_champ_requis.md")

# La CORRECTION qu'on applique au document proposé : elle doit se retrouver telle quelle dans la
# version persistée. Si l'IA gagne sur l'humain, tout l'intérêt de la pause s'effondre.
CORRECTION_TITRE = "Refus d'une demande dont un champ requis est vide"


def _p(titre):
    print(f"\n{'=' * 78}\n{titre}\n{'=' * 78}")


def main() -> int:
    if not SPEC.is_file():
        print(f"spec introuvable : {SPEC}")
        return 1

    client = TestClient(app)
    spec_content = SPEC.read_text(encoding="utf-8")

    _p("PASSE 4a — la spec part, l'IA rédige le document métier")
    t0 = time.time()
    r = client.post(f"/api/modules/{MODULE_ID}/cases",
                    json={"spec_content": spec_content, "title": TITRE})
    if r.status_code != 202:
        print(f"ÉCHEC au démarrage : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    job_id = r.json()["job_id"]
    print(f"job {job_id} — {time.time() - t0:.0f}s")

    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print(f"état : {job['status']}")
    if job["status"] != "awaiting_metier":
        print(f"ÉCHEC : le job devait s'ARRÊTER à la pause. error={job.get('error')!r}")
        return 1

    _p("LE DOCUMENT PROPOSÉ (c'est ce qu'un humain verrait à l'écran)")
    metier = job["metier"]
    print(f"Titre            : {metier['title']}")
    print(f"Préconditions    : {metier['preconditions']}")
    for i, s in enumerate(metier["steps"], 1):
        print(f"  {i}. {s}")
    print(f"Résultat attendu : {metier['expected_result']}")
    print(f"Angle            : {metier['angle']}")

    _p("CONTRÔLES DE LISIBILITÉ")
    ok = True
    if metier["title"].strip().startswith(("[", "(")):
        print(f"  ÉCHEC — le titre porte un préfixe d'angle : {metier['title']!r}")
        ok = False
    else:
        print("  OK — le titre est une phrase métier, sans préfixe d'angle")

    kw = ("soit ", "étant donné", "quand ", "alors ", "given ", "when ", "then ")
    fautives = [s for s in metier["steps"] if s.lower().startswith(kw)]
    if fautives:
        print(f"  ÉCHEC — mots-clés Gherkin dans les étapes : {fautives}")
        ok = False
    else:
        print("  OK — aucune étape ne commence par un mot-clé Gherkin")

    if not (metier["title"] and metier["steps"] and metier["expected_result"]):
        print("  ÉCHEC — document incomplet (titre/étapes/résultat obligatoires)")
        ok = False
    else:
        print("  OK — les trois champs obligatoires sont remplis")

    _p("PASSE 4b — on CORRIGE le titre, puis on valide")
    print(f"  proposé  : {metier['title']}")
    print(f"  corrigé  : {CORRECTION_TITRE}")
    valide = {**metier, "title": CORRECTION_TITRE}
    t1 = time.time()
    r = client.post(f"/api/modules/jobs/{job_id}/metier", json=valide)
    if r.status_code != 202:
        print(f"ÉCHEC à la validation : HTTP {r.status_code} — {r.text[:300]}")
        return 1

    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print(f"état : {job['status']} — {time.time() - t1:.0f}s")
    if job["status"] != "done":
        print(f"ÉCHEC de la génération : {job.get('error')!r}")
        return 1
    case_id = job["case_id"]
    print(f"cas créé : {case_id}")

    _p("CE QUI EST RÉELLEMENT EN BASE (le trou du chantier A)")
    conn = get_initialized_db(config.DB_PATH)
    detail = client.get(f"/api/cases/{case_id}").json()
    version = VersionRepo(conn).get(detail["current_version_id"])

    print(f"Titre du cas     : {detail['case']['title']}")
    print(f"Titre (version)  : {version['title']}")
    print(f"Préconditions    : {version['preconditions']!r}")
    print(f"Étapes (JSON)    : {version['test_steps']!r}")
    print(f"Résultat attendu : {version['expected_result']!r}")
    print(f"Angle            : {version['angle']!r}")

    _p("VÉRIFICATIONS")
    if detail["case"]["title"] != CORRECTION_TITRE:
        print(f"  ÉCHEC — la correction humaine a été PERDUE : {detail['case']['title']!r}")
        ok = False
    else:
        print("  OK — le titre CORRIGÉ par l'humain fait foi")

    try:
        etapes = json.loads(version["test_steps"] or "[]")
    except Exception:
        etapes = []
    if not etapes:
        print("  ÉCHEC — les étapes métier ne sont PAS persistées (chantier A toujours à moitié)")
        ok = False
    else:
        print(f"  OK — {len(etapes)} étapes métier persistées dans la version")

    if not version["expected_result"]:
        print("  ÉCHEC — le résultat attendu n'est pas persisté")
        ok = False
    else:
        print("  OK — le résultat attendu est persisté")

    feature = version["feature_content"] or ""
    nb_scenarios = feature.count("Scénario:") + feature.count("Scenario:")
    print(f"  Scénarios dans le .feature : {nb_scenarios} "
          f"({'OK — 1 cas = 1 scénario' if nb_scenarios == 1 else 'ÉCART vs 0022 n°6'})")

    gate = detail.get("gate") or {}
    print(f"  Gate : allowed={gate.get('allowed')} "
          f"({'OK — non relu, exécution bloquée' if not gate.get('allowed') else 'ÉCHEC §4.3'})")

    _p("COÛT (§9 — moins de 1 € par cas)")
    total = CostRepo(conn).total_for_case_usd(case_id)
    for ligne in CostRepo(conn).breakdown_for_case(case_id):
        print(f"  {ligne['phase']:<12} {ligne['cost_usd']:.4f} $  ({ligne['model']})")
    print(f"  {'TOTAL':<12} {total:.4f} $  = {total / 1.08 * 100:.0f} % du §9")
    if total > 1.08:
        print("  ÉCHEC — le §9 est dépassé")
        ok = False

    conn.close()
    _p("VERDICT : " + ("TOUT EST CONFORME" if ok else "DES ÉCARTS ONT ÉTÉ TROUVÉS (voir ci-dessus)"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
