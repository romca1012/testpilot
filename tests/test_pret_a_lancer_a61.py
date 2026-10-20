"""Décision A61 (porteur, 2026-10-20) — « après une génération, tout doit être bon et prêt à lancer » : l'écran « à relire »
est l'exception, pas la règle. Ce qu'on corrige, mesuré sur le projet d'essai « Essai lignes » (C155 à C158) :

1. le contrôle de preuve d'observation ne reconnaissait pas l'étape web `j'ouvre la page "…"` : tous les champs d'un test
   web sortaient « sans preuve » et le cas restait à relire, la preuve d'écran étant pourtant là ;
2. arrivé par un clic (menu), le texte ne nomme pas la page : une preuve d'écran de la génération où le champ était
   visible suffit — jamais un schéma RPC, jamais une preuve périmée ou d'une autre cible ;
3. un test qui ne pourrait pas être rejoué ligne par ligne (un « Plan du scénario » dont les Exemples répètent les
   variables) est refusé À L'ÉCRITURE — l'IA le réécrit avant de rendre la main, au lieu d'un « bloqué » au lancement.
"""

from __future__ import annotations

from datetime import datetime, timezone

from testpilot.generation import variables_de_test as vdt
from testpilot.generation.evidence import contextual_warnings
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import write_feature_file

BASE = "http://127.0.0.1:8095"
MAINTENANT = datetime.now(timezone.utc).isoformat()


def _preuve(page="/acces", source="ui", visible=True, cible="c1", quand=MAINTENANT):
    return {"source": source, "resource": BASE + page, "observed_at": quand, "target_sha256": cible,
            "fields": [{"name": "age", "visible": visible}]}


def _test(navigation='Et j\'ouvre la page "/acces"'):
    return ("# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit je me connecte en tant que \"principal\"\n"
            f"    {navigation}\n    Quand je renseigne le champ \"age\" avec la valeur \"17\"\n")


def _avis(feature, preuves):
    return contextual_warnings(feature, preuves, target_sha256="c1", base_url=BASE)


def test_falsifiable_j_ouvre_la_page_situe_le_champ_sur_sa_page():
    assert _avis(_test(), [_preuve()]) == [], "champ vu sur /acces, test sur /acces : prêt à lancer"
    assert [a["kind"] for a in _avis(_test(), [_preuve(page="/clients")])] == ["champ_ui_non_verifie"], \
        "vu sur une AUTRE page : toujours signalé"


def test_falsifiable_l_ecriture_odoo_reste_reconnue():
    assert _avis(_test('Et je navigue vers "/acces"'), [_preuve()]) == []


def test_falsifiable_arrive_par_un_clic_une_preuve_d_ecran_de_la_generation_suffit():
    clic = _test('Et je clique sur le bouton "Contrôle d\'accès"')
    assert _avis(clic, [_preuve()]) == []


def test_falsifiable_ce_qui_n_est_pas_une_observation_d_ecran_reste_signale():
    clic = _test('Et je clique sur le bouton "Contrôle d\'accès"')
    for preuve in (_preuve(source="rpc"), _preuve(visible=False), _preuve(cible="autre"), _preuve(quand="2020-01-01T00:00:00+00:00")):
        assert [a["kind"] for a in _avis(clic, [preuve])] == ["champ_ui_non_verifie"], preuve
    assert [a["kind"] for a in _avis(clic, [])] == ["champ_ui_non_verifie"], "aucune preuve : signalé"


PLAN_QUI_REPETE = """# language: fr
Fonctionnalité: F
  Plan du scénario: S
    Quand je renseigne le champ "age" avec la valeur "{{age}}"
    Alors la page affiche le texte "{{resultat}}"

    Exemples:
      | age | resultat |
      | {{age}} | {{resultat}} |
"""
SIMPLE = """# language: fr
Fonctionnalité: F
  Scénario: S
    Quand je renseigne le champ "age" avec la valeur "{{age}}"
    Alors la page affiche le texte "{{resultat}}"
"""


