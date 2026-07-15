"""Run réel : ajout d'un cas par SPEC dans un module (0006) + mesure de la réutilisation
des steps partagés (0003). Passe par la VRAIE route HTTP et la vraie base.

Usage : PYTHONUTF8=1 python scripts/run_reel_0003_0006.py
"""

from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.generation import steps_library

MODULE_ID = 1
SPEC = Path("specs/validation_champ_requis.md").read_text(encoding="utf-8")


def main() -> None:
    client = TestClient(app)

    print("=" * 70)
    print("1. POST /api/modules/%s/cases  (spec -> analyse -> generation -> gate)" % MODULE_ID)
    resp = client.post(f"/api/modules/{MODULE_ID}/cases",
                       json={"spec_content": SPEC, "title": "Validation champ requis",
                             "author": "run-reel"})
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ECHEC :", resp.text[:400])
        return
    job_id = resp.json()["job_id"]

    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print("   job  :", job["status"], "| case_id =", job["case_id"])
    if job["status"] != "done":
        print("   ERREUR :", job["error"][:600])
        return

    case_id = job["case_id"]

    print()
    print("=" * 70)
    print("2. Le cas est-il bien range dans le module, et derriere le gate ?")
    detail = client.get(f"/api/cases/{case_id}").json()
    print("   projet / module :", detail["project"]["name"], "/", detail["module"]["name"])
    print("   validation      :", detail["case"]["validation_status"])
    print("   gate.allowed    :", detail["gate"]["allowed"], "(doit etre False : non relu)")
    print("   versions        :", len(detail["versions"]))

    version = detail["versions"][-1]
    feature = version["feature_content"]
    steps = version["steps_content"]

    print()
    print("=" * 70)
    print("3. MESURE 0003 — reutilisation du catalogue partage")
    catalogue = {s.label for s in steps_library.catalogue()}
    print("   steps partages disponibles :", len(catalogue))

    # Un step partage est "reutilise" si son libelle (hors placeholders) apparait dans le .feature.
    import re

    def to_regex(label: str) -> str:
        parts = [re.escape(p) for p in re.split(r"\{[^}]*\}", label)]
        return ".*?".join(parts)

    reused = sorted(l for l in catalogue if re.search(to_regex(l), feature))
    print("   steps partages REUTILISES  :", len(reused))
    for label in reused:
        print("      +", label[:88])

    declared = steps_library.extract_steps(steps)
    print("   steps CUSTOM ecrits        :", len(declared))
    for s in declared:
        print("      -", s.label[:88])

    counting = [l for l in reused if "nombre d" in l or "nombre total" in l]
    print()
    print("   >> step de COMPTAGE partage reutilise ?", "OUI" if counting else "NON")

    print()
    print("=" * 70)
    print("4. Garde-fou transport (0003-B) — le code genere contient-il du HTTP brut ?")
    for bad in ("import requests", "urllib", "httpx", "/web/dataset"):
        print(f"   {bad:16} present ? {bad in steps}")

    print()
    print("=" * 70)
    print("5. Gherkin genere")
    print(feature)


if __name__ == "__main__":
    main()
