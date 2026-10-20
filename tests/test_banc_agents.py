"""Lot Q2-d — `scripts/banc_agents.py` : l'orchestrateur du banc d'agents web, prouvé AVEC DES DOUBLURES.

Aucun test ici n'appelle un LLM, un navigateur ou un réseau extérieur : `generer` et `jouer` sont injectés. Seul
`ApplicationLocale` parle à l'application de `banc/app_web/` — dans un thread, sur le bouclage, comme les tests du lot Q2-b.

Ce que ces tests fixent (et qui échouerait si la règle était fausse) :
- un FAUX VERT est compté et fait sortir le code 1 ; un `technical_error` sous défaut ne l'améliore pas ;
- pass^k < pass@1 sur un jeu construit ; « non mesuré » n'est JAMAIS 0 % ;
- le plafond de coût arrête AVANT le dépassement ;
- le MÊME test est joué partout (empreintes sha256), la génération n'est faite qu'une fois par (cas, essai) ;
- un attendu incohérent est REFUSÉ, jamais ignoré en silence (écart relevé par Q2-a).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("banc_agents", RACINE / "scripts" / "banc_agents.py")
ba = importlib.util.module_from_spec(_spec)
sys.modules["banc_agents"] = ba
_spec.loader.exec_module(ba)
stats = ba.stats


# ── Doublures ────────────────────────────────────────────────────────────────────────────────────────────

SPECS = ["a", "b"]
ATTENDUS = [
    ba.Attendu("a", "saine", "conforme"),
    ba.Attendu("a", "total_faux", "non_conforme"),
    ba.Attendu("b", "saine", "conforme"),
    ba.Attendu("b", "filtre_ignore", "non_conforme"),
]
DEFAUTS = ["total_faux", "filtre_ignore"]
JEUX_PAR_ESSAI = 4  # a : saine + total_faux ; b : saine + filtre_ignore


class Monde:
    """Un agent et un verdict simulés. Par défaut PARFAITS : conforme sur la saine, non_conforme sous défaut.

    `verdicts` : `(cas, variante, essai) -> verdict` pour fabriquer un jeu précis. `cout` : coût d'une génération.
    """

    def __init__(self, verdicts=None, cout=0.10, genere_ok=None):
        self.verdicts = verdicts or {}
        self.cout = cout
        self.genere_ok = genere_ok or (lambda cas, essai: True)
        self.appels_generer: list[tuple[str, int]] = []
        self.appels_jouer: list[tuple[str, int, str, dict]] = []

    def generer(self, cas, essai):
        self.appels_generer.append((cas, essai))
        if not self.genere_ok(cas, essai):
            return ba.Artefacts(cas, essai, cout_usd=self.cout, genere_ok=False, erreur="dry-run non passé")
        fichiers = {f"{cas}.feature": f"Feature: {cas} essai {essai}", f"{cas}_steps.py": f"# steps {cas} {essai}"}
        return ba.Artefacts(cas, essai, fichiers=fichiers, cout_usd=self.cout, module=cas)

    def jouer(self, artefacts, variante):
        self.appels_jouer.append((artefacts.cas, artefacts.essai, variante, artefacts.empreintes))
        parfait = "conforme" if variante == "saine" else "non_conforme"
        verdict = self.verdicts.get((artefacts.cas, variante, artefacts.essai), parfait)
        return ba.Jeu(verdict=verdict, empreintes=artefacts.empreintes)


def campagne(monde, k=1, **options):
    options.setdefault("defauts_connus", DEFAUTS)
    return ba.executer_campagne(SPECS, ATTENDUS, k, monde.generer, monde.jouer, **options)


def observation(camp, cas, variante, essai=1):
    return next(o for o in camp.observations if (o.cas, o.variante, o.essai) == (cas, variante, essai))


# ── Faux verts, faux rouges, non concluants ──────────────────────────────────────────────────────────────


def test_un_faux_vert_est_compte_et_fait_sortir_le_code_1():
    """Falsifiable : si le faux vert n'était pas lu depuis (variante défectueuse, attendu non_conforme, obtenu conforme),
    ce jeu — un test qui laisse passer un défaut — sortirait en 0."""
    monde = Monde({("a", "total_faux", 1): "conforme"})
    camp = campagne(monde)
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_verts"]["k"] == 1
    assert ind["faux_verts"]["n"] == 2  # a/total_faux et b/filtre_ignore, tous deux concluants
    assert ind["par_defaut"]["total_faux"]["faux_verts"] == 1
    assert ba.code_de_sortie(ind, camp) == 1


def test_un_faux_vert_prime_sur_une_campagne_incomplete():
    monde = Monde({("a", "total_faux", 1): "conforme"})
    camp = campagne(monde, k=3, plafond_usd=0.25, cout_estime_essai=0.0)  # arrêtée par le plafond
    ind = ba.calculer_indicateurs(camp)

    assert camp.interrompue
    assert ba.code_de_sortie(ind, camp) == 1


def test_un_faux_rouge_est_compte_sur_la_saine_sans_faire_sortir_en_1():
    monde = Monde({("a", "saine", 1): "non_conforme"})
    camp = campagne(monde)
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_rouges"]["k"] == 1 and ind["faux_rouges"]["n"] == 2
    assert ind["faux_verts"]["k"] == 0
    assert ba.code_de_sortie(ind, camp) == 0  # le faux rouge est rapporté (écart), la porte dure est le faux vert
    assert any(e["variante"] == "saine" and e["obtenu"] == "non_conforme" for e in ind["ecarts"])


def test_un_test_casse_qui_echoue_partout_n_est_pas_une_detection_fiable():
    """Falsifiable : un test cassé (faux rouge sur la saine) échoue AUSSI sous défaut ; le compter comme détection ferait
    croire que l'agent a trouvé le défaut. La détection fiable exige la saine du MÊME essai conforme."""
    monde = Monde({("a", "saine", 1): "non_conforme"})  # a est cassé : non_conforme partout ; b est parfait
    ind = ba.calculer_indicateurs(campagne(monde))
    d_a, d_b = ind["par_defaut"]["total_faux"], ind["par_defaut"]["filtre_ignore"]

    assert d_a["detectes"] == 1 and d_a["detectes_fiables"] == 0
    assert d_b["detectes"] == 1 and d_b["detectes_fiables"] == 1


def test_une_cle_dupliquee_dans_un_yaml_est_refusee(tmp_path):
    """Falsifiable : PyYAML garde la DERNIÈRE valeur sans rien dire — un attendu changerait sans trace."""
    f = tmp_path / "attendus.yaml"
    f.write_text("\n".join(["saine:", "  a: conforme", "  a: failed", ""]), encoding="utf-8")

    with pytest.raises(ba.ConfigurationInvalide, match="deux fois"):
        ba.charger_yaml(f)
    f.write_text("\n".join(["saine:", "  a: conforme", "  b: conforme", ""]), encoding="utf-8")
    assert ba.charger_yaml(f) == {"saine": {"a": "conforme", "b": "conforme"}}


def test_un_technical_error_sous_defaut_n_ameliore_pas_le_taux_de_faux_verts():
    """Falsifiable : retirer le `technical_error` du calcul sans le dire ferait passer 1/2 à 1/1 (pire) ou à 0/1 (meilleur).
    Ici le jeu non concluant reste COMPTÉ à part, le taux ne bouge pas, et il est affiché à côté du taux."""
    avec_erreur = Monde({("a", "total_faux", 1): "conforme", ("b", "filtre_ignore", 1): "technical_error"})
    sans_erreur = Monde({("a", "total_faux", 1): "conforme", ("b", "filtre_ignore", 1): "non_conforme"})
    ind_err = ba.calculer_indicateurs(campagne(avec_erreur))
    ind_ok = ba.calculer_indicateurs(campagne(sans_erreur))

    assert ind_err["faux_verts"]["k"] == 1  # le faux vert n'est pas masqué par l'erreur de l'autre jeu
    assert ind_err["faux_verts"]["n"] == 1 and ind_err["faux_verts"]["non_concluants"] == 1
    assert ind_err["faux_verts"]["taux"] == 1.0  # jamais « amélioré » en passant l'erreur pour un succès
    assert ind_ok["faux_verts"]["taux"] == 0.5
    assert "1 non concluant" in stats.formater_taux(1, 1, ind_err["faux_verts"]["non_concluants"])
    assert ind_err["non_concluants"] == {"technical_error": 1}


def test_si_tous_les_jeux_sous_defaut_sont_en_erreur_technique_la_porte_n_est_pas_verte():
    monde = Monde({(c, d, 1): "technical_error" for c, d in (("a", "total_faux"), ("b", "filtre_ignore"))})
    camp = campagne(monde)
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_verts"]["n"] == 0 and ind["faux_verts"]["taux"] is None  # « non mesuré », pas 0 %
    assert ind["faux_verts"]["non_concluants"] == 2
    assert ba.code_de_sortie(ind, camp) == 3  # jamais 0 : rien n'a été prouvé


@pytest.mark.parametrize("verdict", ["blocked", "indetermine", "technical_error"])
def test_blocked_et_indetermine_sont_non_concluants_pas_des_succes(verdict):
    camp = campagne(Monde({("a", "total_faux", 1): verdict}))
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_verts"]["non_concluants"] == 1
    assert ind["non_concluants"] == {verdict: 1}
    assert ind["pass_resultat"]["pass_at_1"]["k"] == 1  # seul b est juste partout : a n'est pas compté comme réussi


# ── pass@1, pass^k ───────────────────────────────────────────────────────────────────────────────────────


def test_pass_hat_k_est_strictement_inferieur_a_pass_at_1_sur_un_jeu_construit():
    """a : réussit aux essais 1 et 3, échoue au 2 ; b : réussit toujours. pass@1 = 2/2 mais pass^3 = 1/2."""
    monde = Monde({("a", "saine", 2): "technical_error"})
    ind = ba.calculer_indicateurs(campagne(monde, k=3))

    execution = ind["pass_execution"]
    assert execution["pass_at_1"]["k"] == 2 and execution["pass_at_1"]["n"] == 2
    assert execution["pass_hat_k"]["k"] == 1 and execution["pass_hat_k"]["n"] == 2
    assert execution["pass_hat_k"]["taux"] < execution["pass_at_1"]["taux"] < 1.0 + 1e-9
    assert execution["pass_at_k"]["k"] == 2  # au moins un essai réussi pour chaque cas


