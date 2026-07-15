"""Preuve de la phase A (décision 0008) : le prompt amélioré (Règle 4 falsifiabilité +
consigne [Limite]) produit-il désormais une assertion [Limite] FALSIFIABLE, au lieu de la
tautologie de l'écart 2 ?

Dispositif : re-génère le MÊME spec (`specs/validation_champ_requis.md`) via la vraie route
HTTP, sur la vraie base, puis extrait le scénario [Limite] et les steps custom pour inspection.
Non déterministe (appel LLM) : on lit le résultat, on ne présume pas (§8.5).

Base sauvegardée : data/testpilot.db.pre-preuve-A.bak
Usage : PYTHONUTF8=1 python scripts/prove_A_falsifiabilite.py
"""

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot.api.app import app

MODULE_ID = 1
SPEC = Path("specs/validation_champ_requis.md").read_text(encoding="utf-8")
TITLE = "Validation champ requis (re-gen preuve A falsifiabilite)"


def _limite_scenario(feature: str) -> str:
    lines = feature.splitlines()
    out, capture = [], False
    for ln in lines:
        if re.match(r"\s*Sc[eé]nario\s*:", ln):
            capture = "Limite" in ln
        if capture:
            out.append(ln)
    return "\n".join(out)


def _functions_with_asserts(steps: str) -> None:
    """Pour chaque fonction de step, dit si elle contient un assert / raise (Règle 4)."""
    try:
        tree = ast.parse(steps)
    except SyntaxError as exc:
        print("   (steps non parsables :", exc, ")")
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,)):
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
            deco = ""
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant):
                    deco = str(d.args[0].value)[:60]
            flag = "OK" if (asserts or raises) else ">>> AUCUN assert/raise <<<"
            print(f"   - {node.name:32} assert={len(asserts)} raise={len(raises)}  {flag}")
            if deco:
                print(f"       @… \"{deco}\"")


def main() -> None:
    client = TestClient(app)
    print("=" * 72)
    print("1. Re-génération du spec avec le prompt AMÉLIORÉ (Règle 4)")
    resp = client.post(f"/api/modules/{MODULE_ID}/cases",
                       json={"spec_content": SPEC, "title": TITLE, "author": "preuve-A"})
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ÉCHEC :", resp.text[:500]); return
    job_id = resp.json()["job_id"]
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print("   job  :", job["status"], "| case_id =", job.get("case_id"))
    if job["status"] != "done":
        print("   ERREUR :", (job.get("error") or "")[:600]); return

    detail = client.get(f"/api/cases/{job['case_id']}").json()
    version = detail["versions"][-1]
    feature, steps = version["feature_content"], version["steps_content"]

    print()
    print("=" * 72)
    print("2. Scénario [Limite] généré")
    print(_limite_scenario(feature) or "   (aucun scénario [Limite] trouvé)")

    print()
    print("=" * 72)
    print("3. Steps custom : chacun contient-il une assertion (Règle 4) ?")
    _functions_with_asserts(steps)

    print()
    print("=" * 72)
    print("4. Steps custom — code brut (pour juger la falsifiabilité à l'œil)")
    print(steps)


if __name__ == "__main__":
    main()