def test_falsifiable_un_test_non_rejouable_ligne_par_ligne_est_refuse_a_l_ecriture(tmp_path):
    assert vdt.refus_non_iterable(PLAN_QUI_REPETE, ["age", "resultat"]), "mesuré sur C157/C158 : bloqué au lancement"
    assert vdt.refus_non_iterable(SIMPLE, ["age", "resultat"]) == []
    assert vdt.refus_non_iterable(SIMPLE.replace("{{age}}", "17").replace("{{resultat}}", "Non"), ["age"]) == [], \
        "sans variable : rien à rejouer"

    ctx = ToolContext(module_name="acces", generated_dir=tmp_path, variables_de_test=frozenset({"age", "resultat"}))
    refuse = write_feature_file(ctx, PLAN_QUI_REPETE)
    assert not refuse.ok and "rejoué ligne par ligne" in refuse.observation
    assert not (tmp_path / "acces.feature").exists(), "refusé : rien n'est écrit"
    assert write_feature_file(ctx, SIMPLE).ok


def test_la_consigne_de_l_agent_le_dit_quand_le_cas_a_des_lignes():
    section = vdt.section_prompt([{"nom": "age"}, {"nom": "resultat"}], ["age", "resultat"])
    assert "ni un « Plan du scénario » avec des « Exemples » pour ces variables" in section



# ── Non-régressions (revue A61) : formes JOUABLES qui ne doivent jamais être refusées ─────────────────────────────────────

CONTEXTE = """# language: fr
Fonctionnalité: F
  Contexte:
    Soit je saisis le compte "{{compte}}"

  Scénario: S1
    Quand je renseigne le champ "age" avec la valeur "{{age}}"
    Alors la page affiche le texte "{{resultat}}"

  Scénario: S2 sans variable
    Alors la page affiche le texte "Accueil"
"""
PLAN_SANS_COLLISION = """# language: fr
Fonctionnalité: F
  Plan du scénario: S
    Quand je saisis "<q>" pour l'âge "{{age}}"

    Exemples:
      | q |
      | 1 |
      | 2 |
"""


def test_les_formes_jouables_ne_sont_jamais_refusees():
    for feature in (SIMPLE, CONTEXTE, PLAN_SANS_COLLISION):
        assert vdt.refus_non_iterable(feature, ["age", "resultat", "compte"]) == [], feature


def test_falsifiable_une_variable_inconnue_ne_produit_pas_aussi_un_faux_motif_de_plan(tmp_path):
    ctx = ToolContext(module_name="acces", generated_dir=tmp_path, variables_de_test=frozenset({"age"}))
    refuse = write_feature_file(ctx, SIMPLE.replace("{{resultat}}", "{{inconnue}}"))
    assert not refuse.ok and "inconnue" in refuse.observation
    assert "rejoué ligne par ligne" not in refuse.observation, "un seul motif : la vraie faute"


def test_sans_donnee_de_test_le_controle_est_eteint(tmp_path):
    ctx = ToolContext(module_name="acces", generated_dir=tmp_path)
    assert write_feature_file(ctx, PLAN_QUI_REPETE.replace("{{age}}", "17").replace("{{resultat}}", "Non")).ok


def test_falsifiable_en_correction_les_variables_figees_suffisent_au_controle(tmp_path):
    ctx = ToolContext(module_name="acces", generated_dir=tmp_path)
    ctx.references_figees = vdt.references_du_texte(PLAN_QUI_REPETE)   # les variables du test de référence, telles quelles
    refuse = write_feature_file(ctx, PLAN_QUI_REPETE)
    assert not refuse.ok and "rejoué ligne par ligne" in refuse.observation


def test_falsifiable_la_page_ne_passe_pas_d_un_scenario_a_l_autre():
    """Scénario 1 sur /clients ; scénario 2 arrivé par un clic : sa route est inconnue, pas celle du scénario 1."""
    deux = ("# language: fr\nFonctionnalité: F\n  Scénario: S1\n    Et j'ouvre la page \"/clients\"\n"
            "    Quand je renseigne le champ \"age\" avec la valeur \"1\"\n"
            "  Scénario: S2\n    Et je clique sur le bouton \"Contrôle d'accès\"\n"
            "    Quand je renseigne le champ \"age\" avec la valeur \"17\"\n")
    avis = _avis(deux, [_preuve(page="/acces")])
    assert [a["line"] for a in avis] == [5], "S1 (sur /clients) signalé ; S2 (route inconnue, champ vu) non"
