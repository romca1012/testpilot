"""Banc d'agents — mesure « après UNE réparation » (D23) : un test en erreur technique sur la saine est réparé une fois, puis rejoué.

Tout est simulé (aucun LLM, aucun navigateur). Ce que ces tests prouvent :
- seule l'erreur technique SUR LA SAINE déclenche une réparation (un `non_conforme` n'est pas « réparé » : décision humaine) ;
- la version réparée est rejouée sur TOUTES les variantes, et un test « réparé » qui passe partout est compté en FAUX VERT ;
- le coût de la réparation compte dans le plafond ; une réparation qui échoue n'est jamais prise pour un succès ;
- sans `reparer`, le rapport ne contient rien de nouveau.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("banc_agents_rep", RACINE / "scripts" / "banc_agents.py")
ba = importlib.util.module_from_spec(_spec)
sys.modules["banc_agents_rep"] = ba
_spec.loader.exec_module(ba)

SPECS = ["a"]
ATTENDUS = [ba.Attendu("a", "saine", "conforme"), ba.Attendu("a", "total_faux", "non_conforme")]
DEFAUTS = ["total_faux"]


def generer(cas, essai):
    return ba.Artefacts(cas, essai, fichiers={f"{cas}.feature": "ORIGINAL feature", f"{cas}_steps.py": "ORIGINAL steps"},
                        cout_usd=0.10, module=cas)


def jouer_factory(verdicts_origine, verdicts_repare):
    """`verdicts_*` : variante -> verdict, selon que le contenu joué est l'original ou le réparé."""
    appels = []

    def jouer(artefacts, variante):
        repare = "REPARE" in artefacts.fichiers[f"{artefacts.cas}.feature"]
        appels.append((variante, repare))
        table = verdicts_repare if repare else verdicts_origine
        trace = {"scenarios": [{"name": "S", "status": "error"}],
                 "echecs": [{"scenario_name": "S", "step_text": "je clique", "raw": "Locator.click: Timeout", "traceback_summary": ""}]}
        return ba.Jeu(verdict=table[variante], cause="wrong_field_name", detail="Timeout", empreintes=artefacts.empreintes,
                      trace=trace)

    jouer.appels = appels
    return jouer


def reparateur(cout=0.08, ok=True, resume="J'ai corrigé le locator."):
    appels = []

    def reparer(artefacts, jeu):
        appels.append(jeu)
        if not ok:
            return ba.Artefacts(artefacts.cas, artefacts.essai, cout_usd=cout, genere_ok=False, module=artefacts.module,
                                erreur="l'agent n'a rien réécrit", resume=resume)
        fichiers = {f"{artefacts.cas}.feature": "REPARE feature", f"{artefacts.cas}_steps.py": "REPARE steps"}
        return ba.Artefacts(artefacts.cas, artefacts.essai, fichiers=fichiers, cout_usd=cout, module=artefacts.module,
                            resume=resume)

    reparer.appels = appels
    return reparer


def lancer(jouer, reparer=None, **options):
    options.setdefault("defauts_connus", DEFAUTS)
    return ba.executer_campagne(SPECS, ATTENDUS, 1, generer, jouer, reparer=reparer, **options)


CASSE = {"saine": "technical_error", "total_faux": "technical_error"}


def test_une_erreur_technique_sur_la_saine_est_reparee_puis_rejouee_sur_toutes_les_variantes():
    jouer = jouer_factory(CASSE, {"saine": "conforme", "total_faux": "non_conforme"})
    rep = reparateur()

    camp = lancer(jouer, rep)
    apres = ba.calculer_indicateurs(camp)["apres_reparation"]

    assert len(rep.appels) == 1 and rep.appels[0].verdict == "technical_error"
    assert [o.variante for o in camp.observations_reparees] == ["saine", "total_faux"]
    assert (apres["reparations"]["tentees"], apres["reparations"]["rejouables"]) == (1, 1)
    assert apres["reparations"]["saine_conforme_apres"] == 1
    assert apres["faux_verts"]["k"] == 0 and apres["faux_verts"]["n"] == 1
    assert apres["pass_execution"]["pass_at_1"]["k"] == 1  # avant réparation : 0
    assert ba.calculer_indicateurs(camp)["pass_execution"]["pass_at_1"]["k"] == 0  # l'« avant » n'est pas touché