def test_pass_au_sens_du_resultat_exige_l_attendu_sur_chaque_variante():
    """Le test généré s'exécute bien (pas d'erreur technique) mais rate le défaut : pass@1 exécution = 100 %, résultat = 50 %."""
    monde = Monde({("a", "total_faux", 1): "conforme"})
    ind = ba.calculer_indicateurs(campagne(monde))

    assert ind["pass_execution"]["pass_at_1"]["k"] == 2
    assert ind["pass_resultat"]["pass_at_1"]["k"] == 1 and ind["pass_resultat"]["pass_at_1"]["n"] == 2


def test_une_generation_echouee_est_un_echec_et_ses_jeux_sont_non_concluants_pas_retires():
    monde = Monde(genere_ok=lambda cas, essai: cas != "a")
    camp = campagne(monde)
    ind = ba.calculer_indicateurs(camp)

    assert [o.obtenu for o in camp.observations if o.cas == "a"] == ["technical_error", "technical_error"]
    assert all(o.cause == "generation_echouee" for o in camp.observations if o.cas == "a")
    assert ind["pass_execution"]["pass_at_1"]["k"] == 1 and ind["pass_execution"]["pass_at_1"]["n"] == 2
    assert ind["faux_verts"]["non_concluants"] == 1  # a/total_faux : jamais jugé, jamais effacé
    assert [c for c, *_ in monde.appels_jouer] == ["b", "b"]  # on ne rejoue pas un test qui n'existe pas


# ── Réutilisation de la génération, empreintes ───────────────────────────────────────────────────────────


def test_la_meme_generation_est_reutilisee_pour_la_saine_et_chaque_defaut():
    """generer : UNE fois par (cas, essai) ; jouer : 1 + nombre de défauts listés pour ce cas."""
    monde = Monde()
    campagne(monde, k=3)

    assert monde.appels_generer == [(c, t) for t in (1, 2, 3) for c in SPECS]  # essai par essai, une fois chacun
    assert len(monde.appels_generer) == len(SPECS) * 3
    assert len(monde.appels_jouer) == JEUX_PAR_ESSAI * 3
    par_essai = {}
    for cas, essai, variante, _ in monde.appels_jouer:
        par_essai.setdefault((cas, essai), []).append(variante)
    assert par_essai[("a", 1)] == ["saine", "total_faux"]  # la saine d'abord
    assert par_essai[("b", 2)] == ["saine", "filtre_ignore"]


def test_les_empreintes_des_fichiers_joues_sont_celles_de_la_generation():
    monde = Monde()
    camp = campagne(monde, k=2)

    assert all(o.empreinte_ok is True for o in camp.observations)
    # Tous les jeux d'un même (cas, essai) ont reçu les MÊMES empreintes, celles consignées pour la génération.
    for essai in camp.essais:
        vues = {tuple(sorted(e.items())) for c, t, _, e in monde.appels_jouer if (c, t) == (essai.cas, essai.essai)}
        assert vues == {tuple(sorted(essai.empreintes.items()))}
        assert all(len(h) == 64 for h in essai.empreintes.values())  # sha256 hexadécimal
    # Deux essais du même cas ne sont PAS le même test : leurs empreintes diffèrent.
    a1, a2 = (next(e for e in camp.essais if (e.cas, e.essai) == ("a", t)) for t in (1, 2))
    assert a1.empreintes != a2.empreintes
    assert ba.calculer_indicateurs(camp)["integrite"] == {"verifiees": len(camp.observations), "divergentes": 0,
                                                         "non_rapportees": 0}


def test_un_jeu_dont_les_empreintes_divergent_est_ecarte_et_signale():
    """Falsifiable : si un jeu modifiait le test en route, son verdict ne se comparerait plus à celui de la saine. Même un
    `conforme` sous défaut ne doit alors PAS être compté comme faux vert (ni comme vert) : écarté, dit, code 3."""

    class Modificateur(Monde):
        def jouer(self, artefacts, variante):
            jeu = super().jouer(artefacts, variante)
            if (artefacts.cas, variante) == ("a", "total_faux"):
                jeu.verdict = "conforme"
                jeu.empreintes = {nom: "0" * 64 for nom in artefacts.fichiers}  # le test a changé
            return jeu

    camp = campagne(Modificateur())
    ind = ba.calculer_indicateurs(camp)
    o = observation(camp, "a", "total_faux")

    assert (o.obtenu, o.cause, o.empreinte_ok) == ("technical_error", "empreinte_divergente", False)
    assert ind["faux_verts"]["k"] == 0 and ind["faux_verts"]["non_concluants"] == 1
    assert ind["integrite"]["divergentes"] == 1
    assert any("empreintes" in a for a in camp.anomalies)
    assert ba.code_de_sortie(ind, camp) == 3


def test_des_empreintes_non_rapportees_sont_comptees_a_part_pas_validees():
    class Muet(Monde):
        def jouer(self, artefacts, variante):
            return ba.Jeu(verdict="conforme" if variante == "saine" else "non_conforme")

    ind = ba.calculer_indicateurs(campagne(Muet()))

    assert ind["integrite"]["verifiees"] == 0 and ind["integrite"]["non_rapportees"] == JEUX_PAR_ESSAI


# ── Plafond de coût, en amont ────────────────────────────────────────────────────────────────────────────


def test_le_plafond_de_cout_arrete_avant_le_depassement_pas_apres():
    """Plafond 0,25 $ à 0,10 $ la génération : 2 essais lancés (0,20 $) ; le 3e porterait à 0,30 $ > 0,25 $ → AVANT."""
    monde = Monde(cout=0.10)
    camp = campagne(monde, k=3, plafond_usd=0.25)

    assert len(monde.appels_generer) == 2
    assert "plafond de coût" in camp.interrompue and "avant" in camp.interrompue
    cout_total = ba.calculer_indicateurs(camp)["cout"]["total_usd"]
    assert cout_total == pytest.approx(0.20) and cout_total <= 0.25  # jamais au-dessus du plafond


def test_le_plafond_ne_se_contente_pas_d_un_cumul_deja_atteint():
    """Le cumul 0,20 $ est SOUS le plafond 0,25 $, mais le plus cher essai observé (0,10 $) le ferait passer au-dessus."""
    assert ba.raison_d_arret(0.20, 0.10, 0.25) != ""
    assert ba.raison_d_arret(0.10, 0.10, 0.25) == ""
    assert ba.raison_d_arret(0.0, 0.0, 0.25, cout_estime=0.30) != ""  # le tout premier essai : coût estimé
    assert ba.raison_d_arret(0.0, 0.0, None) == ""
    assert ba.raison_d_arret(0.25, 0.0, 0.25) != ""  # cumul == plafond : jamais d'essai de plus


def test_l_estimation_empeche_de_lancer_le_premier_essai_au_dessus_du_plafond():
    monde = Monde()
    camp = campagne(monde, plafond_usd=0.10, cout_estime_essai=0.15)

    assert monde.appels_generer == []
    assert camp.interrompue and camp.essais == []


def test_l_ordre_essai_par_essai_garde_pass_at_1_sur_le_corpus_entier_quand_le_plafond_arrete():
    monde = Monde(cout=0.10)
    camp = campagne(monde, k=3, plafond_usd=0.25)  # 2 essais lancés sur 6 prévus
    ind = ba.calculer_indicateurs(camp)

    assert monde.appels_generer == [("a", 1), ("b", 1)]  # essai 1 sur TOUS les cas avant l'essai 2
    assert ind["pass_execution"]["pass_at_1"]["n"] == 2
    assert ind["pass_execution"]["pass_hat_k"]["n"] == 0 and ind["pass_execution"]["pass_hat_k"]["taux"] is None
    assert ind["pass_execution"]["pass_hat_k"]["non_mesures"] == 2  # pass^3 : non mesuré, pas 0 %
    assert ba.code_de_sortie(ind, camp) == 3


def test_le_plafond_est_obligatoire_en_mode_reel():
    with pytest.raises(ba.ConfigurationInvalide, match="OBLIGATOIRE"):
        campagne(Monde(), reel=True, plafond_usd=None)
    campagne(Monde(), reel=True, plafond_usd=5.0)  # avec un plafond : accepté


def test_un_arret_demande_par_la_generation_n_est_pas_un_echec_de_l_agent():
    """Crédits épuisés : l'essai n'est PAS retenu (il ne mesure pas l'agent), la campagne est dite incomplète."""

    def generer(cas, essai):
        if (cas, essai) == ("b", 1):
            raise ba.ArretCampagne("crédits API insuffisants")
        return Monde().generer(cas, essai)

    camp = ba.executer_campagne(SPECS, ATTENDUS, 1, generer, Monde().jouer, defauts_connus=DEFAUTS)

    assert "crédits API insuffisants" in camp.interrompue
    assert [e.cas for e in camp.essais] == ["a"]  # b n'est pas retenu comme échec
    assert all(o.cas == "a" for o in camp.observations)


# ── Coût en USD et EUR ───────────────────────────────────────────────────────────────────────────────────


def test_le_cout_est_rapporte_en_dollars_et_en_euros_avec_le_taux_fourni():
    ind = ba.calculer_indicateurs(campagne(Monde(cout=0.108), k=2), taux_eur_usd=1.08)
    cout = ind["cout"]

    assert cout["generations"] == 4 and cout["total_usd"] == pytest.approx(0.432)
    assert cout["total_eur"] == pytest.approx(0.4)  # 0,432 $ / 1,08
    assert cout["par_generation_usd"] == pytest.approx(0.108) and cout["par_generation_eur"] == pytest.approx(0.1)
    assert cout["par_cas_usd"] == {"a": pytest.approx(0.108), "b": pytest.approx(0.108)}


