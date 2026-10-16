"""Décision A52 (porteur, 2026-10-16) — itérations : un test, une ligne de données de test par itération, dans UNE exécution.

Le « Data Table » de QTP/UFT : `{{age}}` = 5, 10, 18 et `{{resultat_attendu}}` déclarés par une personne, un seul test, trois
itérations, un résultat chacune. Ce que ces tests gardent :
1. les itérations d'un test sont les lignes réduites à SES variables (deux lignes identiques pour lui n'en font qu'une) ;
2. le Gherkin réécrit en plan de scénario garde toutes les étapes, chaque itération avec ses valeurs ; un contexte qui emploie
   une variable est recopié ; un plan déjà écrit est combiné ; ce qui ne peut pas l'être est refusé, jamais deviné ;
3. vrai Behave : une itération dont l'application se comporte mal échoue SEULE, et fait échouer l'exécution ;
4. au lancement, toutes les lignes sont figées ; la préparation écrit le plan, consigne chaque itération, bloque si une ligne
   manque d'une valeur ;
5. création : une exécution par environnement, toutes les lignes dedans ; le rapport montre les itérations ;
6. Excel : une ligne par jeu, une variable par colonne (A54) ; l'ancien sens reste lu.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from behave.parser import parse_feature
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import donnees_de_test_service as service
from testpilot.api.services import report_service
from testpilot.parametres import iterations as it
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, RunRepo, TestDataRepo, VersionRepo,
)

AGE = """# language: fr
Fonctionnalité: Accès selon l'âge
  Scénario: Accès
    Quand je renseigne l'âge "{{age}}"
    Alors la page affiche le texte "{{resultat}}"
