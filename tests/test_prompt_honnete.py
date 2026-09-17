"""Le prompt ne promet à l'agent que des capacités qui EXISTENT (décision 0014, étape 1).

⚠️ Un prompt qui décrit une capacité absente est déjà, en soi, un « affiché ≠ réel » (§4.6) —
au niveau du prompt. Constaté le 2026-07-16 : le prompt de génération promettait **quatre** outils
inexistants (`run_behave`, `recall_memory`, `save_memory`, `list_models`), un format de rapport
que rien ne lisait (`RAPPORT_DEBUT`), et un critère de terminaison **impossible à satisfaire**
(« run réel vert » + `save_memory`). L'agent était donc invité à appeler des outils absents — et
`recall_memory` était même prescrit « toujours en 1er ».

Ces tests gardent le MOTIF, pas les quatre cas trouvés : tout nouvel outil cité dans un prompt
doit exister dans `TOOLS_DEFINITIONS`.
"""

import re
from pathlib import Path

import pytest

from testpilot import config
from testpilot.generation.tools import TOOLS_DEFINITIONS

_PROMPTS = config.PROMPTS_DIR
_NOMS_REELS = {t["name"] for t in TOOLS_DEFINITIONS}


def _description(nom_outil: str) -> str:
    """Description RÉELLE d'un outil — celle que l'agent lit."""
    for outil in TOOLS_DEFINITIONS:
        if outil["name"] == nom_outil:
            return outil["description"]
    raise AssertionError(f"outil {nom_outil} introuvable")