def test_un_cout_non_consigne_n_est_pas_compte_comme_zero():
    class SansCout(Monde):
        def generer(self, cas, essai):
            artefacts = super().generer(cas, essai)
            artefacts.cout_usd = None if cas == "a" else artefacts.cout_usd
            return artefacts

    camp = campagne(SansCout())
    cout = ba.calculer_indicateurs(camp, 1.08)["cout"]

    assert cout["generations_sans_cout_consigne"] == 1
    assert cout["par_cas_usd"]["a"] is None and cout["par_cas_usd"]["b"] == pytest.approx(0.10)  # « non mesuré », pas 0
    assert cout["par_generation_usd"] == pytest.approx(0.10)  # moyenne sur les générations dont le coût est connu
    assert any("coût de génération non consigné" in a for a in camp.anomalies)


def test_la_fonction_cout_injectee_remplace_celle_des_artefacts():
    camp = campagne(Monde(cout=0.10), cout=lambda artefacts: 0.5)
    assert ba.calculer_indicateurs(camp)["cout"]["total_usd"] == pytest.approx(1.0)


# ── Protections du harnais ───────────────────────────────────────────────────────────────────────────────


def test_un_jeu_qui_leve_devient_un_technical_error_et_la_campagne_continue():
    class Fragile(Monde):
        def jouer(self, artefacts, variante):
            if (artefacts.cas, variante) == ("a", "total_faux"):
                raise TimeoutError("navigateur planté")
            return super().jouer(artefacts, variante)

    camp = campagne(Fragile())
    o = observation(camp, "a", "total_faux")

    assert (o.obtenu, o.cause) == ("technical_error", "jeu_en_exception") and "TimeoutError" in o.detail
    assert len(camp.observations) == JEUX_PAR_ESSAI  # les autres jeux ont bien eu lieu


def test_un_verdict_inconnu_est_rendu_en_technical_error_et_signale():
    camp = campagne(Monde({("a", "saine", 1): "vert"}))

    assert observation(camp, "a", "saine").obtenu == "technical_error"
    assert any("verdict inconnu 'vert'" in a for a in camp.anomalies)


def test_jouer_peut_rendre_un_verdict_nu():
    camp = ba.executer_campagne(SPECS, ATTENDUS, 1, Monde().generer, lambda a, v: "conforme" if v == "saine" else "non_conforme",
                                defauts_connus=DEFAUTS)
    assert camp.observations[0].obtenu == "conforme" and camp.observations[0].empreinte_ok is None


@pytest.mark.parametrize(
    ("execution", "fonctionnel", "attendu"),
    [
        ("success", "conforme", "conforme"),
        ("success", "non_conforme", "non_conforme"),
        ("technical_error", "non_conforme", "non_conforme"),  # le fonctionnel prime, comme statut_de_test
        ("blocked", "indetermine", "blocked"),
        ("technical_error", "indetermine", "technical_error"),
        ("success", "indetermine", "indetermine"),
        ("success", None, "indetermine"),  # jamais un vert fabriqué par le banc
        ("success", "donnee_invalide", "indetermine"),
        (None, None, "technical_error"),  # aucun signal : jamais un succès
        ("not_executed", None, "technical_error"),
    ],
)
def test_verdict_du_banc_ne_fabrique_jamais_un_vert(execution, fonctionnel, attendu):
    assert ba.verdict_du_banc(execution, fonctionnel) == attendu
    assert ba.verdict_du_banc(execution, fonctionnel) in stats.VERDICTS


# ── Attendus incohérents : refusés, jamais ignorés ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cas", "variante", "attendu"),
    [
        ("a", "saine", "non_conforme"),  # saine : ne compterait ni comme succès ni comme faux rouge
        ("a", "total_faux", "conforme"),  # défaut : sortirait du calcul des faux verts
        ("a", "saine", "passed"),  # statut de lecture au lieu d'un verdict
        ("a", "saine", "blocked"),
    ],
)
def test_un_attendu_de_polarite_impossible_est_refuse_a_la_construction(cas, variante, attendu):
    with pytest.raises(ba.AttenduIncoherent):
        ba.Attendu(cas, variante, attendu)


def test_un_cas_sans_attendu_sur_la_saine_est_refuse_par_l_orchestrateur():
    sans_b = [a for a in ATTENDUS if a.cas != "b"]
    monde = Monde()
    with pytest.raises(ba.ConfigurationInvalide, match="cas sans attendu sur l'application saine : b"):
        ba.executer_campagne(SPECS, sans_b, 1, monde.generer, monde.jouer, defauts_connus=DEFAUTS)
    assert monde.appels_generer == []  # refusé AVANT de dépenser quoi que ce soit


def test_un_code_de_defaut_inconnu_est_refuse_par_l_orchestrateur():
    faute = [*ATTENDUS, ba.Attendu("a", "total_fau", "non_conforme")]  # faute de frappe
    monde = Monde()
    with pytest.raises(ba.ConfigurationInvalide, match="code de défaut inconnu"):
        ba.executer_campagne(SPECS, faute, 1, monde.generer, monde.jouer, defauts_connus=DEFAUTS)
    assert monde.appels_generer == []


def test_un_defaut_que_aucun_cas_ne_liste_est_refuse_il_ne_serait_jamais_exerce():
    monde = Monde()
    with pytest.raises(ba.ConfigurationInvalide, match="défaut login_accepte_tout : aucun cas"):
        ba.executer_campagne(SPECS, ATTENDUS, 1, monde.generer, monde.jouer, defauts_connus=[*DEFAUTS, "login_accepte_tout"])


def test_un_attendu_pour_un_cas_sans_spec_et_un_doublon_sont_refuses():
    problemes = ba.problemes_attendus(SPECS, [*ATTENDUS, ba.Attendu("fantome", "saine", "conforme"), ATTENDUS[0]], DEFAUTS)

    assert any("cas qui n'a pas de spec" in p for p in problemes)
    assert any("écrit 2 fois" in p for p in problemes)


def test_lire_attendus_rapporte_les_polarites_et_statuts_impossibles_au_lieu_de_les_ignorer():
    attendus, problemes = ba.lire_attendus({
        "sain": {"a": "passed", "b": "failed"},  # b : une saine qui « doit échouer » ne se mesure pas
        "defauts": {"total_faux": {"a": "passed"}, "filtre_ignore": {"b": "bof"}, "vide": {}},
    })

    assert [(a.cas, a.variante) for a in attendus] == [("a", "saine")]
    texte = " | ".join(problemes)
    assert "b" in texte and "saine" in texte
    assert "total_faux/a" in texte and "non_conforme" in texte
    assert "statut attendu inconnu 'bof'" in texte
    assert "défaut vide : aucun cas listé" in texte


def test_lire_attendus_exige_une_section_sain_non_vide():
    _, problemes = ba.lire_attendus({"defauts": {"total_faux": {"a": "failed"}}})
    assert any("sain" in p and "ÉQUILIBRÉ" in p for p in problemes)


def test_k_invalide_est_refuse():
    for k in (0, -1, 1.5, True):
        with pytest.raises(ba.ConfigurationInvalide):
            campagne(Monde(), k=k)


# ── Configuration réelle du dépôt ────────────────────────────────────────────────────────────────────────


def test_la_configuration_du_depot_est_coherente_et_l_equilibre_est_la():
    conf = ba.charger_configuration()

    # 2026-10-20 (IT-3e) : 11 specs depuis l'ajout du contrôle d'accès (`acces_age_limite`, défaut `limite_age_decalee`).
    assert len(conf.specs) == 11
    assert {a.cas for a in conf.attendus if a.variante == "saine"} == set(conf.specs)  # jeu équilibré : toutes en saine
    assert {a.variante for a in conf.attendus} - {"saine"} == set(conf.defauts_connus)  # chaque défaut est exercé
    assert all(a.attendu == "conforme" for a in conf.attendus if a.variante == "saine")
    assert all(a.attendu == "non_conforme" for a in conf.attendus if a.variante != "saine")
    assert all(not m["title"].endswith("(banc d'agents web)") for m in conf.specs.values())
    assert conf.defauts_connus == ba.defauts_du_catalogue()  # la vérité vient de l'application, pas d'une copie


def _copie_de_la_configuration(tmp_path):
    import shutil

    dossier = tmp_path / "banc_local"
    shutil.copytree(RACINE / "specs" / "banc_local", dossier)
    return dossier


def _charger_depuis(dossier):
    return ba.charger_configuration(dossier, dossier / "attendus.yaml", dossier / "apps.yaml")


def test_une_configuration_copiee_a_l_identique_est_valide(tmp_path):
    assert len(_charger_depuis(_copie_de_la_configuration(tmp_path)).specs) == 11


def test_falsifiable_un_cas_sans_attendu_dans_le_fichier_est_refuse(tmp_path):
    dossier = _copie_de_la_configuration(tmp_path)
    texte = (dossier / "attendus.yaml").read_text(encoding="utf-8")
    (dossier / "attendus.yaml").write_text(texte.replace("  produits_recherche: passed\n", "", 1), encoding="utf-8")

    with pytest.raises(ba.ConfigurationInvalide, match="cas sans attendu sur l'application saine : produits_recherche"):
        _charger_depuis(dossier)


def test_falsifiable_un_code_de_defaut_inconnu_dans_le_fichier_est_refuse(tmp_path):
    dossier = _copie_de_la_configuration(tmp_path)
    texte = (dossier / "attendus.yaml").read_text(encoding="utf-8")
    (dossier / "attendus.yaml").write_text(texte.replace("\n  total_faux:\n", "\n  total_fau:\n", 1), encoding="utf-8")

    with pytest.raises(ba.ConfigurationInvalide) as erreur:
        _charger_depuis(dossier)
    assert "total_fau/" in str(erreur.value) and "code de défaut inconnu" in str(erreur.value)
    assert "défaut total_faux : aucun cas" in str(erreur.value)  # et le vrai défaut n'est plus exercé