"""
LIGNES = [("Par défaut", {"age": "5", "resultat": "Refusé"}), ("Dix ans", {"age": "10", "resultat": "Refusé"}),
          ("Adulte", {"age": "18", "resultat": "Bienvenue"})]


def _scenarios(texte: str) -> list:
    modele = parse_feature(texte, language="fr")
    return [s for sc in modele.scenarios for s in (sc.scenarios if hasattr(sc, "scenarios") else [sc])]


# ── 1-2. Les règles pures ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_les_iterations_sont_les_lignes_reduites_aux_valeurs_du_test():
    lignes = [("Par défaut", {"age": "5"}), ("Pro", {"age": "5"}), ("Adulte", {"age": "18"})]
    assert it.iterations(lignes) == [("Par défaut / Pro", {"age": "5"}), ("Adulte", {"age": "18"})]


def test_falsifiable_chaque_iteration_porte_ses_valeurs_et_toutes_les_etapes():
    texte = it.en_plan_de_scenario(AGE, LIGNES)
    scenarios = _scenarios(texte)

    assert len(scenarios) == 3
    for scenario, (nom, valeurs) in zip(scenarios, LIGNES):
        etapes = [e.name for e in scenario.steps]
        assert etapes == [f"je renseigne l'âge \"{valeurs['age']}\"", f"la page affiche le texte \"{valeurs['resultat']}\""]
        assert nom in scenario.name
    assert "{{" not in texte


def test_un_contexte_qui_emploie_une_variable_est_recopie_dans_chaque_scenario():
    feature = ('# language: fr\nFonctionnalité: F\n  Contexte:\n    Soit je suis connecté en tant que "{{compte}}"\n\n'
               '  Scénario: S\n    Alors la page affiche le texte "{{resultat}}"\n')
    texte = it.en_plan_de_scenario(feature, [("A", {"compte": "gestion", "resultat": "Oui"}),
                                             ("B", {"compte": "lecture", "resultat": "Non"})])
    scenarios = _scenarios(texte)
    assert [[e.name for e in s.steps] for s in scenarios] == [
        ['je suis connecté en tant que "gestion"', 'la page affiche le texte "Oui"'],
        ['je suis connecté en tant que "lecture"', 'la page affiche le texte "Non"']]
    assert parse_feature(texte, language="fr").background is None


def test_un_plan_deja_ecrit_est_combine_avec_chaque_iteration():
    feature = ('# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n    Quand je saisis "<q>" pour "{{age}}"\n'
               '    Exemples: E\n      | q |\n      | 1 |\n      | 2 |\n')
    scenarios = _scenarios(it.en_plan_de_scenario(feature, [("A", {"age": "5"}), ("B", {"age": "18"})]))
    assert sorted(e.name for s in scenarios for e in s.steps) == sorted(
        ['je saisis "1" pour "5"', 'je saisis "2" pour "5"', 'je saisis "1" pour "18"', 'je saisis "2" pour "18"'])


def test_un_scenario_dont_les_valeurs_ne_changent_pas_n_est_joue_qu_une_fois():
    feature = AGE + '\n  Scénario: Accueil\n    Alors la page affiche le texte "{{titre}}"\n'
    texte = it.en_plan_de_scenario(feature, [("A", {"age": "5", "resultat": "Non", "titre": "Bienvenue"}),
                                             ("B", {"age": "18", "resultat": "Oui", "titre": "Bienvenue"})])
    noms = [s.name for s in _scenarios(texte)]
    assert noms.count("Accueil") == 1 and len(noms) == 3


@pytest.mark.parametrize("feature, motif", [
    ('# language: fr\nFonctionnalité: F\n  Règle: R\n    Scénario: S\n      Alors ok "{{age}}"\n', "Règle"),
    ('# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n    Quand je saisis "<age>" et "{{age}}"\n'
     '    Exemples: E\n      | age |\n      | 1 |\n', "colonne"),
])
def test_ce_qui_ne_peut_pas_etre_itere_est_refuse_jamais_devine(feature, motif):
    with pytest.raises(it.IterationsImpossibles, match=motif):
        it.en_plan_de_scenario(feature, [("A", {"age": "5"}), ("B", {"age": "18"})])


# ── 3. Vrai Behave : une itération en échec échoue seule ───────────────────────────────────────────────────────────────────

STEPS_AGE = '''from behave import when, then

@when('je renseigne l\\'âge "{age}"')
def saisir(context, age):
    # L'application de l'exemple : elle laisse entrer dès 10 ans (DÉFAUT), au lieu de 18.
    context.reponse = "Bienvenue" if int(age) >= 10 else "Refusé"

@then('la page affiche le texte "{texte}"')
def constater(context, texte):
    assert context.reponse == texte, f"{context.reponse!r} affiché, {texte!r} attendu"
'''


def test_falsifiable_vrai_behave_une_iteration_en_echec_echoue_seule(tmp_path):
    (tmp_path / "steps").mkdir()
    (tmp_path / "steps" / "age_steps.py").write_text(STEPS_AGE, encoding="utf-8")
    (tmp_path / "age.feature").write_text(it.en_plan_de_scenario(AGE, LIGNES), encoding="utf-8")

    sortie = tmp_path / "resultat.json"
    subprocess.run([sys.executable, "-m", "behave", "--lang", "fr", "--no-capture", "-f", "json", "-o", str(sortie),
                    str(tmp_path)], cwd=tmp_path, capture_output=True, text=True, check=False)
    resultats = [(e["name"], e["status"]) for f in json.loads(sortie.read_text(encoding="utf-8")) for e in f["elements"]]

    assert [statut for _, statut in resultats] == ["passed", "failed", "passed"], resultats
    assert "Dix ans" in resultats[1][0], "l'itération en échec est nommée d'après sa ligne"


# ── 4-5. Lancement, préparation, création, rapport ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn, feature=AGE):
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Accès", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="acces")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                   steps_content="from behave import then\n")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    ids = {n: depot.creer_variable(pid, nom=n) for n in ("age", "resultat")}
    jeux = {}
    for nom, valeurs in LIGNES:
        dataset_id = depot.jeux(pid)[0]["id"] if nom == "Par défaut" else depot.creer_jeu(pid, nom=nom)
        depot.poser_valeurs(pid, dataset_id, {ids[n]: v for n, v in valeurs.items()})
        jeux[nom] = dataset_id
    return pid, cid, vid, jeux


def _execution(conn, run_id, cid, vid):
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    return eid


def test_falsifiable_toutes_les_lignes_sont_figees_puis_jouees_en_iterations(base):
    pid, cid, vid, jeux = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=list(jeux.values()))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    # modifier le tableau après le lancement ne change rien (A29)
    TestDataRepo(base).poser_valeurs(pid, jeux["Adulte"], {TestDataRepo(base).variables(pid)[0]["id"]: "99"})
    eid = _execution(base, run_id, cid, vid)

    script = service.preparer_le_script(base, eid, cid, vid, "acces")

    assert script.blocage == "" and script.dossier is not None
    joue = (script.dossier / "acces.feature").read_text(encoding="utf-8")
    assert [s.steps[0].name for s in _scenarios(joue)] == ['je renseigne l\'âge "5"', 'je renseigne l\'âge "10"',
                                                           'je renseigne l\'âge "18"']
    consignees = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    assert [i["jeu"] for i in consignees["iterations"]] == ["Par défaut", "Dix ans", "Adulte"]
    assert consignees["iterations"][2]["valeurs"]["age"]["valeur"] == "18"


def test_falsifiable_une_ligne_sans_valeur_bloque_le_test_en_la_nommant(base):
    pid, cid, vid, jeux = _projet(base, feature=AGE.replace("{{resultat}}", "{{inconnue}}"))
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=list(jeux.values()))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))

    script = service.preparer_le_script(base, _execution(base, run_id, cid, vid), cid, vid, "acces")

    assert "inconnue" in script.blocage and script.dossier is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def test_falsifiable_plusieurs_lignes_donnent_une_seule_execution(client):
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid, cid, _, jeux = _projet(conn)
    finally:
        conn.close()

    r = client.post(f"/api/projects/{pid}/runs", json={"name": "Nuit", "selection_mode": "frozen", "case_ids": [cid],
                                                       "dataset_ids": list(jeux.values())})

    assert r.status_code == 201 and r.json()["plan_id"] is None
    assert [x["name"] for x in client.get(f"/api/projects/{pid}/runs").json()] == ["Nuit"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert json.loads(RunRepo(conn).get(r.json()["id"])["dataset_ids"]) == list(jeux.values())
    finally:
        conn.close()


def test_le_rapport_montre_chaque_iteration():
    joues = json.dumps({"jeu": "Par défaut, Adulte", "valeurs": {}, "iterations": [
        {"jeu": "Par défaut", "valeurs": {"age": {"valeur": "5", "origine": "Par défaut"}}},
        {"jeu": "Adulte", "valeurs": {"age": {"valeur": "18", "origine": "Adulte"}}}]})
    donnees = report_service._donnees_jouees(joues)
    assert [i["jeu"] for i in donnees["iterations"]] == ["Par défaut", "Adulte"]
    assert donnees["iterations"][1]["valeurs"]["age"]["valeur"] == "18"


# ── 6. Excel dans le sens du tableau (A54) ─────────────────────────────────────────────────────────────────────────────────

def test_l_excel_a_une_ligne_par_jeu_et_relit_l_ancien_sens(base):
    import openpyxl
    from testpilot.api.services import donnees_de_test_excel as excel

    pid, _, _, _ = _projet(base)
    feuille = openpyxl.load_workbook(io.BytesIO(excel.exporter(base, pid))).active
    assert [c.value for c in feuille[1]] == ["Ligne", "age", "resultat"]
    assert [c.value for c in feuille[3]] == ["Dix ans", "10", "Refusé"]

    relu = excel.lire(excel.exporter(base, pid))
    assert relu.erreurs == [] and relu.valeurs[("age", "Adulte")] == "18"

    ancien = openpyxl.Workbook()
    for ligne in (["Variable", "Par défaut", "Adulte"], ["age", "5", "18"]):
        ancien.active.append(ligne)
    tampon = io.BytesIO()
    ancien.save(tampon)
    lu = excel.lire(tampon.getvalue())
    assert lu.erreurs == [] and lu.valeurs[("age", "Adulte")] == "18"


# ── 7. Revue du 2026-10-16 (bloquants) : aucune variable ne reste littérale, aucune valeur n'est modifiée ─────────────────

def test_falsifiable_une_variable_ecrite_avec_espaces_ou_majuscules_est_posee():
    """`{{ resultat }}` et `{{Resultat}}` sont acceptés par l'exécution d'un jeu seul : restés littéraux en itérations, un
    « Alors … n'est pas affiché » passait sur chaque itération (faux conforme)."""
    feature = AGE.replace('"{{resultat}}"', '"{{ resultat }}"').replace('"{{age}}"', '"{{Age}}"')
    texte = it.en_plan_de_scenario(feature, LIGNES, ["age", "resultat"])

    assert "{{" not in texte
    assert [[e.name for e in s.steps] for s in _scenarios(texte)][2] == [
        'je renseigne l\'âge "18"', 'la page affiche le texte "Bienvenue"']


