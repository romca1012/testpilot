"""Lot VH-06 (point 3) — la part de « code libre » se mesure, et le prompt dit de préférer le catalogue.

Un step écrit à la main par l'agent n'a ni test de falsifiabilité ni résolution éprouvée : c'est la première source d'erreur
technique mesurée (banc base-3 et base-4). Le banc compte donc, pour chaque test généré, les steps qu'il définit lui-même.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
import banc_agents as ba  # noqa: E402

_STEPS = """from behave import given, when, then, step
from _base_helpers import constater


def _aide(page):
    return page.title()


@when('je fais une chose')
def a(context):
    context.page.reload()


@given('un contexte')
@when('un contexte')
def b(context):
    pass


@then('un constat')
def c(context):
    constater(_aide(context.page) == 'A', 't')
"""


def test_les_steps_definis_par_le_test_sont_comptes_par_fonction():
    """`b` est déclarée `@given` ET `@when` (comme le prompt le demande pour une action) : un step écrit à la main, pas deux."""
    assert ba.compter_steps_generes({"x.feature": "Fonctionnalité: x", "x_steps.py": _STEPS}) == 3


def test_un_test_sans_code_libre_compte_zero_et_un_fichier_illisible_ne_fait_rien_tomber():
    assert ba.compter_steps_generes({"x.feature": "…", "x_steps.py": "from _base_helpers import constater\n"}) == 0
    assert ba.compter_steps_generes({"x_steps.py": "def (:\n"}) == 0


def test_le_rapport_dit_combien_de_tests_n_ont_aucun_code_libre():
    campagne = ba.Campagne(k=3, cas=["a"], essais_prevus=3)
    campagne.essais = [ba.EssaiConsigne("a", 1, True, "", 0.1, {}, {}, 0), ba.EssaiConsigne("a", 2, True, "", 0.1, {}, {}, 3),
                       ba.EssaiConsigne("a", 3, False, "échec", 0.1, {}, {}, None)]
    campagne.observations = [ba.Observation("a", "saine", e, "conforme", "conforme", "", "", 1.0, True) for e in (1, 2)]

    rapport = ba.rendre_markdown(campagne, ba.calculer_indicateurs(campagne), {"etiquette": "t", "date": "2026-10-10"})

    assert "## Code libre (lot VH-06)" in rapport
    assert "**1/2**" in rapport and "3 au total (maximum 3" in rapport
    assert "| a | 2 | oui | 0.100 | — | 3 |" in rapport and "| a | 3 | NON : échec | 0.100 | — | — |" in rapport


def test_le_prompt_presente_les_steps_du_lot_et_ils_existent_dans_la_bibliotheque():
    prompt = (RACINE / "src" / "testpilot" / "generation" / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    regle = prompt[prompt.index("### Règle 9"):prompt.index("## PILIER 1")]
    generiques = (RACINE / "behave_runtime" / "steps_library" / "generic" / "_generic_steps.py").read_text(encoding="utf-8")

    for debut in ('dans la ligne contenant', 'la valeur affichée pour', 'un texte de la forme',
                  'je relève la valeur affichée pour', 'contient un élément dont'):
        assert debut in regle, f"le prompt ne présente pas « {debut} »"
        assert debut in generiques, f"« {debut} » n'existe pas dans la bibliothèque"


def test_les_exemples_du_prompt_ne_sont_pas_les_donnees_du_banc():
    """Relecture : « Câble HDMI », « 129,51 € », `CMD-[0-9]{4}`, « Dupont » étaient les attendus exacts des cas du banc — un
    gain mesuré sur ces cas n'aurait pas pu être attribué aux steps plutôt qu'à la fuite."""
    prompt = (RACINE / "src" / "testpilot" / "generation" / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    regle = prompt[prompt.index("### Règle 9"):prompt.index("## PILIER 1")]
    generiques = (RACINE / "behave_runtime" / "steps_library" / "generic" / "_generic_steps.py").read_text(encoding="utf-8")
    lot = generiques[generiques.index("# ── Lot VH-06"):generiques.index("def step_tableau_contient_ligne")]

    for donnee in ("Câble HDMI", "129,51", "CMD-", "Dupont", '"etat"', "Total TTC"):
        assert donnee not in regle, f"« {donnee} » (donnée du banc) est dans la Règle 9"
        assert donnee not in lot, f"« {donnee} » (donnée du banc) est dans une docstring du catalogue"


def test_la_premiere_ligne_de_chaque_docstring_du_lot_se_suffit():
    """Le catalogue du prompt ne garde que la PREMIÈRE ligne d'une docstring : coupée en pleine phrase, elle trompe l'agent."""
    import ast

    arbre = ast.parse((RACINE / "behave_runtime" / "steps_library" / "generic" / "_generic_steps.py").read_text(encoding="utf-8"))
    lot = {"step_saisir_dans_ligne", "step_valeur_affichee", "step_texte_de_la_forme", "step_relever", "step_oracle_liste_contient"}
    vues = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef) and noeud.name in lot:
            vues[noeud.name] = (ast.get_docstring(noeud) or "").splitlines()
    assert set(vues) == lot
    for nom, lignes in vues.items():
        assert len(lignes) == 1 and lignes[0].rstrip().endswith((".", ")")), f"{nom} : {lignes[:2]}"