def test_falsifiable_un_attendu_passed_sous_un_defaut_est_refuse_dans_le_fichier(tmp_path):
    dossier = _copie_de_la_configuration(tmp_path)
    texte = (dossier / "attendus.yaml").read_text(encoding="utf-8")
    (dossier / "attendus.yaml").write_text(texte.replace("    produits_recherche: failed", "    produits_recherche: passed", 1),
                                           encoding="utf-8")

    with pytest.raises(ba.ConfigurationInvalide, match="sous un défaut l'attendu ne peut être que `non_conforme`"):
        _charger_depuis(dossier)


def test_falsifiable_une_spec_sans_attendu_et_un_mot_de_passe_en_clair_sont_refuses(tmp_path):
    dossier = _copie_de_la_configuration(tmp_path)
    (dossier / "nouvelle_spec.md").write_text(
        (dossier / "connexion_valide.md").read_text(encoding="utf-8") + "\nMot de passe : motdepasse-test\n", encoding="utf-8")

    with pytest.raises(ba.ConfigurationInvalide) as erreur:
        _charger_depuis(dossier)
    assert "cas sans attendu sur l'application saine : nouvelle_spec" in str(erreur.value)
    assert "spec nouvelle_spec : contient un mot de passe" in str(erreur.value)  # tous les problèmes d'un coup


def test_un_dossier_de_specs_absent_est_refuse(tmp_path):
    with pytest.raises(ba.ConfigurationInvalide, match="introuvable"):
        ba.charger_configuration(tmp_path / "rien", ba.ATTENDUS, ba.APPS)


# ── « Non mesuré » n'est jamais 0 %, rapport ─────────────────────────────────────────────────────────────


def test_n_egal_zero_donne_non_mesure_jamais_zero_pour_cent(tmp_path):
    camp = campagne(Monde(), plafond_usd=0.0)  # plafond 0 : aucun essai lancé
    ind = ba.calculer_indicateurs(camp, 1.08)
    markdown = ba.rendre_markdown(camp, ind, {"date": "2026-10-07", "commit": "abc"})

    for nom in ("faux_verts", "faux_rouges"):
        assert ind[nom]["taux"] is None and ind[nom]["ic95"] is None and ind[nom]["n"] == 0
    for serie in ("pass_execution", "pass_resultat"):
        assert all(d["taux"] is None for d in ind[serie].values())
    assert ind["cout"]["par_generation_usd"] is None and ind["cout"]["total_usd"] == 0
    assert "non mesuré" in markdown and "Campagne INCOMPLÈTE" in markdown
    assert "0,0 %" not in markdown and "0.0 %" not in markdown and "0 %," not in markdown
    assert ba.code_de_sortie(ind, camp) == 3


def test_le_rapport_porte_l_echantillon_les_intervalles_le_cout_et_les_ecarts(tmp_path):
    monde = Monde({("a", "total_faux", 1): "conforme", ("b", "saine", 1): "blocked"}, cout=0.108)
    camp = campagne(monde, k=2)
    ind = ba.calculer_indicateurs(camp, 1.08)
    contexte = {"date": "2026-10-07", "etiquette": "essai", "commit": "abc1234", "modele_generation": "modele-x",
                "versions": {"testpilot": "1", "behave": "2", "playwright": "3"}}

    md, js = ba.ecrire_sortie(camp, ind, contexte, tmp_path)
    texte = md.read_text(encoding="utf-8")
    donnees = json.loads(js.read_text(encoding="utf-8"))

    assert md.name == "banc-agents-2026-10-07-essai.md" and js.name == "banc-agents-2026-10-07-essai.json"
    assert "2 cas × k = 2 essais" in texte and "`modele-x`" in texte and "`abc1234`" in texte
    assert "IC95" in texte  # intervalle de Wilson
    assert "€" in texte and "$" in texte
    assert "Écarts aux attendus" in texte and "blocked" in texte
    assert donnees["indicateurs"]["faux_verts"]["k"] == 1 and donnees["contexte"]["commit"] == "abc1234"
    assert len(donnees["observations"]) == len(camp.observations) == 2 * JEUX_PAR_ESSAI
    assert donnees["essais"][0]["empreintes"]  # l'empreinte du test généré est consignée


def test_un_sous_ensemble_de_cas_est_signale_dans_le_rapport():
    camp = campagne(Monde())
    texte = ba.rendre_markdown(camp, ba.calculer_indicateurs(camp), {"date": "d", "sous_ensemble_de_cas": True})
    assert "Sous-ensemble de cas" in texte and "ne jamais le publier" in texte


def test_budget_estime():
    budget = ba.estimer_budget(10, 3, 0.15, 1.08)
    assert budget["generations"] == 30 and budget["total_usd"] == pytest.approx(4.5)
    assert budget["total_eur"] == pytest.approx(4.1667, abs=1e-3)
    assert ba.estimer_budget(10, 3, 0.15, None)["total_eur"] is None


# ── Mode à sec et garde-fous de la ligne de commande ─────────────────────────────────────────────────────


def _interdire_le_reel(monkeypatch):
    def interdit(*_a, **_k):
        raise AssertionError("le mode à sec ne doit ni générer, ni jouer, ni démarrer l'application")

    monkeypatch.setattr(ba.GenerateurReel, "__call__", interdit)
    monkeypatch.setattr(ba.JoueurReel, "__call__", interdit)
    monkeypatch.setattr(ba.ApplicationLocale, "demarrer", interdit)
    monkeypatch.setattr(ba, "_lancer_reel", interdit)
    monkeypatch.setattr(ba.subprocess, "run", interdit)
    monkeypatch.setattr(ba.urllib.request, "urlopen", interdit)


def test_le_mode_a_sec_valide_sans_rien_lancer_et_affiche_le_budget(monkeypatch, capsys):
    _interdire_le_reel(monkeypatch)

    code = ba.main(["--a-sec", "--essais", "3"])
    sortie = capsys.readouterr().out

    assert code == 0
    assert "Configuration valide : 11 specs" in sortie and "33 générations" in sortie
    assert "rien n'a été généré ni joué" in sortie and "non mesuré sur le web" in sortie


def test_sans_reel_le_mode_par_defaut_est_a_sec(monkeypatch):
    _interdire_le_reel(monkeypatch)
    assert ba.main([]) == 0


def test_reel_exige_un_plafond_de_cout(monkeypatch):
    _interdire_le_reel(monkeypatch)
    with pytest.raises(SystemExit) as sortie:
        ba.main(["--reel"])
    assert sortie.value.code == 2


def test_reel_et_a_sec_s_excluent():
    with pytest.raises(SystemExit) as sortie:
        ba.main(["--reel", "--a-sec", "--plafond-cout", "5"])
    assert sortie.value.code == 2


@pytest.mark.parametrize("hote", ["0.0.0.0", "192.168.1.10", "exemple.fr", "10.0.0.1", ""])
def test_un_hote_non_loopback_est_refuse_avant_tout(hote, monkeypatch):
    _interdire_le_reel(monkeypatch)
    with pytest.raises(ba.ConfigurationInvalide, match="refusé"):
        ba.exiger_loopback(hote)
    assert ba.main(["--reel", "--plafond-cout", "5", "--hote", hote]) == 2


@pytest.mark.parametrize("hote", ["127.0.0.1", "localhost", "::1"])
def test_les_hotes_de_bouclage_sont_acceptes(hote):
    assert ba.exiger_loopback(hote) in ("127.0.0.1", "::1")


def test_le_budget_est_affiche_avant_de_commencer_le_reel(monkeypatch, capsys):
    monkeypatch.setenv("BANC_AGENTS_ISOLE", "1")  # le test tient lieu de processus déjà isolé : pas de relance
    vu = {}

    def faux_lancement(args, configuration, cas, taux):
        vu["sortie_avant"] = capsys.readouterr().out
        return 0

    monkeypatch.setattr(ba, "_lancer_reel", faux_lancement)
    code = ba.main(["--reel", "--plafond-cout", "5", "--essais", "2", "--cas", "connexion_valide,panier_total_tva"])

    assert code == 0
    assert "BUDGET AVANT DÉPART : 4 générations" in vu["sortie_avant"]
    assert "plafond appliqué : 5.0 $" in vu["sortie_avant"]


def test_un_cas_inconnu_en_mise_au_point_est_refuse(monkeypatch):
    _interdire_le_reel(monkeypatch)
    assert ba.main(["--a-sec", "--cas", "inexistant"]) == 2


def test_le_mode_reel_refuse_odoo_env_prod(monkeypatch):
    monkeypatch.setenv("ODOO_ENV", "prod")
    with pytest.raises(ba.ConfigurationInvalide, match="production"):
        ba._isoler_donnees()


# ── Adaptateurs réels, avec doublures (jamais de LLM ni de navigateur) ───────────────────────────────────


def _rapport(**gen):
    base = {"success": True, "dry_run_passed": True, "module_name": "mod_x", "cost_usd": 0.12,
            "feature_content": "Feature: x", "steps_content": "# steps"}
    return {"case_id": 7, "iteration": 1, "generation": {**base, **gen}}


def test_artefacts_depuis_rapport_lit_les_fichiers_et_le_cout():
    artefacts = ba.artefacts_depuis_rapport("a", 2, _rapport())

    assert artefacts.genere_ok and artefacts.module == "mod_x" and artefacts.cout_usd == pytest.approx(0.12)
    assert sorted(artefacts.fichiers) == ["mod_x.feature", "mod_x_steps.py"]
    assert artefacts.fichiers["mod_x.feature"] == "Feature: x"


@pytest.mark.parametrize("gen", [{"success": False}, {"dry_run_passed": False}, {"steps_content": ""}, {"module_name": ""}])
def test_une_generation_sans_essai_a_blanc_ou_incomplete_n_est_pas_jouable(gen):
    artefacts = ba.artefacts_depuis_rapport("a", 1, _rapport(**gen))

    assert not artefacts.genere_ok and artefacts.fichiers == {}
    assert artefacts.erreur and artefacts.cout_usd == pytest.approx(0.12)  # le coût dépensé reste compté