def test_falsifiable_une_variable_dans_une_cellule_d_exemples_recoit_la_valeur_de_chaque_iteration():
    feature = ('# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n    Quand je saisis "<q>"\n'
               '    Exemples: E\n      | q |\n      | {{age}} |\n')
    texte = it.en_plan_de_scenario(feature, [("A", {"age": "5"}), ("B", {"age": "18"})], ["age"])

    assert "{{" not in texte
    assert sorted(s.steps[0].name for s in _scenarios(texte)) == ['je saisis "18"', 'je saisis "5"']


def test_falsifiable_vrai_behave_une_valeur_est_jouee_telle_qu_annoncee(tmp_path):
    """Une barre oblique inverse n'est jamais doublée : « C:<oblique>temp » est joué tel quel, comme avec un jeu seul (A29).
    Revue : les valeurs sont construites avec `chr(92)` — écrit dans une chaîne Python, « \\t » serait une tabulation."""
    oblique = chr(92)
    attendues = ["C:" + oblique + "temp", "fin" + oblique]
    (tmp_path / "steps").mkdir()
    (tmp_path / "steps" / "s.py").write_text(
        "from behave import when\n@when('je saisis \"{v}\"')\ndef s(context, v):\n"
        f"    assert v in {attendues!r}, repr(v)\n", encoding="utf-8")
    feature = '# language: fr\nFonctionnalité: F\n  Scénario: S\n    Quand je saisis "{{v}}"\n'
    (tmp_path / "f.feature").write_text(
        it.en_plan_de_scenario(feature, [("A", {"v": attendues[0]}), ("B", {"v": attendues[1]})], ["v"]), encoding="utf-8")
    sortie = tmp_path / "r.json"
    subprocess.run([sys.executable, "-m", "behave", "--lang", "fr", "-f", "json", "-o", str(sortie), str(tmp_path)],
                   cwd=tmp_path, capture_output=True, text=True, check=False)
    assert [e["status"] for f in json.loads(sortie.read_text(encoding="utf-8")) for e in f["elements"]] == ["passed", "passed"]


