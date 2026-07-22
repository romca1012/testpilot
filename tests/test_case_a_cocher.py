"""Cases à cocher — la 10ᵉ occurrence du motif, et le seul échec technique restant (2026-07-22).

⚠️ **Le défaut.** Sur `/sinistre_client`, `info_sinistre_ids` est une **case à cocher** obligatoire.
Son nom évoque des documents ; l'agent a écrit `je joins un fichier au champ "info_sinistre_ids"`
**quatre fois**. Playwright a cherché 30 secondes un champ téléversable qui n'existait pas, puis a
échoué sur une trace illisible.

⚠️ **Ce n'était PAS un trou d'outil** — et c'est ce qui rend le cas instructif. `fill_field` sait
cocher depuis toujours (`elif input_type == "checkbox"`). L'agent *pouvait* réussir. Mais le prompt
ne signalait que le type `file` et **se taisait sur tous les autres types**, donc l'agent devinait
d'après le NOM du champ. **Dixième fois que l'annuaire savait sans que personne ne transmette.**

Deux couches, testées ici :
1. le prompt NOMME les cases à cocher et dit quoi employer à la place ;
2. `attach_file` refuse **immédiatement** une cible non-fichier, en indiquant l'issue — 30 secondes
   d'attente deviennent une milliseconde et un message qui se lit.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from testpilot.analysis.plan import TestPlan  # noqa: E402
from testpilot.generation import prompt as pm  # noqa: E402


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-22", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


def _champ(name, **kw):
    base = {"name": name, "required": True, "tag": "input", "type": "text", "visible": True}
    return {**base, **kw}


# ── Couche 1 : le prompt nomme les cases à cocher ────────────────────────────

def test_le_prompt_signale_une_CASE_A_COCHER():
    modele = _modele([_champ("info_sinistre_ids", type="checkbox")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CASE À COCHER" in s
    assert "info_sinistre_ids" in s


def test_le_prompt_dit_QUOI_FAIRE_a_la_place():
    """Une interdiction sans alternative laisse l'agent inventer — c'est ce qui s'est passé."""
    modele = _modele([_champ("info_sinistre_ids", type="checkbox")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert 'avec la valeur "oui"' in s


def test_le_prompt_PREVIENT_la_confusion_avec_une_piece_jointe():
    """⚠️ Le cœur : c'est le NOM du champ qui a trompé l'agent, pas son type. Le prompt doit
    désamorcer explicitement cette lecture, sinon la consigne se fait déborder par l'intuition."""
    modele = _modele([_champ("info_sinistre_ids", type="checkbox")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "ce n'en sont pas" in s
    assert "je joins un fichier" in s, "l'erreur exacte à ne pas commettre est nommée"


def test_un_champ_FICHIER_reste_traite_comme_avant():
    """Non-régression : les deux consignes coexistent sans se marcher dessus."""
    modele = _modele([_champ("rib", type="file"), _champ("certifie", type="checkbox")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CHAMP FICHIER" in s and "`rib`" in s
    assert "CASE À COCHER" in s and "`certifie`" in s


def test_aucune_alerte_case_a_cocher_quand_il_n_y_en_a_pas():
    modele = _modele([_champ("nom")])

    assert "CASE À COCHER" not in pm._section_champs_requis(_plan(["/form/{id}"]), modele)


def test_sur_l_annuaire_REEL_la_case_de_sinistre_client_est_signalee():
    import json

    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    s = pm._section_champs_requis(_plan(["/sinistre_client/{id}"]), modele)

    assert "info_sinistre_ids" in s
    assert "CASE À COCHER" in s, "le champ qui a produit l'échec technique doit être signalé"


# ── Couche 2 : `attach_file` refuse vite, et dit l'issue ─────────────────────

class _Locator:
    def __init__(self, journal, type_reel):
        self.journal, self.type_reel = journal, type_reel
        self.first = self

    def evaluate(self, script, *a): return self.type_reel
    def set_input_files(self, chemin): self.journal.append(("upload", chemin))


class _Page:
    def __init__(self, type_reel):
        self.journal: list = []
        self.type_reel = type_reel

    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _Locator(self.journal, self.type_reel)


@pytest.mark.parametrize("type_reel", ["checkbox", "radio", "text", ""])
def test_televerser_sur_un_NON_FICHIER_echoue_IMMEDIATEMENT(type_reel):
    """⚠️ L'essentiel n'est pas que ça échoue — ça échouait déjà — mais que ça échoue **tout de
    suite** et **lisiblement**. 30 secondes d'attente Playwright suivies d'une trace cryptique
    coûtent du temps de run ET du temps de diagnostic."""
    from _base_helpers import attach_file

    page = _Page(type_reel)

    with pytest.raises(AssertionError, match="n'est PAS un champ fichier"):
        attach_file(page, "info_sinistre_ids", "doc.pdf")

    assert page.journal == [], "aucun téléversement ne doit être tenté"


def test_le_message_INDIQUE_l_issue_pour_une_case_a_cocher():
    """Un message qui ne dit pas quoi faire oblige à re-diagnostiquer à chaque occurrence."""
    from _base_helpers import attach_file

    with pytest.raises(AssertionError) as err:
        attach_file(_Page("checkbox"), "info_sinistre_ids", "doc.pdf")

    message = str(err.value)
    assert 'avec la valeur "oui"' in message
    assert "info_sinistre_ids" in message
    assert "cocher" in message


def test_un_VRAI_champ_fichier_televerse_toujours():
    """Non-régression : le garde-fou ne doit pas bloquer le cas nominal."""
    from _base_helpers import attach_file

    page = _Page("file")

    attach_file(page, "rib_client", "rib.pdf")

    assert [a for a, _ in page.journal] == ["upload"]