def test_un_cout_absent_du_rapport_reste_non_consigne():
    assert ba.artefacts_depuis_rapport("a", 1, _rapport(cost_usd=None)).cout_usd is None


class AppDouble:
    def __init__(self):
        self.appels: list[list[str]] = []

    def reinitialiser(self, defauts):
        self.appels.append(list(defauts))


def test_le_generateur_reel_transmet_le_reste_du_budget_et_reinitialise_la_saine(tmp_path, monkeypatch):
    # Étape 3 : la mesure « prêt à lancer » a sa propre base jetable — doublée ici (testée dans test_banc_pret_a_lancer).
    monkeypatch.setattr(ba, "evaluer_pret_a_lancer", lambda case_id, gen, data_dir: (True, []))
    app = AppDouble()
    lancements = []

    class Processus:
        returncode = 0

    def lancer(commande, **kw):
        lancements.append(commande)
        sortie = commande[commande.index("--out") + 1]
        dossier = tmp_path / ".local-preview" / "qualification" / sortie
        dossier.mkdir(parents=True)
        (dossier / "campagne.json").write_text(json.dumps([_rapport()]), encoding="utf-8")
        return Processus()

    reste = {"v": 0.37}
    generateur = ba.GenerateurReel(app, {"a": 7}, 3, "http://127.0.0.1:1", tmp_path, "cle", lambda: reste["v"],
                                   lancer=lancer, racine=tmp_path)
    artefacts = generateur("a", 2)

    commande = lancements[0]
    assert app.appels == [[]]  # application SAINE et vierge avant la génération
    assert commande[commande.index("--max-cost-usd") + 1] == "0.3700"
    assert commande[commande.index("--cases") + 1] == "7" and commande[commande.index("--iterations") + 1] == "2"
    assert commande[commande.index("--out") + 1] == "banc-agents-a-t2"
    assert commande[commande.index("--expected-base-url") + 1] == "http://127.0.0.1:1"
    assert artefacts.genere_ok and artefacts.cas == "a" and artefacts.essai == 2
    assert artefacts.pret_a_lancer is True, "la mesure est branchée sur chaque génération réussie"


def test_le_generateur_reel_ignore_un_campagne_json_perime_et_leve_arret_si_le_moteur_s_arrete(tmp_path):
    app = AppDouble()

    class Processus:
        returncode = 3

    def lancer(commande, **kw):
        sortie = commande[commande.index("--out") + 1]
        dossier = tmp_path / ".local-preview" / "qualification" / sortie
        (dossier / "arret_plafond.json").write_text(json.dumps({"raison": "crédits API insuffisants"}), encoding="utf-8")
        return Processus()

    dossier = tmp_path / ".local-preview" / "qualification" / "banc-agents-a-t1"
    dossier.mkdir(parents=True)
    (dossier / "campagne.json").write_text(json.dumps([_rapport()]), encoding="utf-8")  # reste d'un run précédent
    generateur = ba.GenerateurReel(app, {"a": 7}, 3, "http://127.0.0.1:1", tmp_path, "cle", lambda: None,
                                   lancer=lancer, racine=tmp_path)

    with pytest.raises(ba.ArretCampagne, match="crédits API insuffisants"):
        generateur("a", 1)


def test_le_generateur_reel_leve_si_le_moteur_plante_sans_rapport(tmp_path):
    class Processus:
        returncode = 1

    generateur = ba.GenerateurReel(AppDouble(), {"a": 7}, 3, "http://127.0.0.1:1", tmp_path, "cle", lambda: None,
                                   lancer=lambda commande, **kw: Processus(), racine=tmp_path)
    with pytest.raises(RuntimeError, match="a échoué"):
        generateur("a", 1)


def _joueur(tmp_path, executer, app=None):
    return ba.JoueurReel(app or AppDouble(), executer, tmp_path, {"K": "V"}, 3, "web")


def test_le_joueur_reel_regle_les_defauts_joue_les_fichiers_exacts_et_restaure_la_saine(tmp_path):
    app = AppDouble()
    vus = {}

    def executer(dossier, module, connexion, project_id, connector_type, traces):
        vus["fichiers"] = {p.name: p.read_bytes() for p in dossier.iterdir()}
        vus["appels_app_pendant"] = list(app.appels)
        vus.update(module=module, connexion=connexion, project_id=project_id, connector_type=connector_type)
        return {"execution": "success", "fonctionnel": "non_conforme", "cause": "assertion", "detail": "d", "duree": 1.5}

    artefacts = ba.Artefacts("a", 1, {"m.feature": "Feature: é\r\n", "m_steps.py": "x = 1\n"}, 0.1, module="m")
    jeu = _joueur(tmp_path, executer, app)(artefacts, "total_faux")

    assert vus["appels_app_pendant"] == [["total_faux"]]  # défaut posé AVANT l'exécution
    assert app.appels == [["total_faux"], []]  # puis la saine restaurée
    assert vus["fichiers"] == {"m.feature": "Feature: é\r\n".encode(), "m_steps.py": b"x = 1\n"}  # octets exacts
    assert (vus["module"], vus["project_id"], vus["connector_type"], vus["connexion"]) == ("m", 3, "web", {"K": "V"})
    assert jeu.verdict == "non_conforme" and jeu.cause == "assertion"
    assert jeu.empreintes == artefacts.empreintes  # le test joué est celui qui a été généré


def test_le_joueur_reel_joue_la_saine_sans_defaut_et_restaure_meme_si_l_execution_leve(tmp_path):
    app = AppDouble()

    def executer(*_a):
        raise RuntimeError("navigateur absent")

    artefacts = ba.Artefacts("a", 1, {"m.feature": "F", "m_steps.py": "S"}, 0.1, module="m")
    with pytest.raises(RuntimeError, match="navigateur absent"):
        _joueur(tmp_path, executer, app)(artefacts, "saine")

    assert app.appels == [[], []]  # saine = aucun défaut ; et restauration malgré l'exception
    assert list(tmp_path.glob("jeu_*")) == []  # dossier de travail nettoyé


def test_le_joueur_reel_detecte_un_test_modifie_pendant_le_jeu(tmp_path):
    def executer(dossier, *_a):
        (dossier / "m_steps.py").write_text("# modifié en cours de route", encoding="utf-8")
        return {"execution": "success", "fonctionnel": "conforme"}

    artefacts = ba.Artefacts("a", 1, {"m.feature": "F", "m_steps.py": "S"}, 0.1, module="m")
    camp = ba.executer_campagne(["a"], [ba.Attendu("a", "saine", "conforme")], 1, lambda c, t: artefacts,
                                _joueur(tmp_path, executer), defauts_connus=[])

    assert camp.observations[0].obtenu == "technical_error" and camp.observations[0].cause == "empreinte_divergente"


def test_le_pipeline_complet_avec_le_joueur_reel_et_une_execution_simulee(tmp_path):
    """Génération simulée, application double, exécution simulée : l'orchestrateur et l'adaptateur réel s'enchaînent."""
    app = AppDouble()

    def executer(dossier, module, connexion, project_id, connector_type, traces):
        defaut = app.appels[-1]
        return {"execution": "success", "fonctionnel": "non_conforme" if defaut else "conforme"}

    monde = Monde()
    camp = ba.executer_campagne(SPECS, ATTENDUS, 2, monde.generer, _joueur(tmp_path, executer, app), defauts_connus=DEFAUTS)
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_verts"]["k"] == 0 and ind["faux_verts"]["n"] == 4 and ind["faux_rouges"]["n"] == 4
    assert ind["integrite"]["verifiees"] == len(camp.observations) == 2 * JEUX_PAR_ESSAI
    assert ba.code_de_sortie(ind, camp) == 0
    assert app.appels[-1] == []  # l'application est restée saine


# ── L'application locale, en HTTP réel sur bouclage (aucun navigateur) ───────────────────────────────────


def _poster(application, chemin, corps):
    return application._appeler("POST", chemin, corps)


def test_application_locale_bascule_les_defauts_et_remet_a_zero_en_http_reel():
    with ba.ApplicationLocale("127.0.0.1") as application:
        assert application.url.startswith("http://127.0.0.1:")
        application.reinitialiser(["total_faux", "filtre_ignore"])
        assert sorted(application._appeler("GET", "/__defauts")["defauts"]) == ["filtre_ignore", "total_faux"]

        application.reinitialiser([])
        assert application._appeler("GET", "/__defauts")["defauts"] == []
        etat = application._appeler("GET", "/__etat")
        assert etat["commandes"] == [] and etat["enregistrements"] == [] and etat["panier"]["lignes"] == []


def test_application_locale_refuse_une_application_sale_apres_le_reset(monkeypatch):
    """Falsifiable : si /__reset ne remettait pas à zéro, un jeu partirait d'un état hérité du précédent."""
    with ba.ApplicationLocale("127.0.0.1") as application:
        vrai = application._appeler

        def appeler(methode, chemin, corps=None):
            if chemin == "/__etat":
                return {"commandes": [{"numero": 1}], "enregistrements": [], "panier": {"lignes": []}}
            return vrai(methode, chemin, corps)

        monkeypatch.setattr(application, "_appeler", appeler)
        with pytest.raises(RuntimeError, match="état initial"):
            application.reinitialiser([])


def test_application_locale_refuse_une_bascule_qui_n_a_pas_eu_lieu(monkeypatch):
    with ba.ApplicationLocale("127.0.0.1") as application:
        vrai = application._appeler

        def appeler(methode, chemin, corps=None):
            if (methode, chemin) == ("POST", "/__defauts"):
                return {"defauts": []}  # la bascule est « acceptée » mais ne fait rien
            return vrai(methode, chemin, corps)

        monkeypatch.setattr(application, "_appeler", appeler)
        with pytest.raises(RuntimeError, match="défauts actifs"):
            application.reinitialiser(["total_faux"])


def test_application_locale_refuse_un_hote_non_loopback():
    with pytest.raises(ba.ConfigurationInvalide):
        ba.ApplicationLocale("0.0.0.0")


def test_application_locale_non_demarree_n_a_pas_d_url():
    with pytest.raises(RuntimeError, match="non démarrée"):
        _ = ba.ApplicationLocale("127.0.0.1").url


