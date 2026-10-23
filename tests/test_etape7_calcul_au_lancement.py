"""Étape 7 (A108, A110) — la valeur attendue CALCULÉE au moment de jouer le test.

Ce que ces tests gardent :
1. le test nomme le calcul ; au lancement, chaque itération reçoit SA valeur calculée avec ses propres données, unité
   comprise, et le rapport dit d'où elle vient ;
2. vrai Behave : seule l'itération où l'application calcule faux échoue (falsifiabilité de bout en bout) ;
3. un calcul impossible (fiche non retenue, entrée sans valeur, nom réservé pris) : le test n'est pas joué, la raison dite ;
4. un test sans calcul se prépare exactement comme avant.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from behave.parser import parse_feature

from testpilot import config
from testpilot.api.services import donnees_de_test_service as service
from testpilot.parametres import calcul_au_lancement
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (CaseDataRepo, CaseRepo, ExecutionRepo, FicheDeCalculRepo, ModuleRepo, ProjectRepo,
                                          RunRepo, TestDataRepo, VersionRepo)

COMMANDE = """# language: fr
Fonctionnalité: Commande
  Scénario: Total
    Quand je commande "{{quantite}}" articles à "{{prix}}"
    Alors le nombre affiché pour "Total" vaut le résultat calculé "Total TTC"
