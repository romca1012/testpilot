"""Lot 04 — `scripts/banc_mesure.py` : le calcul des indicateurs sur des résultats SIMULÉS.

Ce que ces tests fixent :
- chaque indicateur se calcule comme le plan (§3) le définit ;
- « non mesuré » n'est JAMAIS « zéro » (aucune observation → `None`, jamais 0 %) ;
- un cas non mesuré sort du dénominateur, il ne compte ni comme un succès ni comme un échec ;
- un faux PASSED (un défaut dont le cas sort `passed`) fait échouer le code de sortie ;
- le banc refuse une instance qui n'est pas locale.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("banc_mesure", RACINE / "scripts" / "banc_mesure.py")
banc = importlib.util.module_from_spec(_spec)
sys.modules["banc_mesure"] = banc
_spec.loader.exec_module(banc)

ATTENDUS = {
    "sain": {"a": "passed", "b": "passed", "c": "passed", "d": "passed"},
    "defauts": {
        "bug_1": {"a": "failed"},
        "bug_2": {"b": "failed", "c": "failed"},
    },
    "pannes": {
        "panne_1": {"attendu": "blocked", "cas": ["a", "b"]},
        "panne_2": {"attendu": "blocked", "cas": ["a"]},
    },
}


def _obs(config, cas, statut, **kw):
    return {"config": config, "cas": cas, "statut": statut, **kw}


def _toutes_bonnes():
    return (
        [_obs("sain", c, "passed") for c in "abcd"]
        + [_obs("defaut:bug_1", "a", "failed"), _obs("defaut:bug_2", "b", "failed"),
           _obs("defaut:bug_2", "c", "failed")]
        + [_obs("panne:panne_1", "a", "blocked"), _obs("panne:panne_1", "b", "blocked"),
           _obs("panne:panne_2", "a", "blocked")]
    )


# ── Chaque indicateur ────────────────────────────────────────────────────────────────────────

def test_un_banc_parfait_donne_i1_zero_i2_zero_i5_cent_pour_cent():
    i = banc.calculer_indicateurs(_toutes_bonnes(), ATTENDUS)

    assert i["I1"]["valeur"] == 0.0 and i["I1"]["faux_passed"] == 0 and i["I1"]["paires_mesurees"] == 3
    assert i["I2"]["valeur"] == 0.0 and i["I2"]["cas_mesures"] == 4
    assert i["I5"]["valeur"] == 1.0 and i["I5"]["bloques"] == 3
    assert i["ecarts_aux_attendus"] == []
    assert banc.code_de_sortie(i) == 0


def test_i1_compte_les_paires_defaut_cas_qui_sortent_passed_et_nomme_les_defauts_manques():
    obs = _toutes_bonnes()
    obs[5] = _obs("defaut:bug_2", "b", "passed")  # bug_2 : une paire sur deux passe à tort
    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["I1"]["faux_passed"] == 1
    assert i["I1"]["valeur"] == pytest.approx(1 / 3)
    assert i["I1"]["defauts_manques"] == [], "bug_2 est détecté par son autre paire"

    obs[6] = _obs("defaut:bug_2", "c", "passed")  # plus aucune paire de bug_2 n'échoue
    i = banc.calculer_indicateurs(obs, ATTENDUS)
    assert i["I1"]["defauts_manques"] == ["bug_2"]


def test_i2_compte_les_failed_de_l_instance_saine():
    obs = _toutes_bonnes()
    obs[0] = _obs("sain", "a", "failed")
    obs[1] = _obs("sain", "b", "retest")  # un retest n'est pas un faux FAILED

    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["I2"]["faux_failed"] == 1 and i["I2"]["valeur"] == pytest.approx(1 / 4)


def test_i5_compte_les_pannes_rapportees_blocked_et_liste_les_mal_attribuees():
    obs = _toutes_bonnes()
    obs[8] = _obs("panne:panne_1", "b", "failed")  # une panne prise pour un défaut de l'application

    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["I5"]["valeur"] == pytest.approx(2 / 3)
    assert i["I5"]["mal_attribuees"] == [{"config": "panne:panne_1", "cas": "b", "statut": "failed"}]


# ── « Non mesuré » n'est pas « zéro » ────────────────────────────────────────────────────────

def test_sans_aucune_observation_tout_est_non_mesure_jamais_zero():
    i = banc.calculer_indicateurs([], ATTENDUS)

    for cle in ("I1", "I2", "I3", "I4", "I5", "I6"):
        assert i[cle]["valeur"] is None, cle
    assert banc.code_de_sortie(i) == 3, "rien de mesuré n'est pas un succès"


def test_le_mode_fige_ne_mesure_ni_i3_ni_i4_ni_i6():
    i = banc.calculer_indicateurs(_toutes_bonnes(), ATTENDUS)

    assert i["I3"]["valeur"] is None and i["I4"]["valeur"] is None and i["I6"]["valeur"] is None
    assert "non mesuré" in banc.rendre_markdown(i, {"version": "17.0", "date": "d", "mode": "figé"}, [])


def test_un_cas_non_mesure_sort_du_denominateur_et_est_liste():
    obs = _toutes_bonnes()
    obs[0] = _obs("sain", "a", None, raison="Timeout")  # harnais tombé

    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["I2"]["cas_mesures"] == 3
    assert i["non_mesurees"] == [{"config": "sain", "cas": "a", "raison": "Timeout"}]


def test_un_defaut_entierement_non_mesure_ne_vaut_pas_zero_faux_passed():
    obs = [o for o in _toutes_bonnes() if not o["config"].startswith("defaut:")]

    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["I1"]["valeur"] is None


def test_les_indicateurs_de_generation_se_calculent_depuis_l_echantillon():
    gen = {"generes": 20, "sans_erreur_technique": 17, "verdict_exploitable": 15, "cout_total": 8.0,
           "nouveaux_cas": 20}

    i = banc.calculer_indicateurs(_toutes_bonnes(), ATTENDUS, gen)

    assert i["I3"]["valeur"] == pytest.approx(0.85) and i["I4"]["valeur"] == pytest.approx(0.75)
    assert i["I6"]["valeur"] == pytest.approx(0.4) and i["I3"]["echantillon"] == 20


# ── Le code de sortie ────────────────────────────────────────────────────────────────────────

def test_un_faux_passed_fait_echouer_le_code_de_sortie():
    obs = _toutes_bonnes()
    obs[4] = _obs("defaut:bug_1", "a", "passed")

    assert banc.code_de_sortie(banc.calculer_indicateurs(obs, ATTENDUS)) == 1


def test_une_panne_mal_attribuee_fait_echouer_le_code_de_sortie():
    obs = _toutes_bonnes()
    obs[9] = _obs("panne:panne_2", "a", "retest")

    assert banc.code_de_sortie(banc.calculer_indicateurs(obs, ATTENDUS)) == 1


def test_un_faux_failed_seul_ne_fait_pas_echouer_le_code_de_sortie():
    """I2 a une cible tolérante (≤ 2 %) : il est publié et comparé, pas bloquant comme I1 et I5."""
    obs = _toutes_bonnes()
    obs[0] = _obs("sain", "a", "failed")

    assert banc.code_de_sortie(banc.calculer_indicateurs(obs, ATTENDUS)) == 0


def test_un_ecart_aux_attendus_est_liste_avec_sa_cause():
    obs = _toutes_bonnes()
    obs[2] = _obs("sain", "c", "retest", cause="wrong_field_name")

    i = banc.calculer_indicateurs(obs, ATTENDUS)

    assert i["ecarts_aux_attendus"] == [
        {"config": "sain", "cas": "c", "attendu": "passed", "observe": "retest", "cause": "wrong_field_name"}]


# ── Les attendus : forme seulement ───────────────────────────────────────────────────────────

def test_les_attendus_du_depot_sont_bien_formes_et_ne_referencent_que_des_cas_existants():
    attendus = banc.charger_attendus()
    cas = {p.stem for p in banc.CAS_FIGES.glob("*.feature")}

    assert banc.valider_attendus(attendus, cas) == []
    assert 12 <= len(cas) <= 15, "le plan demande 12 à 15 specs"
    assert {p.stem for p in (RACINE / "specs" / "banc").glob("*.md")} == cas, "une spec par cas figé"


def test_valider_attendus_signale_un_cas_ou_un_statut_inconnu():
    erreurs = banc.valider_attendus({"sain": {"x": "passed"}, "defauts": {"d": {"a": "casse"}}}, {"a"})

    assert any("« x » n'existe pas" in e for e in erreurs)
    assert any("statut attendu inconnu" in e for e in erreurs)


def test_chaque_defaut_du_module_a_au_moins_un_cas_attendu():
    from_module = (RACINE / "banc" / "odoo_addons" / "tp_bugs_injectes" / "models" / "bugs.py").read_text(
        encoding="utf-8")
    attendus = banc.charger_attendus()

    for code in attendus["defauts"]:
        assert f'"{code}"' in from_module, f"le défaut « {code} » n'existe pas dans le module"
    codes_module = {c for c in banc_codes(from_module)}
    assert codes_module == set(attendus["defauts"]), "un défaut sans attendu ne serait jamais mesuré"


def banc_codes(source: str):
    import ast
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Assign) and any(getattr(t, "id", "") == "CODES" for t in noeud.targets):
            return [e.value for e in noeud.value.elts]
    return []


# ── Sécurité ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", ["https://staging.client.example", "http://10.0.0.5:8069", "https://odoo.sapian.fr"])
def test_le_banc_refuse_une_instance_qui_n_est_pas_locale(url):
    with pytest.raises(SystemExit, match="LOCALE"):
        banc.InstanceBanc(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:18069", "http://localhost:18069"])
def test_le_banc_accepte_une_instance_locale(url):
    assert banc.InstanceBanc(url).url == url


# ── L'orchestration (sans Odoo ni navigateur) ────────────────────────────────────────────────

class _InstanceFausse:
    url, base, utilisateur, mot_de_passe = "http://127.0.0.1:18069", "banc", "admin", "admin"

    def __init__(self):
        self.journal = []

    def fixer_defauts(self, actifs, codes):
        self.journal.append(("defauts", sorted(actifs)))

    def arreter(self):
        self.journal.append(("arret",))

    def demarrer(self):
        self.journal.append(("demarrage",))

    def desinstaller(self, module):
        self.journal.append(("desinstalle", module))

    def installer(self, module):
        self.journal.append(("installe", module))


_ATT_MODULE = {**ATTENDUS, "pannes": {**ATTENDUS["pannes"],
                                      "module_desinstalle": {"attendu": "blocked", "module": "crm", "cas": ["d"]}}}


def test_l_orchestration_rejoue_sain_puis_chaque_defaut_puis_chaque_panne_et_remet_tout_en_etat():
    instance = _InstanceFausse()
    lances = []

    def executer(cas, connexion):
        lances.append((cas, connexion["ODOO_PASSWORD"]))
        return {"cas": cas, "statut": "passed"}

    obs = banc.mesurer_fige(instance, {**_ATT_MODULE, "pannes": {
        "odoo_arrete": {"attendu": "blocked", "cas": ["a"]},
        "mauvais_mot_de_passe": {"attendu": "blocked", "cas": ["a"]},
        "module_desinstalle": {"attendu": "blocked", "module": "crm", "cas": ["d"]}}},
        executer=executer, journal=lambda *_: None)

    assert [o["config"] for o in obs][:4] == ["sain"] * 4
    assert ("defauts", ["bug_1"]) in instance.journal and ("defauts", ["bug_2"]) in instance.journal
    assert instance.journal[-1] != ("defauts", ["bug_2"]), "les défauts sont remis à zéro"
    assert ("arret",) in instance.journal and ("demarrage",) in instance.journal
    assert ("desinstalle", "crm") in instance.journal and ("installe", "crm") in instance.journal
    mauvais = [mdp for cas, mdp in lances if mdp not in ("admin",)]
    assert mauvais == ["mot-de-passe-errone-du-banc"], "seule la panne « mauvais mot de passe » change le mot de passe"


def test_un_harnais_qui_plante_donne_un_cas_non_mesure_jamais_un_succes():
    def executer(cas, connexion):
        raise RuntimeError("Chromium introuvable")

    obs = banc.mesurer_fige(_InstanceFausse(), {"sain": {"a": "passed"}}, executer=executer,
                            journal=lambda *_: None)

    assert obs == [{"cas": "a", "statut": None, "raison": "RuntimeError: Chromium introuvable", "config": "sain"}]


def test_la_panne_est_levee_meme_si_un_cas_plante_pendant_la_panne():
    instance = _InstanceFausse()

    def executer(cas, connexion):
        raise RuntimeError("boom")

    banc.mesurer_fige(instance, {"pannes": {"odoo_arrete": {"attendu": "blocked", "cas": ["a"]}}},
                      executer=executer, journal=lambda *_: None)

    assert ("demarrage",) in instance.journal, "Odoo doit être relancé quoi qu'il arrive"


def test_une_panne_qui_ne_peut_pas_etre_posee_est_non_mesuree_jamais_un_succes():
    class _Instance(_InstanceFausse):
        def arreter(self):
            raise RuntimeError("docker introuvable")

    obs = banc.mesurer_fige(_Instance(), {"pannes": {"odoo_arrete": {"attendu": "blocked", "cas": ["a"]}}},
                            executer=lambda cas, connexion: {"cas": cas, "statut": "blocked"},
                            journal=lambda *_: None)

    assert obs == [{"config": "panne:odoo_arrete", "cas": "a", "statut": None,
                    "raison": "panne non posée : RuntimeError: docker introuvable"}]
    assert banc.calculer_indicateurs(obs, {"pannes": {"odoo_arrete": {"attendu": "blocked", "cas": ["a"]}}})[
        "I5"]["valeur"] is None
