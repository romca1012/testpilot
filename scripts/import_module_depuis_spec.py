"""Importe un module de `testpilot-agent` dans le référentiel, en RÉGÉNÉRANT depuis sa spec.

⚠️ On importe la **spec**, jamais le `.feature` déjà généré. Copier les fichiers bruts créerait un
cas sans spec ni version (le « cas fantôme » que `0006` refuse) et ferait entrer du Gherkin produit
par un agent d'**avant** nos garde-fous (`0003`, `0007` A1, `0008` A). Régénérer donne un cas natif
(spec + version + `origin=ia_generated` + gate) et éprouve le pipeline actuel sur un domaine réel.

INVARIANT : le cas arrive **non relu**. Passer par `POST /api/modules/{id}/cases` produit
`gate.allowed = False` — « déjà généré ailleurs » n'exempte pas du gate (§4.3).

Chaque module de l'ancien projet devient un MODULE du référentiel (rangement métier, `0004`) :
un achat de véhicule n'a rien à faire dans « Demande materiel », et l'exécution groupée
multi-modules a besoin de plusieurs modules pour avoir un sens.

Usage : PYTHONUTF8=1 python scripts/import_module_depuis_spec.py achat_vehicule "Achat véhicule"
"""

import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app

AGENT_SPECS = Path("../testpilot-agent/docs")
PROJECT_ID = 1


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    slug, module_name = sys.argv[1], sys.argv[2]

    spec_path = AGENT_SPECS / f"spec_{slug}.md"
    if not spec_path.is_file():
        print(f"ÉCHEC : spec introuvable — {spec_path}")
        sys.exit(1)
    spec = spec_path.read_text(encoding="utf-8")

    db = Path(config.DB_PATH)
    if db.exists():
        backup = db.with_suffix(f".db.pre-import-{slug}.bak")
        shutil.copy2(db, backup)
        print("backup ->", backup.name)

    client = TestClient(app)

    print("=" * 72)
    print(f"1. Module « {module_name} » (rangement métier, 0004)")
    modules = client.get(f"/api/projects/{PROJECT_ID}/modules").json()
    existant = next((m for m in modules if m["name"] == module_name), None)
    if existant:
        mid = existant["id"]
        print(f"   déjà présent : id={mid}")
    else:
        resp = client.post(f"/api/projects/{PROJECT_ID}/modules",
                           json={"name": module_name, "description": f"Importé de {spec_path.name}"})
        if resp.status_code != 201:
            print("   ÉCHEC :", resp.status_code, resp.text[:300]); sys.exit(1)
        mid = resp.json()["id"]
        print(f"   créé : id={mid}")

    print()
    print("=" * 72)
    print(f"2. Génération depuis la SPEC ({len(spec)} car.) — appel LLM réel, plusieurs minutes")
    resp = client.post(f"/api/modules/{mid}/cases",
                       json={"spec_content": spec, "title": module_name, "author": "import-agent"})
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ÉCHEC :", resp.text[:400]); sys.exit(1)
    job = client.get(f"/api/modules/jobs/{resp.json()['job_id']}").json()
    print("   job  :", job["status"], "| case_id =", job.get("case_id"))
    if job["status"] != "done":
        print("   ERREUR :", (job.get("error") or "")[:800]); sys.exit(1)

    cid = job["case_id"]
    detail = client.get(f"/api/cases/{cid}").json()
    version = detail["versions"][-1]

    print()
    print("=" * 72)
    print("3. Le cas est-il conforme au modèle (0006) ET non relu (§4.3) ?")
    print("   titre            :", detail["case"]["title"])
    print("   module           :", detail["module"]["name"], "| projet :", detail["project"]["name"])
    print("   origin           :", detail["case"]["origin"] if "origin" in detail["case"] else "(n/a)")
    print("   versions         :", len(detail["versions"]))
    print("   validation       :", detail["case"]["validation_status"])
    print("   gate.allowed     :", detail["gate"]["allowed"], "<- DOIT être False (gate obligatoire)")
    print("   gate.reason      :", detail["gate"]["reason"])
    lint = detail["gate"].get("lint_warnings") or []
    print("   lint_warnings    :", len(lint), "(0008 — non bloquant)")
    for w in lint:
        print(f"      - {w['kind']} l.{w['line']} : {w['message'][:70]}")

    print()
    print("=" * 72)
    print("4. Qualité du Gherkin généré")
    feature = version["feature_content"]
    scenarios = [l.strip() for l in feature.splitlines() if l.strip().startswith("Scénario")]
    print(f"   scénarios : {len(scenarios)}")
    for s in scenarios:
        print("      -", s[:78])
    # A1 : les steps UI doivent porter le NOM TECHNIQUE, jamais le libellé humain.
    import re
    champs = re.findall(r'champ "([^"]+)"', feature)
    libelles = [c for c in champs if " " in c or c != c.lower()]
    print(f"   paramètres de champ : {sorted(set(champs))}")
    print(f"   au libellé humain (A1 violé ?) : {sorted(set(libelles)) or 'aucun'}")
    # 0011 : un comptage sans snapshot echouerait desormais — verifions la paire.
    a_snapshot = "est enregistré pour comparaison" in feature
    a_comptage = "n'a pas augmenté" in feature or "augmente de 1" in feature
    print(f"   comptage utilisé : {a_comptage} | snapshot posé : {a_snapshot}"
          + ("  <- OK" if (not a_comptage or a_snapshot) else "  <- ATTENTION : comptage sans snapshot (0011)"))

    print()
    print("=" * 72)
    print(f"IMPORT TERMINÉ — cas {cid} dans le module {mid}. NON RELU : le gate reste à franchir.")


if __name__ == "__main__":
    main()