def test_un_plan_sans_exemples_et_les_etiquettes_des_exemples():
    sans = '# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n    Quand je saisis "{{age}}" et "<q>"\n'
    with pytest.raises(it.IterationsImpossibles):
        it.en_plan_de_scenario(sans, [("A", {"age": "5"}), ("B", {"age": "18"})], ["age"])

    avec = ('# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n    Quand je saisis "{{age}}" et "<q>"\n'
            '    @lent\n    Exemples: E\n      | q |\n' + r'      | a\|b |' + '\n')
    texte = it.en_plan_de_scenario(avec, [("A", {"age": "5"}), ("B", {"age": "18"})], ["age"])
    exemples = [e for s in parse_feature(texte, language="fr").scenarios for e in s.examples]
    assert [e.tags for e in exemples] == [["lent"], ["lent"]]
    assert sorted(s.steps[0].name for s in _scenarios(texte)) == ['je saisis "18" et "a|b"', 'je saisis "5" et "a|b"']


def test_falsifiable_une_ligne_mise_a_la_corbeille_avant_le_lancement_ne_lance_rien(base):
    """A36 sur le chemin des itérations : jamais les autres lignes jouées à la place."""
    from testpilot.store.repositories import DonneeDeTestInvalide

    pid, cid, vid, jeux = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=list(jeux.values()))
    TestDataRepo(base).supprimer_jeu(pid, jeux["Adulte"], par="admin")

    with pytest.raises(DonneeDeTestInvalide):
        service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    assert RunRepo(base).get(run_id)["parametres_figes"] == ""