# ── Revue verdict-reviewer : plafond non contournable, code de sortie, bornes ────────────────────────────


def test_falsifiable_des_generations_qui_plantent_comptent_au_pire_pour_le_plafond():
    """Avant correction : un essai dont `generer` lève avait un coût None compté pour 0 ; avec un moteur qui plante après avoir
    dépensé, le plafond n'arrêtait jamais la campagne (4,5 $ dépensés pour un plafond de 1 $)."""
    appels = []

    def generer(cas, essai):
        appels.append((cas, essai))
        raise RuntimeError("le moteur a planté après la génération")

    camp = ba.executer_campagne(SPECS, ATTENDUS, 3, generer, Monde().jouer, defauts_connus=DEFAUTS,
                                plafond_usd=0.25, cout_estime_essai=0.10)

    assert len(appels) == 2  # 2 × 0,10 $ comptés au pire ; le 3e dépasserait 0,25 $
    assert "plafond de coût" in camp.interrompue
    assert all(e.cout_usd is None for e in camp.essais)  # le rapport garde « non consigné », jamais 0
    assert ba.calculer_indicateurs(camp)["cout"]["par_generation_usd"] is None


def test_cout_retenu_pour_le_plafond():
    assert ba.cout_retenu_pour_le_plafond(0.07, 0.2, 0.1) == 0.07
    assert ba.cout_retenu_pour_le_plafond(None, 0.2, 0.1) == 0.2
    assert ba.cout_retenu_pour_le_plafond(None, 0.0, 0.1) == 0.1


@pytest.mark.parametrize("plafond", [float("nan"), float("inf"), -1.0])
def test_un_plafond_invalide_est_refuse_il_desactiverait_l_arret(plafond):
    monde = Monde()
    with pytest.raises(ba.ConfigurationInvalide, match="plafond de coût invalide"):
        campagne(monde, plafond_usd=plafond)
    assert monde.appels_generer == []


@pytest.mark.parametrize("estime", [float("nan"), -0.1])
def test_une_estimation_invalide_est_refusee(estime):
    with pytest.raises(ba.ConfigurationInvalide, match="coût estimé"):
        campagne(Monde(), plafond_usd=1.0, cout_estime_essai=estime)


def test_la_ligne_de_commande_refuse_un_plafond_nan_nul_ou_une_estimation_negative(monkeypatch):
    _interdire_le_reel(monkeypatch)
    assert ba.main(["--reel", "--plafond-cout", "nan"]) == 2
    assert ba.main(["--reel", "--plafond-cout", "0"]) == 2
    assert ba.main(["--a-sec", "--cout-estime-essai", "-1"]) == 2


def test_beaucoup_de_non_concluants_sous_defaut_ne_donnent_pas_un_vert():
    """1 jeu concluant sans faux vert + un jeu en erreur sous défaut : n'est PAS « rien à signaler »."""
    camp = campagne(Monde({("a", "total_faux", 1): "technical_error"}))  # 1 des 2 jeux sous défaut = 50 % > seuil
    ind = ba.calculer_indicateurs(camp)

    assert ind["faux_verts"]["k"] == 0 and ind["faux_verts"]["n"] == 1
    assert ind["part_non_concluants_sous_defaut"] == 0.5
    assert ba.code_de_sortie(ind, camp) == 3


def test_peu_de_non_concluants_restent_sous_le_seuil():
    camp = campagne(Monde({("a", "total_faux", 1): "technical_error"}), k=5)  # 1 jeu sur 10 sous défaut = 10 %
    ind = ba.calculer_indicateurs(camp)

    assert ind["part_non_concluants_sous_defaut"] == pytest.approx(0.1)
    assert ind["part_non_concluants_sous_defaut"] <= ba.SEUIL_NON_CONCLUANTS
    assert ba.code_de_sortie(ind, camp) == 0  # toujours rapporté, mais la porte est mesurée


def test_des_empreintes_non_rapportees_ne_donnent_pas_un_vert():
    class Muet(Monde):
        def jouer(self, artefacts, variante):
            return ba.Jeu(verdict="conforme" if variante == "saine" else "non_conforme")

    camp = campagne(Muet())
    assert ba.code_de_sortie(ba.calculer_indicateurs(camp), camp) == 3  # « même test partout » non prouvé


def test_cas_vide_ou_en_double_en_mise_au_point(monkeypatch):
    _interdire_le_reel(monkeypatch)
    monkeypatch.setenv("BANC_AGENTS_ISOLE", "1")  # pas de relance : `_lancer_reel` est remplacé ci-dessous
    assert ba.main(["--a-sec", "--cas", " , ,"]) == 2
    vu = {}

    def lancer(args, conf, cas, taux):
        vu["cas"] = cas
        return 0

    monkeypatch.setattr(ba, "_lancer_reel", lancer)
    ba.main(["--reel", "--plafond-cout", "5", "--cas", "connexion_valide,,connexion_valide"])
    assert vu["cas"] == ["connexion_valide"]


def test_un_moteur_bloque_ne_suspend_pas_la_campagne_sans_limite(tmp_path):
    def lancer(commande, **kw):
        assert kw["timeout"] == 42
        raise ba.subprocess.TimeoutExpired(commande, 42)

    generateur = ba.GenerateurReel(AppDouble(), {"a": 7}, 3, "http://127.0.0.1:1", tmp_path, "cle", lambda: None,
                                   lancer=lancer, racine=tmp_path, delai_s=42)
    with pytest.raises(RuntimeError, match="n'a pas rendu la main"):
        generateur("a", 1)


# ── Isolation des données (incident du 2026-10-07 : le premier essai réel a écrit dans le vrai data/) ─────────────

def test_une_base_dans_le_dossier_jetable_est_acceptee(tmp_path):
    ba.verifier_donnees_isolees(tmp_path / "testpilot.db", tmp_path)
    ba.verifier_donnees_isolees(tmp_path / "sous" / "testpilot.db", tmp_path)


def test_une_base_hors_du_dossier_jetable_est_refusee(tmp_path):
    """Falsifiable : avant, rien ne comparait la base RÉELLEMENT chargée au dossier jetable."""
    reel = tmp_path / "data" / "testpilot.db"
    jetable = tmp_path / "jetable"

    with pytest.raises(ba.ConfigurationInvalide, match="vrai data/"):
        ba.verifier_donnees_isolees(reel, jetable)


def test_un_dossier_au_prefixe_voisin_n_est_pas_le_dossier_jetable(tmp_path):
    """`/x/data2/testpilot.db` commence par `/x/data` mais n'est PAS dedans : comparaison par parenté, pas par texte."""
    with pytest.raises(ba.ConfigurationInvalide):
        ba.verifier_donnees_isolees(tmp_path / "data2" / "testpilot.db", tmp_path / "data")


def test_une_base_postgresql_est_refusee_meme_si_le_chemin_est_bon(tmp_path):
    with pytest.raises(ba.ConfigurationInvalide, match="TESTPILOT_DB_URL"):
        ba.verifier_donnees_isolees(tmp_path / "testpilot.db", tmp_path, db_url="postgresql://x/y")


def test_le_reel_est_relance_dans_un_processus_au_dossier_jetable_pose_avant_tout_import(monkeypatch, tmp_path):
    appels = []
    monkeypatch.setattr(ba.subprocess, "call", lambda cmd, env: appels.append((cmd, env)) or 0)
    monkeypatch.delenv("BANC_AGENTS_ISOLE", raising=False)
    monkeypatch.delenv("BANC_DATA_DIR", raising=False)
    monkeypatch.setenv("TESTPILOT_DB_PATH", "C:/vrai/data/testpilot.db")
    monkeypatch.setenv("TESTPILOT_DB_URL", "postgresql://prod/x")
    monkeypatch.setattr(ba, "valider_a_sec", lambda *a, **k: pytest.fail("la configuration ne doit pas être chargée "
                                                                         "avant la relance isolée"))

    code = ba.main(["--reel", "--plafond-cout", "0.5", "--essais", "1", "--cas", "connexion_valide"])

    assert code == 0 and len(appels) == 1
    commande, env = appels[0]
    assert env["BANC_AGENTS_ISOLE"] == "1"
    assert env["TESTPILOT_DATA_DIR"] == env["BANC_DATA_DIR"]
    assert "banc_agents_data_" in env["TESTPILOT_DATA_DIR"]
    assert "TESTPILOT_DB_PATH" not in env and "TESTPILOT_DB_URL" not in env, "aucune base réelle ne doit survivre"
    from cryptography.fernet import Fernet
    Fernet(env["TESTPILOT_SECRET_KEY"].encode())  # une clé Fernet VALIDE, posée avant le démarrage du processus
    assert commande[-8:-5] == ["--reel", "--plafond-cout", "0.5"] or "--reel" in commande
    assert "--cas" in commande and "connexion_valide" in commande


def test_la_cle_de_chiffrement_est_neuve_a_chaque_relance_et_jamais_celle_du_poste(monkeypatch):
    """Falsifiable : l'incident du premier essai (clé créée au chargement ≠ clé de la campagne → exécution `blocked`)."""
    clefs = []
    monkeypatch.setattr(ba.subprocess, "call", lambda cmd, env: clefs.append(env["TESTPILOT_SECRET_KEY"]) or 0)
    monkeypatch.setenv("TESTPILOT_SECRET_KEY", "CLE-REELLE-DU-POSTE")

    ba.relancer_isole(["--reel"])
    ba.relancer_isole(["--reel"])

    assert "CLE-REELLE-DU-POSTE" not in clefs
    assert len(set(clefs)) == 2


def test_la_relance_isolee_refuse_la_production(monkeypatch):
    monkeypatch.setenv("ODOO_ENV", "prod")
    monkeypatch.setattr(ba.subprocess, "call", lambda *a, **k: pytest.fail("jamais de relance en production"))

    assert ba.relancer_isole(["--reel"]) == 2