def test_l_agent_de_reparation_ne_recoit_que_l_echec_observe():
    rep = reparateur()
    lancer(jouer_factory(CASSE, {"saine": "conforme", "total_faux": "non_conforme"}), rep)

    jeu = rep.appels[0]
    assert jeu.trace["echecs"][0]["raw"] == "Locator.click: Timeout" and jeu.trace["scenarios"][0]["status"] == "error"


def test_un_non_conforme_ou_un_conforme_sur_la_saine_n_est_jamais_repare():
    """Falsifiable : réparer un `non_conforme` ferait « corriger » le test pour qu'il cesse d'accuser l'application."""
    for verdict_saine in ("non_conforme", "conforme", "blocked", "indetermine"):
        rep = reparateur()
        lancer(jouer_factory({"saine": verdict_saine, "total_faux": "non_conforme"}, {}), rep)
        assert rep.appels == [], verdict_saine


def test_une_reparation_qui_fait_passer_le_test_partout_est_un_faux_vert():
    """Falsifiable : le risque central — l'agent « répare » en supprimant ce qui vérifiait. Le défaut n'est plus détecté."""
    jouer = jouer_factory(CASSE, {"saine": "conforme", "total_faux": "conforme"})

    camp = lancer(jouer, reparateur())
    indicateurs = ba.calculer_indicateurs(camp)

    assert indicateurs["apres_reparation"]["faux_verts"]["k"] == 1
    assert indicateurs["faux_verts"]["k"] == 0  # avant réparation : aucun
    assert ba.code_de_sortie(indicateurs, camp) == 1


def test_une_reparation_inexploitable_ou_qui_leve_n_est_jamais_prise_pour_un_succes():
    jouer = jouer_factory(CASSE, {})
    camp = lancer(jouer, reparateur(ok=False))
    apres = ba.calculer_indicateurs(camp)["apres_reparation"]

    assert camp.observations_reparees == [] and camp.reparations[0].rejouable is False
    assert apres["pass_execution"]["pass_at_1"]["k"] == 0 and apres["reparations"]["rejouables"] == 0

    def casse(_a, _j):
        raise RuntimeError("le moteur est tombé")

    camp = lancer(jouer_factory(CASSE, {}), casse)
    assert camp.reparations[0].tentee and not camp.reparations[0].rejouable
    assert any("le moteur est tombé" in a for a in camp.anomalies)


def test_le_cout_de_la_reparation_compte_dans_le_plafond():
    """Falsifiable : plafond 0,25 $, génération 0,10, estimation 0,10 → après la génération (0,10) la réparation (0,10)
    laisse 0,05 : la campagne s'arrête AVANT l'essai suivant au lieu de l'ignorer."""
    specs = ["a", "b"]
    attendus = ATTENDUS + [ba.Attendu("b", "saine", "conforme"), ba.Attendu("b", "total_faux", "non_conforme")]
    jouer = jouer_factory(CASSE, {"saine": "conforme", "total_faux": "non_conforme"})

    camp = ba.executer_campagne(specs, attendus, 1, generer, jouer, defauts_connus=DEFAUTS, reparer=reparateur(cout=0.10),
                                plafond_usd=0.25, cout_estime_essai=0.10)

    assert camp.interrompue and [e.cas for e in camp.essais] == ["a"]
    assert camp.reparations and camp.reparations[0].cout_usd == 0.10


def test_une_reparation_non_tentee_faute_de_budget_est_dite():
    jouer = jouer_factory(CASSE, {})
    camp = ba.executer_campagne(SPECS, ATTENDUS, 1, generer, jouer, defauts_connus=DEFAUTS, reparer=reparateur(),
                                plafond_usd=0.10, cout_estime_essai=0.10)

    assert camp.reparations[0].tentee is False and "plafond" in camp.reparations[0].motif