def test_falsifiable_une_variable_mal_ecrite_bloque_aussi_en_iterations(base):
    pid, cid, vid, jeux = _projet(base, feature=AGE.replace('"{{resultat}}"', '"{{resultat}"'))
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=list(jeux.values()))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))

    script = service.preparer_le_script(base, _execution(base, run_id, cid, vid), cid, vid, "acces")

    assert "mal écrite" in script.blocage and script.dossier is None


def test_une_seule_iteration_est_consignee_comme_un_jeu_seul(base):
    pid, cid, vid, jeux = _projet(base, feature=AGE.replace('"{{age}}"', '"7"').replace('"{{resultat}}"', '"ok"'))
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=list(jeux.values()))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)

    service.preparer_le_script(base, eid, cid, vid, "acces")

    consignees = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    assert "iterations" not in consignees and consignees["valeurs"] == {}


def test_un_chevron_deja_ecrit_pour_une_variable_est_refuse():
    feature = ('# language: fr\nFonctionnalité: F\n  Scénario: S\n    Quand je saisis "{{age}}"\n'
               '    Alors le texte "<age>" est affiché\n')
    with pytest.raises(it.IterationsImpossibles, match="<nom>"):
        it.en_plan_de_scenario(feature, [("A", {"age": "5"}), ("B", {"age": "18"})], ["age"])


def test_falsifiable_le_delai_croit_avec_les_iterations_mais_reste_plafonne():
    from testpilot.api.services import run_service

    assert run_service.delai_des_iterations(900, 1) == 900
    assert run_service.delai_des_iterations(900, 3) == 2700
    assert run_service.delai_des_iterations(900, 50) == run_service.DELAI_DES_ITERATIONS_MAX


def test_falsifiable_l_agent_de_correction_ne_voit_aucune_valeur_d_aucune_iteration(base, monkeypatch):
    """Revue : un dictionnaire unique ne masquait que la valeur de la DERNIÈRE itération."""
    from testpilot.api.services import generation_service

    monkeypatch.setenv("TESTPILOT_VARIABLES_DE_TEST", "1")
    pid, cid, vid, jeux = _projet(base)
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)
    joues = {"jeu": "", "valeurs": {}, "iterations": [{"jeu": j, "valeurs": {"age": {"valeur": v, "origine": j}}}
                                                      for j, v in (("A", "15"), ("B", "10"), ("C", "18"))]}
    base.execute("UPDATE execution SET parametres_joues=?, error_message=?, execution_status='technical_error' WHERE id=?",
                 (json.dumps(joues), "âge 15 refusé, âge 10 refusé, âge 18 accepté", eid))
    base.commit()

    contexte = generation_service._regeneration_failure_context(base, cid)

    texte = json.dumps(contexte, ensure_ascii=False)
    assert "âge 15 " not in texte and "âge 10 " not in texte and "âge 18 " not in texte
    assert texte.count("{{age}}") >= 3