def test_preparer_projet_web_refuse_d_ecrire_si_la_configuration_pointe_ailleurs(monkeypatch, tmp_path):
    """Le scénario exact de l'incident : `config.DB_PATH` figé sur un autre dossier avant la préparation du projet."""
    import types

    from testpilot import config

    faux_projet = types.ModuleType("banc_projet")
    faux_projet.explorer = lambda *a, **k: pytest.fail("aucune exploration ne doit avoir lieu")
    monkeypatch.setitem(sys.modules, "banc_projet", faux_projet)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "vrai_data" / "testpilot.db")
    monkeypatch.setattr(config, "DB_URL", "")
    monkeypatch.delenv("TESTPILOT_DATA_DIR", raising=False)
    monkeypatch.delenv("TESTPILOT_SECRET_KEY", raising=False)
    import testpilot.store.db as db
    monkeypatch.setattr(db, "get_initialized_db", lambda *a, **k: pytest.fail("aucune base ne doit être ouverte"))

    with pytest.raises(ba.ConfigurationInvalide, match="vrai data/"):
        ba.preparer_projet_web("http://127.0.0.1:1", {"identifiant": "u", "mot_de_passe": "p"}, {},
                               tmp_path / "jetable", "cle")


def test_le_projet_jetable_declare_l_oracle_que_les_specs_citent():
    """Falsifiable : la campagne `base-1` (2026-10-07) n'en déclarait aucun — 3 cas sur 10 sortaient non concluants."""
    import json

    from testpilot.connectors import oracle_config

    oracle = ba.oracle_du_banc_web("http://127.0.0.1:4242")

    assert oracle["oracle_type"] == "http" and oracle["oracle_base_url"] == "http://127.0.0.1:4242"
    assert oracle_config.erreurs(oracle["oracle_type"], oracle["oracle_base_url"], "", oracle["oracle_queries"]) == []
    assert oracle_config.noms_declares(oracle["oracle_queries"]) == ["etat"]
    chemins = [r["path"] for r in json.loads(oracle["oracle_queries"])]
    assert chemins == ["/__etat"], "jamais /__defauts : l'agent ne doit pas pouvoir lire les défauts actifs"
    for spec in (ba.RACINE / "specs" / "banc_local").glob("commande_persistance_serveur.md"):
        assert "`etat`" in spec.read_text(encoding="utf-8")


# ── Aucune dépense réelle depuis un test (incident du 2026-10-07 : 5 générations payantes lancées par erreur) ─────

def test_sous_pytest_la_relance_reelle_est_refusee_meme_si_main_est_appele_sans_doublure(monkeypatch, capsys):
    """Falsifiable : c'est exactement ce qui est arrivé — `main(["--reel", ...])` sans substituer `subprocess.call`."""
    monkeypatch.delenv("BANC_AGENTS_ISOLE", raising=False)

    code = ba.main(["--reel", "--plafond-cout", "0.5", "--essais", "1", "--cas", "connexion_valide"])

    assert code == 2, "la barrière refuse (configuration invalide) au lieu de lancer une campagne réelle"
    assert "refusé sous pytest" in capsys.readouterr().err


def test_sous_pytest_le_moteur_de_generation_reel_est_refuse(tmp_path):
    generateur = ba.GenerateurReel(AppDouble(), {"a": 7}, 3, "http://127.0.0.1:1", tmp_path, "cle", lambda: None,
                                   racine=tmp_path)  # `lancer` par défaut = le VRAI subprocess.run

    with pytest.raises(ba.ConfigurationInvalide, match="refusé sous pytest"):
        generateur("a", 1)


def test_la_barriere_laisse_passer_une_doublure():
    ba.refuser_depense_reelle_sous_pytest(lambda *a, **k: 0, ba._APPEL_REEL, "essai")  # ne lève pas


def test_hors_pytest_la_barriere_ne_gene_pas_le_reel(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    ba.refuser_depense_reelle_sous_pytest(ba._APPEL_REEL, ba._APPEL_REEL, "essai")  # ne lève pas


# ── Lot PT-02d : données de test du projet jetable ───────────────────────────────────────────────────────────────────────


def test_variables_ecrites_lit_les_noms_du_feature_seulement():
    fichiers = {"m.feature": 'Quand je saisis "{{nom_client}}" puis "{{ ville_client }}" et "{{nom_client}}"',
                "m_steps.py": "x = '{{autre}}'"}

    assert ba.variables_ecrites(fichiers) == ["nom_client", "ville_client"]
    assert ba.variables_ecrites({"m.feature": "Alors ok"}) == []


def test_falsifiable_le_joueur_pose_les_valeurs_et_rapporte_l_empreinte_du_test_genere(tmp_path, monkeypatch):
    vus = {}
    monkeypatch.setattr(ba, "poser_les_donnees_de_test",
                        lambda texte, pid, valeurs=None: (texte.replace("{{nom_client}}", "Dupont SARL"), []))

    def executer(dossier, module, connexion, project_id, connector_type, traces):
        vus["feature"] = (dossier / "m.feature").read_text(encoding="utf-8")
        return {"execution": "success", "fonctionnel": "conforme", "cause": "", "detail": "", "duree": 1.0}

    artefacts = ba.Artefacts("a", 1, {"m.feature": 'Quand je saisis "{{nom_client}}"\n', "m_steps.py": "S"}, 0.1, module="m")
    jeu = _joueur(tmp_path, executer)(artefacts, ba.VARIANTE_SAINE)

    assert vus["feature"] == 'Quand je saisis "Dupont SARL"\n', "jamais {{nom_client}} saisi tel quel"
    assert jeu.verdict == "conforme" and jeu.empreintes == artefacts.empreintes


def test_falsifiable_une_valeur_qui_manque_rend_le_jeu_bloque_sans_le_jouer(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "poser_les_donnees_de_test",
                        lambda texte, pid, valeurs=None: (texte, ["variable inconnue « pays »"]))
    joue = []

    def executer(*a, **k):
        joue.append(1)
        return {"execution": "success", "fonctionnel": "conforme"}

    artefacts = ba.Artefacts("a", 1, {"m.feature": '"{{pays}}"', "m_steps.py": "S"}, 0.1, module="m")
    jeu = _joueur(tmp_path, executer)(artefacts, ba.VARIANTE_SAINE)

    assert jeu.verdict == "blocked" and "pays" in jeu.detail and joue == []


def test_poser_les_donnees_de_test_suit_le_calcul_de_la_production(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "banc.db")
    conn = get_initialized_db(config.DB_PATH)
    pid = ProjectRepo(conn).create(name="Banc", connector_type="web", base_url="http://127.0.0.1:1")
    ba.declarer_les_donnees_de_test(conn, pid)
    conn.close()

    etape = 'Quand je saisis "{{nom_client}}" à "{{ville_client}}"'
    assert ba.poser_les_donnees_de_test(etape, pid) == ('Quand je saisis "Dupont SARL" à "Lyon"', [])
    texte, manques = ba.poser_les_donnees_de_test('Quand je saisis "{{pays}}"', pid)
    assert texte == 'Quand je saisis "{{pays}}"' and manques == ["pays"]
    # Projet sans variable : le banc BLOQUE une référence (plus strict que la production, revue du 2026-10-15).
    assert ba.poser_les_donnees_de_test('"{{pays}}"', None)[1] != []


def test_le_cas_du_banc_cite_ses_donnees_seulement_quand_pt02f_est_allume(monkeypatch):
    """PT-02f : le cas du banc tel qu'une personne l'aurait validé (« Dupont SARL » → {{nom_client}}) ; éteint : inchangé."""
    from testpilot.generation import interrupteurs

    metier = {"title": "Créer un client", "preconditions": "", "steps": ["Créer le client Dupont SARL à Lyon"],
              "expected_result": "Dupont SARL apparaît dans la liste"}
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "0")
    assert ba.citer_les_donnees_dans_le_cas(metier) == metier

    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")   # PT-02f n'agit qu'avec PT-02d
    cite = ba.citer_les_donnees_dans_le_cas(metier)
    assert cite["steps"] == ["Créer le client {{nom_client}} à {{ville_client}}"]
    assert cite["expected_result"] == "{{nom_client}} apparaît dans la liste" and cite["title"] == "Créer un client"


def test_falsifiable_le_banc_bloque_une_variable_quand_le_projet_n_en_declare_aucune(tmp_path, monkeypatch):
    """Rejeu sans --donnees-de-test d'une génération qui en écrivait : jamais `{{nom_client}}` joué tel quel."""
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "banc.db")
    conn = get_initialized_db(config.DB_PATH)
    pid = ProjectRepo(conn).create(name="Banc", connector_type="web", base_url="http://127.0.0.1:1")
    conn.close()

    texte, manques = ba.poser_les_donnees_de_test('Alors la liste ne contient pas "{{nom_client}}"', pid)

    assert manques and "n'en déclare aucune" in manques[0]
    assert ba.poser_les_donnees_de_test('Alors la liste ne contient pas "{{nom_client"', pid)[1] != [], "mal fermée"
    assert ba.poser_les_donnees_de_test("Alors ok", pid) == ("Alors ok", [])


# ── Second jeu de données (porteur, 2026-10-16) ──────────────────────────────────────────────────────────────────────────


class MondeAVariables(Monde):
    """Le test du cas « a » écrit `{{nom_client}}` ; celui de « b » n'écrit aucune variable."""

    def generer(self, cas, essai):
        artefacts = super().generer(cas, essai)
        if cas == "a":
            artefacts.fichiers[f"{cas}.feature"] += '\n    Quand je saisis "{{nom_client}}"'
        return artefacts