"""
FICHE = {"nom": "Total TTC", "resultat": "total", "unite": "EUR",
         "elements": [{"nom": "quantite", "source": "variable {{quantite}}"}, {"nom": "prix", "source": "variable {{prix}}"},
                      {"nom": "taux_tva", "valeur": "20", "source": "CGI art. 278", "verifie_le": "2026-10-23"}],
         "etapes": [{"resultat": "ht", "operation": "multiplier", "termes": ["quantite", "prix"]},
                    {"resultat": "tva", "operation": "pourcentage", "de": "ht", "taux": "taux_tva"},
                    {"resultat": "ttc", "operation": "additionner", "termes": ["ht", "tva"]},
                    {"resultat": "total", "operation": "arrondir", "valeur": "ttc", "decimales": 2,
                     "mode": "au_plus_proche"}],
         "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "36,00"}]}
# L'application de l'exemple oublie la TVA quand on commande 2 articles : DÉFAUT à attraper.
STEPS = '''from behave import when, then
from decimal import Decimal, ROUND_HALF_UP

@when('je commande "{quantite}" articles à "{prix}"')
def commander(context, quantite, prix):
    q, p = Decimal(quantite), Decimal(prix.replace(",", "."))
    ttc = q * p if q == 2 else q * p * Decimal("1.2")
    context.total = str(ttc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)).replace(".", ",") + " €"

@then('le nombre affiché pour "{libelle}" vaut "{valeur}"')
def constater(context, libelle, valeur):
    assert context.total.replace(" €", "").replace(",", ".") == valeur.split()[0].replace(",", "."), (context.total, valeur)
'''


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn, *, feature=COMMANDE, retenir=True, lignes=(("Trois", "3", "10"), ("Deux", "2", "19,99"))):
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="M"),
                                feature_slug="commande")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature, steps_content="")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    ids = {n: depot.creer_variable(pid, nom=n) for n in ("quantite", "prix")}
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": nom, "valeurs": {ids["quantite"]: q, ids["prix"]: p}}
                                            for nom, q, p in lignes])
    from testpilot.parametres import calcul
    FicheDeCalculRepo(conn).creer(project_id=pid, case_id=cid, contenu=calcul.valider_fiche(FICHE), origine="personne",
                                  statut="retenue" if retenir else "proposee", auteur="marie",
                                  retenue_par="marie" if retenir else "")
    return pid, cid, vid


def _preparer(conn, pid, cid, vid):
    run_id = RunRepo(conn).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(conn, RunRepo(conn).get(run_id))
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    return eid, service.preparer_le_script(conn, eid, cid, vid, "commande")


def test_chaque_iteration_recoit_sa_valeur_calculee_et_son_origine(base):
    pid, cid, vid = _projet(base)
    eid, script = _preparer(base, pid, cid, vid)

    assert not script.blocage, script.blocage
    joue = (script.dossier / "commande.feature").read_text(encoding="utf-8")
    modele = parse_feature(joue, language="fr")
    assert "le résultat calculé" not in joue and "{{" not in joue
    lignes_exemples = [r.cells for s in modele.scenarios for ex in s.examples for r in ex.table.rows]
    calculees = sorted(row[-1] for row in lignes_exemples)
    assert calculees == ["36,00 EUR", "47,98 EUR"], "3 × 10 + 20 % ; 2 × 19,99 + 20 % = 47,976 → 47,98"
    consignees = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    origines = {v["origine"] for i in consignees["iterations"] for n, v in i["valeurs"].items() if n.startswith("tp_calcul")}
    assert origines == {"calcul « Total TTC »"}


def test_falsifiable_vrai_behave_seule_l_iteration_calculee_faux_par_l_application_echoue(base, tmp_path):
    from testpilot.execution.behave_result import parse_behave_json

    pid, cid, vid = _projet(base)
    _eid, script = _preparer(base, pid, cid, vid)
    (script.dossier / "commande_steps.py").unlink()
    (script.dossier / "steps").mkdir()
    (script.dossier / "steps" / "commande_steps.py").write_text(STEPS, encoding="utf-8")
    sortie = tmp_path / "resultat.json"
    fini = subprocess.run([sys.executable, "-m", "behave", "--lang", "fr", "--no-capture", "-f", "json", "-o", str(sortie),
                           str(script.dossier)], cwd=script.dossier, capture_output=True, text=True, check=False)
    resultat = parse_behave_json(sortie.read_text(encoding="utf-8"), fini.returncode)

    statuts = sorted((s.name, s.status) for s in resultat.scenarios)
    assert [st for _n, st in statuts].count("failed") == 1, statuts
    assert any("Deux" in n and st == "failed" for n, st in statuts), "l'application oublie la TVA pour 2 articles"


@pytest.mark.parametrize("cas, motif", [
    ("non_retenue", "n'est pas retenu pour ce cas"),
    # Le prix est saisi par le test, mais n'a de valeur nulle part (ni la ligne du cas, ni le projet).
    ("entree_sans_valeur", "« prix » manque"),
])
def test_un_calcul_impossible_bloque_le_test_en_le_disant(base, cas, motif):
    if cas == "non_retenue":
        pid, cid, vid = _projet(base, retenir=False)
    else:
        pid, cid, vid = _projet(base, lignes=(("Trois", "3", ""),))
    _eid, script = _preparer(base, pid, cid, vid)
    assert script.blocage and motif in script.blocage and "n'a pas été joué" in script.blocage


def test_un_test_sans_calcul_se_prepare_comme_avant(base):
    feature = COMMANDE.replace('vaut le résultat calculé "Total TTC"', 'vaut "36,00 €"')
    pid, cid, vid = _projet(base, feature=feature)
    _eid, script = _preparer(base, pid, cid, vid)
    joue = (script.dossier / "commande.feature").read_text(encoding="utf-8")
    assert "tp_calcul" not in joue and '"36,00 €"' in joue


def test_appels_et_reecriture():
    assert calcul_au_lancement.noms_appeles(COMMANDE + COMMANDE) == ["Total TTC"]
    texte = calcul_au_lancement.reecrire(COMMANDE, {"Total TTC": "tp_calcul_1"})
    assert 'vaut "{{tp_calcul_1}}"' in texte


# ── L'agent technique reçoit les calculs retenus : des noms, jamais des chiffres ──────────────────────────────────────────

def test_falsifiable_l_agent_recoit_le_nom_et_les_entrees_jamais_un_chiffre():
    from testpilot.api.services.generation_service import _calculs_pour_l_agent
    from testpilot.generation.prompt import _section_metier

    metier = {"title": "Commande", "steps": ["Commander"], "expected_result": "Le total TTC s'affiche"}
    sans = _section_metier(metier)
    avec = _section_metier({**metier, "calculs": _calculs_pour_l_agent([FICHE])})

    assert avec.startswith(sans), "sans calcul retenu, le métier d'avant octet pour octet"
    assert 'vaut le résultat calculé "<nom du calcul>"' in avec and "« Total TTC » — en EUR" in avec
    assert "{{quantite}}, {{prix}}" in avec
    ajout = avec[len(sans):]
    assert "20" not in ajout and "36" not in ajout, "ni la constante (TVA) ni l'exemple ne sont montrés"


def test_une_fiche_illisible_n_est_pas_proposee_a_l_agent():
    from testpilot.api.services.generation_service import _calculs_pour_l_agent
    assert _calculs_pour_l_agent([{**FICHE, "exemples": []}]) == []


# ── Revue du 2026-10-23 ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_entree_ecrite_en_dur_bloque_le_test(base):
    """BLOQUANT de la revue : le test écrit « 3 » et « 10 » en dur — calculer chaque ligne avec SES valeurs annoncerait des
    itérations jamais jouées (deux lignes fusionnées en un faux « conforme »)."""
    feature = COMMANDE.replace('"{{quantite}}" articles à "{{prix}}"', '"3" articles à "10"')
    pid, cid, vid = _projet(base, feature=feature, lignes=())
    # Les lignes du PROJET cochées au lancement (la garde A59 ne couvre que les lignes propres au cas).
    depot = TestDataRepo(base)
    ids = {v["nom"]: v["id"] for v in depot.variables(pid)}
    jeux = []
    for nom, q, p in (("Trois", "3", "10"), ("Six", "6", "5")):
        jeu = depot.creer_jeu(pid, nom=nom)
        depot.poser_valeurs(pid, jeu, {ids["quantite"]: q, ids["prix"]: p})
        jeux.append(jeu)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=jeux)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)
    base.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    base.commit()
    script = service.preparer_le_script(base, eid, cid, vid, "commande")
    assert script.blocage and "ne saisit pas {{quantite}}, {{prix}}" in script.blocage


@pytest.mark.parametrize("feature", [
    # « le résultat calculé » dans une ACTION : la valeur attendue serait saisie dans l'application (une tautologie).
    COMMANDE.replace('Quand je commande "{{quantite}}" articles à "{{prix}}"',
                     'Quand je commande "{{quantite}}" articles à "{{prix}}"\n    Et je saisis le résultat calculé "Total TTC"'),
    COMMANDE + '    # le nombre affiché pour "X" vaut le résultat calculé "Total TTC"\n',
])
def test_falsifiable_le_calcul_ne_s_appelle_que_depuis_la_verification(base, feature):
    pid, cid, vid = _projet(base, feature=feature)
    _eid, script = _preparer(base, pid, cid, vid)
    assert script.blocage and "Calcul :" in script.blocage


def test_falsifiable_une_fiche_qui_ne_retrouve_plus_ses_exemples_bloque_au_lancement(base):
    pid, cid, vid = _projet(base)
    contenu = json.loads(base.execute("SELECT contenu FROM fiche_de_calcul").fetchone()[0])
    contenu["exemples"][0]["attendu"] = "99"
    base.execute("UPDATE fiche_de_calcul SET contenu=?", (json.dumps(contenu),))
    base.commit()
    _eid, script = _preparer(base, pid, cid, vid)
    assert script.blocage and "l'exemple 1 attend 99" in script.blocage


def test_falsifiable_une_entree_saisie_par_un_autre_scenario_ne_compte_pas(base):
    """2e passe de la revue (bloquant) : le scénario A cite {{quantite}} et {{prix}}, le scénario B — celui qui vérifie le
    calcul — écrit 3 et 10 en dur ; B serait calculé avec les valeurs de chaque ligne sans jamais les jouer."""
    feature = COMMANDE + """
  Scénario: Autre
    Quand je commande "3" articles à "10"
    Alors le nombre affiché pour "Total" vaut le résultat calculé "Total TTC"
