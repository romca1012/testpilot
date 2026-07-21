"""Essai RÉEL du parcours COMPLET, depuis un projet neuf.

    PYTHONUTF8=1 python scripts/essai_reel_parcours_complet.py

⚠️ **DÉPENSE ~$0,15**, **écrit dans la VRAIE base**, et **explore réellement l'application**
(crawl Playwright de plusieurs minutes). Sauvegarder avant :

    cp data/testpilot.db data/testpilot.db.pre-parcours.bak

Il rejoue le flux produit dans l'ordre voulu par le porteur :

    1. créer un projet + sa connexion
    2. EXPLORER l'application → cartographie propre au projet
    3. créer un module (le trou comblé : un projet neuf en est dépourvu)
    4. rédiger un cas → PAUSE métier → validation → Gherkin
    5. vérifier que le Gherkin a UTILISÉ les faits mesurés

Le point 5 est le seul qui compte vraiment : les tests unitaires prouvent qu'on **dit** les faits
à l'agent, jamais qu'il **écoute**. Ce projet a déjà mesuré l'obéissance en réel pour `0012` et
`0007` A1 — c'est la seule méthode qui vaut.
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
from testpilot.store.repositories import CostRepo, VersionRepo  # noqa: E402

NOM_PROJET = "Essai parcours complet"
NOM_MODULE = "Demande de materiel"
SPEC = Path("specs/validation_champ_requis.md")

# La connexion du projet réel, reprise depuis la config (c'est la même instance).
CONNEXION = {
    "base_url": config.ODOO_URL, "database": config.ODOO_DB,
    "username": config.ODOO_USER, "password": config.ODOO_PASSWORD,
}


def _p(titre):
    print(f"\n{'=' * 78}\n{titre}\n{'=' * 78}")


def main() -> int:
    if not SPEC.is_file():
        print(f"spec introuvable : {SPEC}")
        return 1
    client = TestClient(app)
    ok = True

    _p("1. CRÉER LE PROJET ET SA CONNEXION")
    r = client.post("/api/projects", json={"name": NOM_PROJET, "connector_type": "odoo",
                                           **CONNEXION})
    if r.status_code != 201:
        print(f"ÉCHEC : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    pid = r.json()["id"]
    print(f"  projet {pid} — cible : {r.json()['base_url']}")
    print(f"  mot de passe renvoyé par l'API : {'password' in r.json()}  (doit être False)")

    _p("2. EXPLORER L'APPLICATION (crawl réel, aucun LLM — plusieurs minutes)")
    avant = client.get(f"/api/projects/{pid}/exploration").json()
    print(f"  avant : explored={avant['explored']}")
    t0 = time.time()
    r = client.post(f"/api/projects/{pid}/exploration")
    if r.status_code != 202:
        print(f"ÉCHEC : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    etat = client.get(f"/api/projects/{pid}/exploration").json()
    print(f"  après : {etat['pages']} routes · {etat['transitions']} transitions · "
          f"{etat['champs']} champs — {time.time() - t0:.0f}s")
    if etat.get("error"):
        print(f"  ERREUR : {etat['error']}")
    if not etat["explored"]:
        print("  ÉCHEC — aucune cartographie produite")
        return 1
    chemin = domain_model.chemin_du_modele(pid)
    print(f"  rangée sous : {chemin.name}  (existe : {chemin.exists()})")
    if not chemin.exists():
        print("  ÉCHEC — la cartographie n'est pas rangée par projet")
        ok = False

    _p("3. CRÉER LE MODULE (un projet neuf n'en a aucun — le trou comblé)")
    modules = client.get(f"/api/projects/{pid}/modules").json()
    print(f"  modules d'un projet neuf : {len(modules)}  (doit être 0)")
    r = client.post(f"/api/projects/{pid}/modules", json={"name": NOM_MODULE})
    if r.status_code != 201:
        print(f"ÉCHEC : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    mid = r.json()["id"]
    print(f"  module {mid} créé")

    _p("4a. RÉDIGER LE CAS — l'IA écrit le métier, puis S'ARRÊTE")
    t0 = time.time()
    r = client.post(f"/api/modules/{mid}/cases",
                    json={"spec_content": SPEC.read_text(encoding="utf-8"), "title": "Essai"})
    if r.status_code != 202:
        print(f"ÉCHEC : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    job_id = r.json()["job_id"]
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print(f"  état : {job['status']} — {time.time() - t0:.0f}s")
    if job["status"] != "awaiting_metier":
        print(f"  ÉCHEC : le job devait s'arrêter. error={job.get('error')!r}")
        return 1
    metier = job["metier"]
    print(f"  titre : {metier['title']}")
    for i, s in enumerate(metier["steps"], 1):
        print(f"    {i}. {s}")

    _p("4b. VALIDER (sans rien corriger cette fois) → écriture du Gherkin")
    t0 = time.time()
    r = client.post(f"/api/modules/jobs/{job_id}/metier", json=metier)
    if r.status_code != 202:
        print(f"ÉCHEC : HTTP {r.status_code} — {r.text[:300]}")
        return 1
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print(f"  état : {job['status']} — {time.time() - t0:.0f}s")
    if job["status"] != "done":
        print(f"  ÉCHEC : {job.get('error')!r}")
        return 1
    case_id = job["case_id"]
    print(f"  cas {case_id} créé")

    _p("5. LE GHERKIN A-T-IL UTILISÉ LES FAITS MESURÉS ?")
    conn = get_initialized_db(config.DB_PATH)
    detail = client.get(f"/api/cases/{case_id}").json()
    version = VersionRepo(conn).get(detail["current_version_id"])
    feature = version["feature_content"] or ""
    steps = version["steps_content"] or ""
    modele = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
    routes_reelles = set(modele.get("pages") or {})

    print(feature[:900])
    print("\n--- contrôles ---")

    # (a) `0020` : l'onglet ne se clique QUE depuis la route qui le porte.
    onglets = modele.get("onglets_internes") or {}
    hotes = {lib: r for r, libs in onglets.items() for lib in libs}
    cites = [lib for lib in hotes if lib and lib in feature]
    if cites:
        for lib in cites:
            route = hotes[lib]
            print(f"  onglet « {lib} » cité — sa page est `{route}` — présente dans le test : "
                  f"{route in feature}")
    else:
        print("  aucun onglet mesuré n'est cité par le test")

    # (b) `0019` : les valeurs de <select> ne s'inventent pas.
    selects = [(r, c) for r, i in (modele.get("pages") or {}).items()
               for c in (i.get("champs") or []) if c.get("tag") == "select" and c.get("options")]
    verifs = 0
    for route, ch in selects:
        if f'"{ch["name"]}"' not in steps and f'"{ch["name"]}"' not in feature:
            continue
        valides = {v for v, _ in ch["options"]}
        utilisees = {v for v in valides if f'"{v}"' in feature or f'"{v}"' in steps}
        verifs += 1
        print(f"  select `{ch['name']}` utilisé — valeurs réelles employées : "
              f"{sorted(utilisees) or 'AUCUNE (valeur inventée ?)'}")
    if not verifs:
        print("  aucun <select> mesuré n'est sollicité par le test")

    # (c) aucune route inventée
    import re
    citees = set(re.findall(r'"(/[a-zA-Z0-9_\-/{}]+)"', feature + steps))
    def connue(u):
        return any(u == r or re.fullmatch(r.replace("{id}", r"[^/]+"), u) for r in routes_reelles)
    inventees = sorted(u for u in citees if not connue(u))
    if inventees:
        print(f"  ⚠️ routes citées ABSENTES de la mesure : {inventees}")
    else:
        print(f"  OK — les {len(citees)} routes citées existent toutes dans la mesure")

    gate = detail.get("gate") or {}
    print(f"  gate : allowed={gate.get('allowed')}  (doit être False — non relu)")

    _p("COÛT (§9 — moins de 1 € par cas)")
    total = CostRepo(conn).total_for_case_usd(case_id)
    for ligne in CostRepo(conn).breakdown_for_case(case_id):
        print(f"  {ligne['phase']:<12} {ligne['cost_usd']:.4f} $  ({ligne['model']})")
    print(f"  {'TOTAL':<12} {total:.4f} $ = {total / 1.08 * 100:.0f} % du §9")
    conn.close()

    _p(f"Projet {pid} · module {mid} · cas {case_id} — artefacts d'essai à arbitrer")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