def test_falsifiable_le_second_jeu_rejoue_seulement_les_tests_a_variables_et_compte_a_part():
    """Un test dont la variable ne sert pas (attendu figé) sort non conforme au second jeu : dit, jamais mélangé à pass@k."""
    rejoues = []

    def second_jeu(artefacts):
        rejoues.append(artefacts.cas)
        return ba.Jeu(verdict="non_conforme", detail="attendu figé", empreintes=artefacts.empreintes)

    camp = campagne(MondeAVariables(), second_jeu=second_jeu)
    indicateurs = ba.calculer_indicateurs(camp)

    assert rejoues == ["a"], "seul le test qui écrit une variable est rejoué"
    assert [(o.cas, o.variante, o.attendu, o.obtenu) for o in camp.observations_second_jeu] == \
        [("a", ba.VARIANTE_SECOND_JEU, "conforme", "non_conforme")]
    assert len(camp.observations) == JEUX_PAR_ESSAI, "les jeux d'avant, inchangés"
    assert indicateurs["second_jeu"]["rejoues"] == 1 and indicateurs["second_jeu"]["conformes_a_l_attendu"] == 0
    assert indicateurs["faux_verts"] == ba.calculer_indicateurs(campagne(MondeAVariables()))["faux_verts"]
    texte = ba.rendre_markdown(camp, indicateurs, {"date": "2026-10-16", "mode": "a_sec"})
    assert "## Second jeu de données" in texte and "attendu figé" in texte and "0/1" in texte


def test_sans_second_jeu_le_rapport_est_celui_d_avant():
    camp = campagne(MondeAVariables())

    assert camp.observations_second_jeu == [] and ba.calculer_indicateurs(camp)["second_jeu"] is None
    assert "Second jeu" not in ba.rendre_markdown(camp, ba.calculer_indicateurs(camp), {"date": "2026-10-16", "mode": "a_sec"})


def test_le_second_jeu_pose_ses_valeurs_comme_un_jeu_de_la_production(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "banc.db")
    conn = get_initialized_db(config.DB_PATH)
    pid = ProjectRepo(conn).create(name="Banc", connector_type="web", base_url="http://127.0.0.1:1")
    ba.declarer_les_donnees_de_test(conn, pid)
    conn.close()

    etape = 'Quand je saisis "{{nom_client}}" à "{{ville_client}}"'
    assert ba.poser_les_donnees_de_test(etape, pid, ba.SECOND_JEU_DU_BANC) == \
        ('Quand je saisis "Martin Lefèvre SA" à "Paris"', [])
    assert all(len(v) <= 40 for v in ba.SECOND_JEU_DU_BANC.values()), "valeurs valides pour l'application du banc"


def test_le_joueur_reel_joue_le_second_jeu_et_range_ses_traces_a_part(tmp_path, monkeypatch):
    vus = {}
    monkeypatch.setattr(ba, "poser_les_donnees_de_test",
                        lambda texte, pid, valeurs=None: (texte.replace("{{nom_client}}", (valeurs or {}).get(
                            "nom_client", "Dupont SARL")), []))

    def executer(dossier, module, connexion, project_id, connector_type, traces):
        vus["feature"], vus["traces"] = (dossier / "m.feature").read_text(encoding="utf-8"), traces
        return {"execution": "success", "fonctionnel": "conforme", "cause": "", "detail": "", "duree": 1.0}

    artefacts = ba.Artefacts("a", 1, {"m.feature": 'Quand je saisis "{{nom_client}}"\n', "m_steps.py": "S"}, 0.1, module="m")
    jeu = _joueur(tmp_path, executer)(artefacts, ba.VARIANTE_SAINE, ba.SECOND_JEU_DU_BANC)

    assert vus["feature"] == 'Quand je saisis "Martin Lefèvre SA"\n'
    assert vus["traces"].name.endswith("-second-jeu") and jeu.empreintes == artefacts.empreintes



def test_falsifiable_le_second_jeu_n_est_pas_rejoue_quand_la_saine_est_deja_en_ecart():
    """Revue du 2026-10-16 : un test cassé l'est sur les deux jeux — l'écart ne dit rien de la variable, il n'est pas compté."""
    rejoues = []
    monde = MondeAVariables(verdicts={("a", "saine", 1): "technical_error"})

    camp = campagne(monde, second_jeu=lambda a: rejoues.append(a.cas) or ba.Jeu("conforme", empreintes=a.empreintes))

    assert rejoues == [] and camp.observations_second_jeu == []
    assert camp.second_jeu_non_rejoues == [{"cas": "a", "essai": 1, "saine": "technical_error"}]
    assert ba.calculer_indicateurs(camp)["second_jeu"]["non_rejoues_saine_en_ecart"] == 1


@pytest.mark.parametrize("jeu, cause", [
    (lambda a: ba.Jeu("conforme", empreintes={"x": "y"}), "empreinte_divergente"),
    (lambda a: (_ for _ in ()).throw(RuntimeError("navigateur tombé")), "jeu_en_exception"),
])
def test_falsifiable_le_second_jeu_passe_par_les_protections_du_jeu(jeu, cause):
    """Revue du 2026-10-16 : une empreinte divergente ou une exception au second jeu n'est jamais comptée conforme."""
    camp = campagne(MondeAVariables(), second_jeu=jeu)
    sj = ba.calculer_indicateurs(camp)["second_jeu"]

    assert [(o.obtenu, o.cause) for o in camp.observations_second_jeu] == [("technical_error", cause)]
    assert sj["conformes_a_l_attendu"] == 0 and sj["prouves"] == 0
    if cause == "empreinte_divergente":
        assert sj["integrite"]["divergentes"] == 1


@pytest.mark.parametrize("etat, attendu", [
    ({"enregistrements": [{"nom": "Martin Lefèvre SA", "ville": "Paris"}]}, ba.PREUVE_OK),
    ({"enregistrements": [{"nom": "Dupont SARL", "ville": "Paris"}]}, ba.PREUVE_EN_DUR),   # en dur dans le code des steps
    ({"enregistrements": [{"nom": "Martin Lefèvre SA", "ville": ""}]}, ba.PREUVE_PARTIELLE),  # la ville ne sert pas
    ({"enregistrements": [{"nom": "Martin Lefèvre SA", "ville": "Parisienne"}]}, ba.PREUVE_PARTIELLE),  # champ à champ
    ({"enregistrements": []}, ba.PREUVE_ABSENTE),
    (None, ""),
])
def test_falsifiable_la_preuve_vient_de_l_etat_du_serveur(etat, attendu):
    """Revue du 2026-10-16 : CHAQUE variable écrite doit avoir atteint le serveur ; une seule ne prouve pas l'autre."""
    premier = {n: v for n, (_d, v) in ba.DONNEES_DE_TEST_DU_BANC.items()}

    assert ba.preuve_par_l_etat(etat, ba.SECOND_JEU_DU_BANC, premier, ["nom_client", "ville_client"]) == attendu


def test_falsifiable_conforme_sans_preuve_n_est_pas_compte_prouve():
    """Revue du 2026-10-16 : steps écrits à la main qui saisissent « Dupont SARL » en dur — le second jeu sort conforme, mais
    l'état du serveur le dit : jamais compté « prouvé »."""
    camp = campagne(MondeAVariables(), second_jeu=lambda a: ba.Jeu("conforme", empreintes=a.empreintes,
                                                                   preuve=ba.PREUVE_EN_DUR))
    sj = ba.calculer_indicateurs(camp)["second_jeu"]

    assert sj["conformes_a_l_attendu"] == 1 and sj["prouves"] == 0 and sj["valeur_du_premier_jeu_en_dur"] == 1
    assert ba.PREUVE_EN_DUR in ba.rendre_markdown(camp, ba.calculer_indicateurs(camp), {"date": "2026-10-16",
                                                                                       "mode": "a_sec"})


def test_le_joueur_lit_l_etat_du_serveur_apres_le_second_jeu_avant_la_remise_a_zero(tmp_path, monkeypatch):
    class AppAvecEtat(AppDouble):
        def etat(self):
            self.appels.append(["etat"])
            return {"enregistrements": [{"nom": "Martin Lefèvre SA", "ville": "Paris"}]}

    app = AppAvecEtat()
    monkeypatch.setattr(ba, "poser_les_donnees_de_test", lambda texte, pid, valeurs=None: (texte, []))
    artefacts = ba.Artefacts("a", 1, {"m.feature": 'Quand je saisis "{{nom_client}}"', "m_steps.py": "S"}, 0.1, module="m")

    def executer(*a, **k):
        app.appels.append(["executer"])
        return {"execution": "success", "fonctionnel": "conforme"}

    jeu = _joueur(tmp_path, executer, app)(artefacts, ba.VARIANTE_SAINE, ba.SECOND_JEU_DU_BANC)

    assert jeu.preuve == ba.PREUVE_OK
    assert app.appels == [[], ["executer"], ["etat"], []], "lu APRÈS le jeu et AVANT la remise à zéro"
    app.appels.clear()
    assert _joueur(tmp_path, executer, app)(artefacts, ba.VARIANTE_SAINE).preuve == "" and ["etat"] not in app.appels


def test_un_etat_illisible_garde_le_verdict_du_jeu(tmp_path, monkeypatch):
    class AppEtatEnPanne(AppDouble):
        def etat(self):
            raise RuntimeError("GET /__etat : HTTP 500")

    monkeypatch.setattr(ba, "poser_les_donnees_de_test", lambda texte, pid, valeurs=None: (texte, []))
    artefacts = ba.Artefacts("a", 1, {"m.feature": "F", "m_steps.py": "S"}, 0.1, module="m")
    jeu = _joueur(tmp_path, lambda *a, **k: {"execution": "success", "fonctionnel": "conforme"}, AppEtatEnPanne())(
        artefacts, ba.VARIANTE_SAINE, ba.SECOND_JEU_DU_BANC)

    assert jeu.verdict == "conforme" and jeu.preuve == ba.PREUVE_ILLISIBLE


def test_les_valeurs_du_second_jeu_passent_le_controle_de_saisie_de_la_production():
    from testpilot.parametres import resolution

    assert all(resolution.valider_valeur(v) == v for v in ba.SECOND_JEU_DU_BANC.values())
    assert set(ba.SECOND_JEU_DU_BANC) == set(ba.DONNEES_DE_TEST_DU_BANC), "chaque variable du banc change de valeur"
    assert all(ba.SECOND_JEU_DU_BANC[n] != v for n, (_d, v) in ba.DONNEES_DE_TEST_DU_BANC.items())