"""
    pid, cid, vid = _projet(base, feature=feature)
    _eid, script = _preparer(base, pid, cid, vid)
    assert script.blocage and "ne saisit pas {{quantite}}, {{prix}}" in script.blocage


def test_un_plan_de_scenario_n_est_pas_compte_plusieurs_fois():
    plan = """# language: fr
Fonctionnalité: Commande
  Plan du scénario: Total
    Quand je commande "{{quantite}}" articles à "<prix>"
    Alors le nombre affiché pour "Total" vaut le résultat calculé "Total TTC"
    Exemples:
      | prix |
      | 10   |
      | 20   |
"""
    refus, appels = calcul_au_lancement.analyser_les_appels(plan)
    assert refus == "" and appels == [("Total TTC", frozenset({"quantite"}))], "<prix> n'est pas une saisie de {{prix}}"


def test_la_fiche_retenue_la_plus_recente_est_appliquee(base):
    """Une ancienne fiche retenue, devenue invalide, ne bloque plus : c'est la dernière retenue de ce nom qui compte."""
    pid, cid, vid = _projet(base)
    base.execute("UPDATE fiche_de_calcul SET contenu=?", (json.dumps({"nom": "Total TTC"}),))   # l'ancienne, cassée
    base.commit()
    from testpilot.parametres import calcul
    double = {**FICHE, "etapes": [*FICHE["etapes"][:-1], {"resultat": "total", "operation": "multiplier",
                                                            "termes": ["ttc", "2"]}],
              "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "72"}]}
    FicheDeCalculRepo(base).creer(project_id=pid, case_id=cid, contenu=calcul.valider_fiche(double), origine="personne",
                                  statut="retenue", auteur="marie", retenue_par="marie")
    _eid, script = _preparer(base, pid, cid, vid)
    assert not script.blocage, script.blocage
    joue = (script.dossier / "commande.feature").read_text(encoding="utf-8")
    assert "72,0 EUR" in joue or "72 EUR" in joue or "72,00 EUR" in joue, joue