def test_sans_reparation_demandee_le_rapport_ne_change_pas():
    jouer = jouer_factory({"saine": "conforme", "total_faux": "non_conforme"}, {})
    camp = lancer(jouer)
    indicateurs = ba.calculer_indicateurs(camp)

    assert indicateurs["apres_reparation"] is None and "Après UNE réparation" not in ba.rendre_markdown(camp, indicateurs, {})


def test_le_rapport_montre_l_avant_et_l_apres_et_le_cout():
    camp = lancer(jouer_factory(CASSE, {"saine": "conforme", "total_faux": "non_conforme"}), reparateur(cout=0.08))
    md = ba.rendre_markdown(camp, ba.calculer_indicateurs(camp), {"date": "2026-10-08"})

    assert "Après UNE réparation" in md and "Avant réparation" in md and "0.080 $" in md


# ── Pièces pures du réparateur réel ───────────────────────────────────────────────────────────────────────


def _origine():
    return ba.Artefacts("a", 1, fichiers={"m.feature": "F", "m_steps.py": "S"}, cout_usd=0.1, module="m")


@pytest.mark.parametrize("rapport, rejouable, mot", [
    ({"changed": True, "dry_run_passed": True, "feature_content": "F2", "steps_content": "S2", "cost_usd": 0.07}, True, ""),
    ({"changed": False, "cost_usd": 0.03}, False, "rien réécrit"),
    ({"changed": True, "dry_run_passed": False, "stopped_reason": "incomplete", "cost_usd": 0.05}, False, "essai à blanc"),
    ({"changed": True, "dry_run_passed": True, "feature_content": "F2", "steps_content": "", "cost_usd": 0.05}, False, "vide"),
    ({"error": "boom", "error_type": "ValueError"}, False, "ValueError"),
])
def test_artefacts_depuis_reparation(rapport, rejouable, mot):
    res = ba.artefacts_depuis_reparation(_origine(), rapport)

    assert (res.genere_ok and bool(res.fichiers)) is rejouable
    assert mot in res.erreur
    if rejouable:
        assert res.fichiers == {"m.feature": "F2", "m_steps.py": "S2"} and res.cout_usd == 0.07


def test_un_cout_non_consigne_reste_non_consigne():
    res = ba.artefacts_depuis_reparation(_origine(), {"changed": False})

    assert res.cout_usd is None


def test_l_entree_de_l_agent_porte_les_fichiers_et_l_echec_brut():
    rep = ba.ReparateurReel(application=None, project_id=7, url="http://127.0.0.1:1", data_dir=Path("."), cle_secrete="k",
                            reste_usd=lambda: 1.0)
    entree = rep.entree(_origine(), ba.Jeu("technical_error", detail="Timeout",
                                           trace={"scenarios": [{"name": "S", "status": "error"}], "echecs": [{"raw": "X"}]}))

    assert entree["feature_content"] == "F" and entree["steps_content"] == "S" and entree["echecs"] == [{"raw": "X"}]
    sans_trace = rep.entree(_origine(), ba.Jeu("technical_error", detail="Timeout"))
    assert sans_trace["echecs"][0]["raw"] == "Timeout"  # repli : au moins le message, jamais une entrée vide


def test_la_commande_de_reparation_transmet_le_reste_du_budget_et_le_mode():
    rep = ba.ReparateurReel(application=None, project_id=7, url="http://127.0.0.1:1", data_dir=Path("."), cle_secrete="k",
                            reste_usd=lambda: 0.4321)
    commande = rep.commande("sortie", Path("e.json"))

    assert "--reparer-depuis" in commande and commande[commande.index("--max-cost-usd") + 1] == "0.4321"
    assert commande[commande.index("--expected-base-url") + 1] == "http://127.0.0.1:1"