# Un appel d'outil dans le prompt s'écrit `nom(...)` ou `` `nom` ``. On ne retient que les
# identifiants en snake_case suivis d'une parenthèse : c'est la forme d'un appel.
_APPEL_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*\(")

# Mots en snake_case suivis d'une parenthèse qui ne sont PAS des outils : fonctions Python citées
# en exemple, helpers de la bibliothèque, attributs. Liste explicite — un ajout ici doit être
# justifié, sinon le garde ne garde plus rien.
_NON_OUTILS = {
    # helpers de la bibliothèque partagée, cités dans les règles de code
    "fill_field", "click_button", "leave_field_empty", "select_field_value",
    "register_created", "no_duplicate", "wait_form_submission", "count_records",
    "resolve_field_name", "validation_error_inline", "no_partial_record",
    # Python / Behave
    "search_count", "wait_for_selector", "get_by_label", "get_by_role", "wait_for_load_state",
    "toggle_submit_button",
    # Playwright — Règle 5 (attendre avant de lire/compter, bug réel cas C43, 2026-09-14 ;
    # is_visible/to_be_visible ajoutés à l'audit fiabilité du 2026-09-17)
    "wait_for_url", "wait_for", "inner_text", "text_content", "is_visible", "to_be_visible",
}


def _fichiers_prompt() -> list[Path]:
    return sorted(_PROMPTS.glob("*.md"))


def test_il_y_a_bien_des_prompts_a_verifier():
    # Garde du garde : si le glob ne trouve rien, les tests ci-dessous passeraient à vide.
    assert _fichiers_prompt(), f"aucun prompt trouvé dans {_PROMPTS}"


@pytest.mark.parametrize("nom_fantome", ["run_behave", "recall_memory", "save_memory",
                                         "list_models"])
def test_les_outils_fantomes_ont_disparu(nom_fantome):
    """Les quatre outils que le prompt promettait sans qu'ils existent."""
    assert nom_fantome not in _NOMS_REELS, (
        f"{nom_fantome} existe maintenant : retirer ce test et documenter la capacité.")
    for path in _fichiers_prompt():
        contenu = path.read_text(encoding="utf-8")
        assert nom_fantome not in contenu, (
            f"{path.name} promet encore `{nom_fantome}`, qui n'existe pas. Un prompt qui décrit "
            f"une capacité absente est un « affiché ≠ réel » (§4.6).")


def test_aucun_prompt_ne_cite_un_outil_inexistant():
    """Le garde du MOTIF : tout `nom_snake_case(` d'un prompt est soit un outil réel, soit
    explicitement listé comme n'en étant pas un."""
    coupables: dict[str, set[str]] = {}
    for path in _fichiers_prompt():
        contenu = path.read_text(encoding="utf-8")
        for nom in set(_APPEL_RE.findall(contenu)):
            if nom in _NOMS_REELS or nom in _NON_OUTILS:
                continue
            coupables.setdefault(path.name, set()).add(nom)
    assert not coupables, (
        f"Ces prompts citent des appels qui ne correspondent à aucun outil réel : {coupables}. "
        f"Outils réels : {sorted(_NOMS_REELS)}. Si c'est une fonction Python citée en exemple, "
        f"ajoutez-la à _NON_OUTILS ; sinon le prompt promet ce qui n'existe pas.")


def test_le_prompt_de_generation_ne_promet_ni_run_reel_ni_reparation():
    """La phase de l'agent s'arrête au dry-run : le lui dire évite qu'il attende un retour
    d'exécution qui ne viendra jamais (son ancien critère de terminaison exigeait « run réel
    vert » — impossible, donc jamais satisfait)."""
    contenu = (_PROMPTS / "system_prompt.md").read_text(encoding="utf-8")
    assert "Tu n'exécutes pas le test réel et tu ne le répares pas" in contenu
    assert "RAPPORT_DEBUT" not in contenu   # format que rien ne lisait


def test_le_prompt_de_reparation_existe_et_interdit_le_maquillage():
    """La doctrine de run réel n'est pas perdue : elle est déplacée, pas supprimée."""
    path = _PROMPTS / "repair_prompt.md"
    assert path.is_file(), "le prompt de réparation a disparu — la doctrine de 0008 avec lui"
    contenu = path.read_text(encoding="utf-8")
    assert "maquillage interdit" in contenu           # la règle absolue de 0008
    assert "faux négatif" in contenu                  # l'enjeu, §4.4
    assert "Tu ne lances aucune exécution" in contenu  # design (b) : l'agent ne pilote pas


def test_le_plafond_annonce_est_le_plafond_reel():
    """Annoncer « ≤15 » quand la boucle coupe à 25 est encore un « affiché ≠ réel »."""
    contenu = (_PROMPTS / "system_prompt.md").read_text(encoding="utf-8")
    assert f"Plafond dur : {config.MAX_ITERATIONS} tours" in contenu, (
        f"le prompt doit annoncer le vrai plafond ({config.MAX_ITERATIONS}), pas un chiffre "
        f"décoratif.")


# ══════════════════════════════════════════════════════════════════════════════
# Principe 6 (docs/PRINCIPES.md) — généralisation du motif
#
# `test_aucun_prompt_ne_cite_un_outil_inexistant` gardait UNE promesse : « cet outil existe ».
# Le principe la généralise : **toute affirmation d'un prompt ou d'une description d'outil sur
# une capacité, un format ou une contrainte doit être liée par un test au code qui l'applique.**
#
# Ces gardes vérifient le COMPORTEMENT, pas le texte : un `grep` dirait seulement que le mot est
# là, jamais que la règle est appliquée. C'est la différence entre relire le prompt et le prouver.
# ══════════════════════════════════════════════════════════════════════════════

from testpilot.generation.tools import ToolContext, write as write_tools  # noqa: E402


def _ctx(tmp_path, reserved=frozenset()):
    return ToolContext(module_name="m", generated_dir=tmp_path, reserved_steps=reserved)


def test_la_promesse_ASCII_de_la_description_est_REELLEMENT_appliquee(tmp_path):
    """`write_steps_file` annonce « Validé : ASCII ». Sans ce test, la description pourrait
    mentir le jour où la validation saute — et l'agent, lui, la croirait."""
    assert "ASCII" in _description("write_steps_file")
    r = write_tools.write_steps_file(_ctx(tmp_path), 'x = “bonjour”\n')
    assert not r.ok and "guillemets typographiques" in r.observation


def test_la_promesse_pas_de_step_partage_redefini_est_REELLEMENT_appliquee(tmp_path):
    assert "pas de step partagé redéfini" in _description("write_steps_file")
    contenu = ('from behave import given\n\n\n'
               '@given("je me connecte avec mes identifiants utilisateur")\n'
               'def step_impl(context):\n    pass\n')
    r = write_tools.write_steps_file(
        _ctx(tmp_path, reserved=frozenset({"je me connecte avec mes identifiants utilisateur"})),
        contenu)
    assert not r.ok and "bibliothèque partagée" in r.observation


def test_la_promesse_REMPLACE_le_fichier_est_REELLEMENT_tenue(tmp_path):
    """Les deux descriptions annoncent « REMPLACE … rends le fichier ENTIER ».

    Si l'outil AJOUTAIT au lieu de remplacer, la consigne serait fausse et l'agent produirait des
    doublons de steps. C'est la promesse dont dépend le correctif du bug 2 de `0014`.
    """
    for nom in ("write_feature_file", "write_steps_file"):
        assert "REMPLACE" in _description(nom)

    write_tools.write_steps_file(_ctx(tmp_path), "PREMIER = 1\n")
    write_tools.write_steps_file(_ctx(tmp_path), "SECOND = 2\n")
    contenu = (tmp_path / "m_steps.py").read_text(encoding="utf-8")
    assert contenu == "SECOND = 2\n"
    assert "PREMIER" not in contenu       # remplacement, pas ajout


def test_la_promesse_tu_ne_lances_aucune_execution_est_STRUCTURELLE():
    """Le prompt de réparation l'affirme ; aucun outil ne doit pouvoir la démentir.

    C'est le design (b) de `0014` — l'agent propose, l'orchestrateur exécute. Rien ne gardait
    cette affirmation : ajouter un outil `run_behave` demain la rendrait fausse en silence.
    """
    contenu = (_PROMPTS / "repair_prompt.md").read_text(encoding="utf-8")
    assert "Tu ne lances aucune exécution" in contenu

    interdits = ("run", "exec", "behave", "launch", "trigger")
    coupables = [n for n in _NOMS_REELS if any(mot in n.lower() for mot in interdits)]
    assert not coupables, (
        f"le prompt de réparation affirme « Tu ne lances aucune exécution » alors que ces outils "
        f"existent : {coupables}. Soit l'outil part, soit l'affirmation part — pas les deux.")


def test_le_prompt_de_reparation_ne_promet_pas_un_budget_qu_il_ignore():
    """Le prompt ne doit pas annoncer un nombre de tentatives : c'est le GATE qui le fixe,
    par version (décision 0014, option C), et il varie d'une relecture à l'autre."""
    contenu = (_PROMPTS / "repair_prompt.md").read_text(encoding="utf-8")
    for chiffre in ("2 tentatives", "deux tentatives", "3 tentatives"):
        assert chiffre not in contenu, (
            f"le prompt annonce « {chiffre} » alors que le budget vient du gate et varie.")
