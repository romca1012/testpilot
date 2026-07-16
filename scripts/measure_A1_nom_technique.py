"""Mesure de la phase A1 (décision 0007) : le catalogue annonce désormais que `{field}` est le
NOM TECHNIQUE du champ, jamais son libellé affiché. L'agent obéit-il ?

Question tranchée par ce script : le step UI généré est-il paramétré `champ "name"` (nom
technique — obéissance) ou `champ "Raison de la demande"` (libellé humain — l'écart 1 persiste) ?

Référence AVANT A1, mesurée sur la vraie base (cf. note 0007) : le bug était DÉTERMINISTE —
cas 2 ET cas 3 ont tous deux produit `champ "Raison de la demande"` pour le step UI, tout en
paramétrant correctement les assertions RPC avec `name`. C'est ce contraste qui avait établi que
l'agent applique un modèle cohérent (libellé pour l'UI, technique pour le RPC) faute d'un contrat
écrit — trou que A1 vient combler.

Non déterministe (appel LLM) : on LIT le résultat, on ne le présume pas (§8.5). L'obéissance d'un
LLM se mesure, elle ne se décrète pas — c'est la limite assumée de toute option « prompt ».

Vérité terrain des noms techniques du formulaire : `scripts/probe_champs_formulaire.py`
(le champ affiché « Raison de la demande * » porte l'attribut `name='name'`).

Base sauvegardée : data/testpilot.db.pre-mesure-A1.bak
Usage : PYTHONUTF8=1 python scripts/measure_A1_nom_technique.py
"""

import re
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app

MODULE_ID = 1
SPEC = Path("specs/validation_champ_requis.md").read_text(encoding="utf-8")
TITLE = "Validation champ requis (mesure A1 nom technique)"

# Le cas EXACT de l'écart 1 : ce libellé s'affiche, mais le champ s'appelle `name`.
LIBELLE_FAUTIF = "Raison de la demande"
NOM_TECHNIQUE_ATTENDU = "name"

# Steps UI de la bibliothèque partagée : leur `{field}` DOIT être l'attribut HTML `name`.
_UI_FIELD_RES = [
    re.compile(r'je renseigne le champ "([^"]+)" avec la valeur'),
    re.compile(r'je laisse le champ "([^"]+)" vide'),
    re.compile(r'je sélectionne "[^"]*" dans le champ "([^"]+)"'),
]
# Steps de vérification Odoo : leur `{field}` est le champ du MODÈLE (déjà correct avant A1).
_RPC_FIELD_RES = [
    re.compile(r'le champ "([^"]+)" de cet enregistrement'),
    re.compile(r'avec le champ "([^"]+)" égal à'),
    re.compile(r'aucun enregistrement partiel avec le champ "([^"]+)" vide'),
]


def _params(feature: str, regexes) -> list[str]:
    return [m for rx in regexes for m in rx.findall(feature)]


def _ressemble_a_un_libelle(param: str) -> bool:
    """Heuristique de PRÉSENTATION seulement — le verdict s'appuie sur le cas exact, pas sur elle."""
    return " " in param or param != param.lower()


def main() -> None:
    db = Path(config.DB_PATH)
    if db.exists():
        backup = db.with_suffix(".db.pre-mesure-A1.bak")
        shutil.copy2(db, backup)
        print("backup base ->", backup.name)

    client = TestClient(app)
    print("=" * 72)
    print("1. Re-génération du MÊME spec, avec le catalogue ANNOTÉ (A1)")
    resp = client.post(f"/api/modules/{MODULE_ID}/cases",
                       json={"spec_content": SPEC, "title": TITLE, "author": "mesure-A1"})
    print("   HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("   ÉCHEC :", resp.text[:500]); return
    job = client.get(f"/api/modules/jobs/{resp.json()['job_id']}").json()
    print("   job  :", job["status"], "| case_id =", job.get("case_id"))
    if job["status"] != "done":
        print("   ERREUR :", (job.get("error") or "")[:800]); return

    detail = client.get(f"/api/cases/{job['case_id']}").json()
    feature = detail["versions"][-1]["feature_content"]

    ui = _params(feature, _UI_FIELD_RES)
    rpc = _params(feature, _RPC_FIELD_RES)

    print()
    print("=" * 72)
    print("2. Paramètres `{field}` des steps UI partagés (ceux que A1 vise)")
    if not ui:
        print("   (aucun step UI partagé paramétré par un champ — mesure non concluante)")
    for p in ui:
        verdict = "LIBELLÉ ?" if _ressemble_a_un_libelle(p) else "technique"
        print(f"   - {p!r:34} → {verdict}")

    print()
    print("3. Paramètres `{field}` des steps de vérification Odoo (déjà corrects avant A1)")
    for p in rpc:
        print(f"   - {p!r}")

    print()
    print("=" * 72)
    print("VERDICT DE LA MESURE (cas exact de l'écart 1)")
    print(f"   Libellé fautif d'avant A1   : {LIBELLE_FAUTIF!r}")
    print(f"   Nom technique attendu       : {NOM_TECHNIQUE_ATTENDU!r}")
    libelle_present = any(LIBELLE_FAUTIF in p for p in ui)
    technique_present = any(p == NOM_TECHNIQUE_ATTENDU for p in ui)
    print(f"   Step UI paramétré au libellé : {libelle_present}")
    print(f"   Step UI paramétré au `name`  : {technique_present}")
    if technique_present and not libelle_present:
        print("   => OBÉISSANCE CONFIRMÉE : l'agent écrit le nom technique dans le step UI.")
    elif libelle_present:
        print("   => ÉCART 1 PERSISTE à la génération. Non bloquant : le repli de la phase B le")
        print("      rattrape à l'exécution (et le trace). A1 n'aura pas suffi — à documenter.")
    else:
        print("   => NON CONCLUANT : le spec n'a pas produit le step UI attendu. Relire ci-dessus.")

    print()
    print("=" * 72)
    print("4. Steps UI du .feature généré (lecture directe)")
    for ln in feature.splitlines():
        if "champ" in ln:
            print("   ", ln.strip())


if __name__ == "__main__":
    main()