def test_sous_pytest_la_reparation_reelle_est_refusee(tmp_path):
    """La barrière de dépense : un test ne peut jamais lancer un VRAI agent de réparation (incident du 2026-10-07)."""

    class App:
        def reinitialiser(self, _d):
            pass

    rep = ba.ReparateurReel(App(), 7, "http://127.0.0.1:1", tmp_path, "k", lambda: 1.0, racine=tmp_path)

    with pytest.raises(Exception, match="(?i)pytest|dépense|refus"):
        rep(_origine(), ba.Jeu("technical_error"))


# ── Rejeu de générations déjà faites (aucun coût de génération) ────────────────────────────────────────────


def _ecrire_campagne(dossier, cas, essai, rapports):
    import json

    repertoire = dossier / f"banc-agents-{cas}-t{essai}"
    repertoire.mkdir(parents=True)
    (repertoire / "campagne.json").write_text(json.dumps(rapports), encoding="utf-8")


def _rapport(module="m", ok=True):
    return {"generation": {"module_name": module, "success": ok, "dry_run_passed": ok, "cost_usd": 0.11,
                           "feature_content": "F", "steps_content": "S"}}


def test_le_rejeu_relit_les_tests_deja_generes_sans_cout_de_generation(tmp_path):
    _ecrire_campagne(tmp_path, "a", 1, [_rapport()])

    art = ba.GenerateurDepuisDisque(tmp_path)("a", 1)

    assert art.genere_ok and set(art.fichiers) == {"m.feature", "m_steps.py"} and art.cout_usd == 0.0 and art.module == "m"


def test_le_rejeu_reproduit_une_generation_echouee_et_une_generation_absente(tmp_path):
    """Falsifiable : une génération passée en échec reste un échec ; un dossier absent n'est jamais un test « vide » réussi."""
    _ecrire_campagne(tmp_path, "a", 1, [_rapport(ok=False)])
    _ecrire_campagne(tmp_path, "a", 2, [])

    assert ba.GenerateurDepuisDisque(tmp_path)("a", 1).genere_ok is False
    assert "vide" in ba.GenerateurDepuisDisque(tmp_path)("a", 2).erreur
    absente = ba.GenerateurDepuisDisque(tmp_path)("a", 3)
    assert absente.genere_ok is False and "absent" in absente.erreur


def test_une_campagne_rejouee_puis_reparee_de_bout_en_bout(tmp_path):
    _ecrire_campagne(tmp_path, "a", 1, [_rapport(module="a")])
    jouer = jouer_factory(CASSE, {"saine": "conforme", "total_faux": "non_conforme"})

    camp = ba.executer_campagne(SPECS, ATTENDUS, 1, ba.GenerateurDepuisDisque(tmp_path), jouer, defauts_connus=DEFAUTS,
                                reparer=reparateur(), plafond_usd=1.0, cout_estime_essai=0.1)

    assert camp.essais[0].cout_usd == 0.0 and len(camp.observations_reparees) == 2


def test_la_trace_de_l_echec_transmet_l_adresse_de_la_page_a_l_agent_de_reparation():
    """Falsifiable : la première mesure avec l'adresse (2026-10-08) ne la transmettait PAS -- l'agent ne l'a jamais reçue."""
    from types import SimpleNamespace

    echec = SimpleNamespace(scenario_name="S", step_text="Quand a", raw="boom", traceback_summary="", page_url="http://h/panier")
    resultat = SimpleNamespace(real_run=SimpleNamespace(scenarios=[SimpleNamespace(name="S", status="failed")], failures=[echec]))

    trace = ba.trace_de_l_echec(resultat)

    assert trace["echecs"][0]["page_url"] == "http://h/panier"
    assert trace["echecs"][0]["raw"] == "boom"
    sans_adresse = SimpleNamespace(scenario_name="S", step_text="Quand a", raw="boom", traceback_summary="")
    assert ba.trace_de_l_echec(SimpleNamespace(real_run=SimpleNamespace(scenarios=[], failures=[sans_adresse])))["echecs"][0]["page_url"] == ""
