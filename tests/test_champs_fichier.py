"""Champs FICHIER — la cause n°1 des erreurs techniques mesurées (2026-07-21).

Mesure du taux d'erreur technique : **2 échecs sur 3** venaient de là. L'agent remplissait un
`<input type="file">` comme du texte → le navigateur refuse
(`InvalidStateError: This input element accepts a filename`).

⚠️ **L'agent ne pouvait PAS réussir** : la bibliothèque partagée n'avait aucun step d'upload, et
`fill_field` ne connaissait pas le type `file`. L'outil n'existait pas — ce n'était pas une
faiblesse de prompt. Or **13 des 37 routes du portail** ont un champ fichier, presque toujours
REQUIS : c'était donc un plafond structurel sur la fiabilité.

Le correctif a trois couches, testées ici :
1. `fill_field` reconnaît le type `file` et téléverse (plus jamais de `el.value = …`) ;
2. un step partagé `je joins un fichier au champ "…"` existe (l'agent voit la capacité) ;
3. le prompt DIT quels champs requis sont des fichiers (l'annuaire le savait, personne ne le
   transmettait).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from testpilot.analysis.plan import TestPlan  # noqa: E402
from testpilot.generation import domain_model, prompt as pm  # noqa: E402


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-21", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


# ── Couche 1 : le helper téléverse au lieu d'écrire du texte ──────────────────

class _FauxLocator:
    def __init__(self, journal, input_type):
        self.journal = journal
        self.input_type = input_type
        self.first = self

    def set_input_files(self, chemin): self.journal.append(("upload", chemin))

    def evaluate(self, script, *a):
        # `fill_field` interroge le locator pour le tag puis le type de l'élément.
        return "input" if "tagName" in script else self.input_type


class _FauxPage:
    """Simule un `<input type="file">`. `page.evaluate` = l'ANCIEN chemin fautif (écriture JS)."""

    def __init__(self, input_type="file"):
        self.input_type = input_type
        self.journal: list = []

    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocator(self.journal, self.input_type)
    def evaluate(self, script, *a):
        self.journal.append(("js", script))   # ← ce que le correctif doit éviter
        return None


def test_fill_field_TELEVERSE_sur_un_champ_fichier():
    """Le cœur du correctif : plus jamais `el.value = …` sur un champ fichier."""
    from _base_helpers import fill_field

    page = _FauxPage(input_type="file")
    # `resolve_field_name` interroge la page ; on court-circuite en passant un nom résoluble.
    import _base_helpers as H
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        fill_field(page, "rib_client", "rib.pdf")
    finally:
        H.resolve_field_name = original

    actions = [a for a, _ in page.journal]
    assert "upload" in actions, "un champ fichier doit être TÉLÉVERSÉ"
    assert "js" not in actions, "plus jamais d'écriture JS sur un champ fichier"


def test_le_fichier_televerse_existe_vraiment_et_n_est_pas_vide():
    """Un fichier vide (ou un .txt déguisé) peut être rejeté par une validation de type — on
    diagnostiquerait alors un faux « champ introuvable »."""
    from _base_helpers import attach_file

    page = _FauxPage()
    import _base_helpers as H
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        attach_file(page, "rib_client", "rib.pdf")
    finally:
        H.resolve_field_name = original

    chemin = Path(page.journal[0][1])
    assert chemin.exists()
    assert chemin.read_bytes().startswith(b"%PDF"), "un PDF valide, pas un fichier vide"


def test_le_nom_du_fichier_est_deduit_quand_la_valeur_n_en_est_pas_un():
    from _base_helpers import attach_file

    page = _FauxPage()
    attach_file(page, "justificatifs_mutation", "un texte quelconque")

    nom = Path(page.journal[0][1]).name
    assert nom.startswith("piece-jointe-"), "nom généré depuis le champ"
    assert nom.endswith(".pdf")


# ── Couche 2 : le step partagé existe (l'agent voit la capacité) ──────────────

def test_le_step_d_upload_est_AU_CATALOGUE():
    """Sans step au catalogue, l'agent ne peut pas savoir que la capacité existe (`0003`)."""
    from testpilot.generation import steps_library

    libelles = [s.label for s in steps_library.catalogue()]
    assert any("joins un fichier" in lb for lb in libelles), (
        "le step d'upload doit être proposé à l'agent")


# ── Couche 3 : le prompt DIT quels champs sont des fichiers ───────────────────

def test_le_prompt_signale_les_champs_FICHIER():
    """L'annuaire connaissait le type depuis toujours ; personne ne le transmettait."""
    modele = _modele([
        {"name": "nom", "required": True, "tag": "input", "type": "text"},
        {"name": "rib_client", "required": True, "tag": "input", "type": "file"},
    ])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CHAMP FICHIER" in s
    assert "rib_client" in s
    assert "je joins un fichier au champ" in s, "le prompt indique LE step à employer"
    assert "InvalidStateError" in s, "il dit pourquoi écrire du texte échoue"


def test_sans_champ_fichier_aucune_alerte_inutile():
    """Pas de consigne inventée là où elle n'a pas lieu d'être (bruit = alerte tue)."""
    modele = _modele([{"name": "nom", "required": True, "tag": "input", "type": "text"}])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CHAMP FICHIER" not in s


def test_le_type_est_expose_par_l_annuaire():
    """La donnée manquante, à la source : `formulaires_requis` n'exposait pas `type`."""
    modele = _modele([{"name": "rib", "required": True, "tag": "input", "type": "file"}])

    forms = domain_model.formulaires_requis(modele, ["/form/{id}"])

    assert forms[0]["requis"][0]["type"] == "file"


# ── Sur l'annuaire RÉEL : l'ampleur du problème ───────────────────────────────

def test_sur_l_annuaire_REEL_les_champs_fichier_sont_signales():
    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    s = pm._section_champs_requis(_plan(["/mutation/{id}"]), modele)

    assert "justificatifs_mutation" in s
    assert "CHAMP FICHIER" in s, "le champ fichier requis de /mutation doit être signalé"
