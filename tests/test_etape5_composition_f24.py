"""Étape 5 du plan unique (F24) — un « Alors » qui lit « cet enregistrement » sans qu'aucune étape précédente ne l'ait
posé est refusé à l'ÉCRITURE (avant : `RuntimeError` à l'exécution, un cas en erreur technique et une réparation payée).

Gardé ici : ce qui pose et ce qui lit est lu dans le CODE de la bibliothèque (AST, à travers ses helpers) ; le contexte, les
règles et les plans comptent ; une étape hors bibliothèque (écrite par le test) peut poser l'enregistrement — prudence.
"""

from __future__ import annotations

from testpilot.generation import composition_scenario as cs
from testpilot.generation import steps_library as sl
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

CATALOGUE = sl.catalogue(connector_type="odoo")
LIT = 'Alors le champ "name" de cet enregistrement est égal à "X"'
TROUVE = 'Soit un enregistrement avec le champ "name" égal à "X" existe dans le modèle "res.partner"'


def _feature(*etapes, contexte=()):
    lignes = ["# language: fr", "Fonctionnalité: f"]
    if contexte:
        lignes += ["  Contexte:", *[f"    {e}" for e in contexte]]
    return "\n".join([*lignes, "  Scénario: s", *[f"    {e}" for e in etapes], ""])


def test_la_bibliotheque_dit_qui_pose_et_qui_lit_par_son_code():
    poseurs = {s.label for s in CATALOGUE if s.pose_enregistrement}
    lecteurs = {s.label for s in CATALOGUE if s.lit_enregistrement}
    assert "j'enregistre le document" in poseurs
    assert 'un enregistrement avec le champ "{field}" égal à "{value}" existe dans le modèle "{model}"' in poseurs
    assert 'le champ "{field}" de cet enregistrement est égal à "{expected}"' in lecteurs
    assert "cet utilisateur voit l'enregistrement" in lecteurs   # par un helper
    assert not poseurs & lecteurs


def test_falsifiable_lu_sans_etre_pose_est_signale():
    fautes = cs.enregistrement_lu_sans_etre_pose(_feature(LIT), CATALOGUE)
    assert len(fautes) == 1 and "aucune étape précédente" in fautes[0]


def test_pose_avant_dans_le_scenario_ou_le_contexte_passe():
    assert cs.enregistrement_lu_sans_etre_pose(_feature(TROUVE, LIT), CATALOGUE) == []
    assert cs.enregistrement_lu_sans_etre_pose(_feature(LIT, contexte=[TROUVE]), CATALOGUE) == []


def test_pose_apres_ne_compte_pas():
    assert cs.enregistrement_lu_sans_etre_pose(_feature(LIT, TROUVE.replace("Soit", "Et")), CATALOGUE)


def test_une_etape_hors_bibliotheque_peut_poser_l_enregistrement():
    assert cs.enregistrement_lu_sans_etre_pose(_feature("Soit je prépare mon client maison", LIT), CATALOGUE) == []


def test_sans_catalogue_rien_n_est_refuse():
    assert cs.enregistrement_lu_sans_etre_pose(_feature(LIT), []) == []


def test_falsifiable_write_feature_file_refuse_avant_d_ecrire(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, shared_steps=CATALOGUE)
    sortie = w.write_feature_file(ctx, _feature(LIT))
    assert not sortie.ok and "ENREGISTREMENT_NON_POSE" in sortie.observation
    assert not (tmp_path / "m.feature").exists()


def test_falsifiable_correction_et_reparation_refusent_aussi_un_enregistrement_non_pose(monkeypatch, tmp_path):
    """Revue du 2026-10-22 : la correction et la réparation écrivent avec le MÊME contrôle de composition — leur contexte
    reçoit le catalogue, et un « cet enregistrement » jamais posé y est refusé."""
    from testpilot import config
    from testpilot.generation import correction_agent, repair_agent

    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    refus = []

    def boucle(**kw):
        sortie = w.write_feature_file(kw["ctx"], _feature(LIT))
        refus.append((bool(kw["ctx"].shared_steps), sortie.ok, "ENREGISTREMENT_NON_POSE" in sortie.observation))
    monkeypatch.setattr(correction_agent, "run_loop", boucle)
    monkeypatch.setattr(repair_agent, "run_loop", boucle)
    correction_agent.propose_correction(module_name="m", lint_warnings=[], feature_content=_feature(TROUVE, LIT),
                                        steps_content="", llm=object(), connector_type="odoo")
    repair_agent.propose_fix(module_name="m", scenarios=[], failures=[], llm=object(), connector_type="odoo",
                             feature_content=_feature(TROUVE, LIT))
    assert refus == [(True, False, True), (True, False, True)]
