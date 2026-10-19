"""Décisions A57 et A58 (porteur, 2026-10-19) — les lignes PROPRES À UN CAS : jouer un test avec toutes les valeurs d'une
variable, une itération par valeur, le résultat attendu de chacune déclaré par une personne.

Ce que ces tests gardent :
1. le dépôt : colonnes = variables vivantes du projet, 50 lignes au plus, noms distincts ; rien n'est écrit à moitié ;
2. lancer le cas joue TOUTES ses lignes en itérations, chacune posée par-dessus les valeurs du projet (case vide = valeur du
   projet) ; « première ligne seulement » n'en joue qu'une ;
3. les lignes sont FIGÉES au lancement (A29) : les modifier ensuite ne change rien à ce qui est joué ;
4. des lignes du projet cochées se combinent avec celles du cas ; au-delà de 50 itérations, le test est bloqué en le disant ;
5. vrai Behave : seule la valeur que l'application traite mal fait échouer son itération ;
6. l'API : lecture, écriture, refus d'une valeur qui casserait le test.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from behave.parser import parse_feature
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import donnees_de_test_service as service
from testpilot.api.services import report_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseDataRepo, CaseRepo, DonneeDeTestInvalide, ExecutionRepo, ModuleRepo, ProjectRepo, RunRepo, TestDataRepo, VersionRepo,
)

AGE = """# language: fr
Fonctionnalité: Accès selon l'âge
  Scénario: Accès
    Soit je suis le client "{{client}}"
    Quand je renseigne l'âge "{{age}}"
    Alors la page affiche le texte "{{resultat}}"
"""
# L'application de l'exemple : elle laisse entrer dès 17 ans (DÉFAUT À LA LIMITE), au lieu de 18.
STEPS_AGE = '''from behave import given, when, then

@given('je suis le client "{client}"')
def client(context, client):
    assert client == "Dupont SARL", client

@when('je renseigne l\\'âge "{age}"')
def saisir(context, age):
    context.reponse = "Bienvenue" if int(age) >= 17 else "Accès refusé"

@then('la page affiche le texte "{texte}"')
def constater(context, texte):
    assert context.reponse == texte, f"{context.reponse!r} affiché, {texte!r} attendu"
'''
LIGNES = [("Mineur", {"age": "16", "resultat": "Accès refusé"}), ("Limite basse", {"age": "17", "resultat": "Accès refusé"}),
          ("Majeur", {"age": "18", "resultat": "Bienvenue"})]


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn, lignes=LIGNES):
    """Un projet : `client` partagé (valeur du projet seulement), `age` et `resultat` déclarés dans le projet mais remplis
    par les lignes du CAS."""
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Accès", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="acces")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=AGE, steps_content="")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    ids = {n: depot.creer_variable(pid, nom=n) for n in ("client", "age", "resultat")}
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ids["client"]: "Dupont SARL"})
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": nom, "valeurs": {ids[n]: v for n, v in valeurs.items()}}
                                            for nom, valeurs in lignes])
    return pid, cid, vid, ids


def _execution(conn, run_id, cid, vid):
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    return eid


def _etapes(texte: str) -> list[list[str]]:
    modele = parse_feature(texte, language="fr")
    return [[e.name for e in s.steps] for sc in modele.scenarios for s in (sc.scenarios if hasattr(sc, "scenarios") else [sc])]


# ── 1. Le dépôt ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_les_lignes_du_cas_se_relisent_dans_l_ordre_cases_vides_absentes(base):
    pid, cid, _, ids = _projet(base)
    CaseDataRepo(base).remplacer(cid, pid, [{"nom": "A", "valeurs": {ids["age"]: "16", ids["resultat"]: ""}}])
    assert CaseDataRepo(base).lignes(cid)[0]["valeurs"] == {ids["age"]: "16"}
    assert CaseDataRepo(base).niveaux(cid) == [("A", {"age": "16"})]
    assert CaseDataRepo(base).cas_avec_lignes(pid) == [cid]


@pytest.mark.parametrize("lignes, motif", [
    ([{"nom": "A", "valeurs": {9999: "x"}}], "variable de ce projet"),
    ([{"nom": "A", "valeurs": {}}, {"nom": "a", "valeurs": {}}], "deux lignes"),
    ([{"nom": "", "valeurs": {}}] * 51, "50 lignes"),
    ([{"nom": "x" * 61, "valeurs": {}}], "trop long"),
])
def test_falsifiable_une_ligne_invalide_n_ecrit_rien(base, lignes, motif):
    pid, cid, _, _ = _projet(base)
    avant = CaseDataRepo(base).lignes(cid)
    with pytest.raises(DonneeDeTestInvalide, match=motif):
        CaseDataRepo(base).remplacer(cid, pid, lignes)
    assert CaseDataRepo(base).lignes(cid) == avant


def test_falsifiable_une_variable_a_la_corbeille_ne_compte_plus(base):
    pid, cid, _, ids = _projet(base)
    TestDataRepo(base).supprimer_variable(pid, ids["age"], par="x")
    assert all("age" not in valeurs for _, valeurs in CaseDataRepo(base).niveaux(cid))


# ── 2-4. Lancer le cas : une itération par ligne ──────────────────────────────────────────────────────────────────────────

def test_falsifiable_lance_seul_le_cas_joue_toutes_ses_lignes_par_dessus_le_projet(base):
    pid, cid, vid, _ = _projet(base)
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)

    script = service.preparer_le_script(base, eid, cid, vid, "acces")

    assert script.blocage == "" and script.dossier is not None
    joue = (script.dossier / "acces.feature").read_text(encoding="utf-8")
    assert _etapes(joue) == [['je suis le client "Dupont SARL"', f'je renseigne l\'âge "{v["age"]}"',
                              f'la page affiche le texte "{v["resultat"]}"'] for _, v in LIGNES]
    consignees = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    assert [i["jeu"] for i in consignees["iterations"]] == ["Mineur", "Limite basse", "Majeur"]
    assert consignees["iterations"][0]["valeurs"]["client"]["origine"] == "Par défaut", "case vide : la valeur du projet"


def test_falsifiable_les_lignes_sont_figees_au_lancement(base):
    """A29 : modifier les lignes du cas après le lancement ne change rien à ce qui est joué."""
    pid, cid, vid, ids = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    CaseDataRepo(base).remplacer(cid, pid, [{"nom": "Autre", "valeurs": {ids["age"]: "99", ids["resultat"]: "x"}}])

    script = service.preparer_le_script(base, _execution(base, run_id, cid, vid), cid, vid, "acces")

    joue = (script.dossier / "acces.feature").read_text(encoding="utf-8")
    assert '"99"' not in joue and len(_etapes(joue)) == 3


def test_la_premiere_ligne_seulement(base):
    pid, cid, vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], lignes_des_cas="premiere")
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)

    script = service.preparer_le_script(base, eid, cid, vid, "acces")

    joue = (script.dossier / "acces.feature").read_text(encoding="utf-8")
    assert _etapes(joue) == [['je suis le client "Dupont SARL"', 'je renseigne l\'âge "16"',
                              'la page affiche le texte "Accès refusé"']]
    assert json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])["jeu"] == "Mineur"


def test_des_lignes_du_projet_cochees_se_combinent_avec_celles_du_cas(base):
    pid, cid, vid, ids = _projet(base)
    depot = TestDataRepo(base)
    pro = depot.creer_jeu(pid, nom="Pro")
    depot.poser_valeurs(pid, pro, {ids["client"]: "Martin SA"})
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=[depot.jeux(pid)[0]["id"], pro])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)

    service.preparer_le_script(base, eid, cid, vid, "acces")

    consignees = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    assert [i["jeu"] for i in consignees["iterations"]] == [
        "Par défaut · Mineur", "Par défaut · Limite basse", "Par défaut · Majeur", "Pro · Mineur", "Pro · Limite basse",
        "Pro · Majeur"]
    assert consignees["iterations"][3]["valeurs"]["client"]["valeur"] == "Martin SA"


def test_falsifiable_au_dela_de_50_iterations_le_test_est_bloque_en_le_disant(base):
    pid, cid, vid, ids = _projet(base, lignes=[(f"L{k}", {"age": str(k), "resultat": "x"}) for k in range(30)])
    depot = TestDataRepo(base)
    pro = depot.creer_jeu(pid, nom="Pro")
    depot.poser_valeurs(pid, pro, {ids["client"]: "Martin SA"})
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], dataset_ids=[depot.jeux(pid)[0]["id"], pro])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))

    script = service.preparer_le_script(base, _execution(base, run_id, cid, vid), cid, vid, "acces")

    assert "60 itérations" in script.blocage and script.dossier is None


def test_un_cas_sans_ligne_se_joue_comme_avant(base):
    pid, cid, vid, _ = _projet(base, lignes=[])
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)
    script = service.preparer_le_script(base, eid, cid, vid, "acces")
    assert "age" in script.blocage, "sans ligne du cas ni valeur du projet, la variable manque — nommée, comme avant"


# ── 5. Vrai Behave ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_vrai_behave_seule_la_valeur_mal_traitee_echoue(base, tmp_path, monkeypatch):
    """L'application laisse entrer dès 17 ans : seule la ligne « Limite basse » échoue, et l'écran le dit."""
    from types import SimpleNamespace

    from testpilot.api.services import run_service
    from testpilot.execution.behave_result import parse_behave_json
    from testpilot.verdict.status import derive_verdict

    pid, cid, vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)
    script = service.preparer_le_script(base, eid, cid, vid, "acces")
    (script.dossier / "acces_steps.py").unlink()
    (script.dossier / "steps").mkdir()
    (script.dossier / "steps" / "age_steps.py").write_text(STEPS_AGE, encoding="utf-8")
    sortie = tmp_path / "resultat.json"
    fini = subprocess.run([sys.executable, "-m", "behave", "--lang", "fr", "--no-capture", "-f", "json", "-o", str(sortie),
                           str(script.dossier)], cwd=script.dossier, capture_output=True, text=True, check=False)
    resultat = parse_behave_json(sortie.read_text(encoding="utf-8"), fini.returncode)
    verdict = derive_verdict(SimpleNamespace(dry_run_passed=True, real_run=resultat, retried=False))
    base.execute("UPDATE execution SET execution_status=?, functional_status=? WHERE id=?",
                 (verdict.execution_status, verdict.functional_status, eid))
    base.commit()
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")   # jamais d'appel à l'IA depuis un test
    run_service._persist(base, eid, cid, verdict, SimpleNamespace(real_run=resultat), 0.0, "acces")

    vues = report_service.iterations_jouees(ExecutionRepo(base).get(eid), ExecutionRepo(base).list_scenario_results(eid))
    assert [(v["jeu"], v["statut"]) for v in vues] == [("Mineur", "passed"), ("Limite basse", "failed"), ("Majeur", "passed")]


# ── 6. L'API ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_l_api_lit_et_ecrit_les_lignes_du_cas_et_refuse_une_valeur_qui_casserait_le_test(base, monkeypatch):
    pid, cid, _, ids = _projet(base)
    client = TestClient(app_mod.app)
    url = f"/api/cases/{cid}/donnees-de-test"

    lu = client.get(url).json()
    assert [v["nom"] for v in lu["variables"]] == ["client", "age", "resultat"]
    assert [l["nom"] for l in lu["lignes"]] == ["Mineur", "Limite basse", "Majeur"]

    ecrit = client.put(url, json={"lignes": [{"nom": "Seule", "valeurs": {str(ids["age"]): "21"}}]})
    assert ecrit.status_code == 200 and ecrit.json()["lignes"][0]["valeurs"] == {str(ids["age"]): "21"}

    refus = client.put(url, json={"lignes": [{"nom": "X", "valeurs": {str(ids["age"]): 'a"b'}}]})
    assert refus.status_code == 422
    assert [l["nom"] for l in client.get(url).json()["lignes"]] == ["Seule"], "rien n'est écrit à moitié"
    assert client.get(f"/api/projects/{pid}/donnees-de-test/cas-avec-lignes").json() == [cid]


# ── Revue du 2026-10-19 ───────────────────────────────────────────────────────────────────────────────────────────────────

EN_DUR = AGE.replace('"{{age}}"', '"16"').replace('"{{resultat}}"', '"Accès refusé"')


def test_falsifiable_un_test_qui_n_emploie_pas_les_variables_des_lignes_est_bloque(base):
    """Bloquant de la revue : le test écrit l'âge en dur. Ses trois lignes fusionnaient en UNE itération jouée avec « 16 »,
    et l'écran annonçait les trois classes jouées — un « conforme » sur des valeurs jamais posées."""
    from testpilot.api.services import run_service

    pid, cid, vid, _ = _projet(base)
    base.execute("UPDATE test_case_version SET feature_content=? WHERE id=?", (EN_DUR, vid))
    base.commit()
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)

    script = service.preparer_le_script(base, eid, cid, vid, "acces")

    assert "« {{age}} », le test ne l'emploie pas" in script.blocage and "« {{resultat}} »" in script.blocage
    assert script.dossier is None
    ecarts = run_service.ecarts_cas_test(base, CaseRepo(base).get(cid), vid)
    assert any("{{age}}" in e for e in ecarts), "la porte d'exécution le dit aussi, avant tout lancement"
    assert not run_service.gate_du_cas(base, CaseRepo(base).get(cid), vid).allowed


def test_falsifiable_la_valeur_du_cas_l_emporte_sur_celle_du_projet_et_une_case_vide_la_reprend(base):
    pid, cid, vid, ids = _projet(base, lignes=[("Limite basse", {"age": "17", "resultat": "Accès refusé"}),
                                               ("Sans âge", {"resultat": "Bienvenue"})])
    depot = TestDataRepo(base)
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ids["age"]: "30"})
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)

    service.preparer_le_script(base, eid, cid, vid, "acces")

    iterations = json.loads(base.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])["iterations"]
    assert iterations[0]["valeurs"]["age"] == {"valeur": "17", "origine": "Limite basse"}
    assert iterations[1]["valeurs"]["age"] == {"valeur": "30", "origine": "Par défaut"}


def _tous_les_cas(conn, pid):
    return RunRepo(conn).create(project_id=pid, name="Tout", selection_mode="all")


def test_falsifiable_un_cas_entre_dans_la_campagne_apres_son_lancement_est_bloque_s_il_a_ses_lignes(base):
    pid, cid, vid, ids = _projet(base, lignes=[])
    run_id = _tous_les_cas(base, pid)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    nouveau = CaseRepo(base).create(title="Nouveau", module_id=CaseRepo(base).get(cid)["module_id"], feature_slug="nouveau")
    nvid = VersionRepo(base).create(test_case_id=nouveau, spec_content="", spec_hash="", feature_content=AGE, steps_content="")
    base.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (nvid, nouveau))
    base.commit()
    CaseDataRepo(base).remplacer(nouveau, pid, [{"nom": "Limite", "valeurs": {ids["age"]: "17", ids["resultat"]: "x"}}])

    script = service.preparer_le_script(base, _execution(base, run_id, nouveau, nvid), nouveau, nvid, "nouveau")

    assert "après son lancement" in script.blocage and script.dossier is None


def test_un_cas_present_au_lancement_rejoue_ce_qui_a_ete_fige(base):
    """A29 : des lignes ajoutées APRÈS le lancement à un cas déjà dans la campagne ne changent pas ce qu'elle joue."""
    pid, cid, vid, ids = _projet(base, lignes=[])
    depot = TestDataRepo(base)
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ids["age"]: "30", ids["resultat"]: "Bienvenue"})
    run_id = _tous_les_cas(base, pid)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    CaseDataRepo(base).remplacer(cid, pid, [{"nom": "Limite", "valeurs": {ids["age"]: "17"}}])

    script = service.preparer_le_script(base, _execution(base, run_id, cid, vid), cid, vid, "acces")

    assert script.blocage == "" and '"30"' in (script.dossier / "acces.feature").read_text(encoding="utf-8")


def test_le_gel_porte_les_cas_presents_et_leurs_lignes_en_une_seule_ecriture(base):
    pid, cid, _, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    figes = json.loads(RunRepo(base).get(run_id)["parametres_figes"])
    assert figes["cas_figes"] == [cid] and [l["jeu"] for l in figes["lignes_des_cas"][str(cid)]] == ["Mineur", "Limite basse", "Majeur"]


def test_falsifiable_les_valeurs_d_une_variable_a_la_corbeille_sont_gardees(base):
    """Revue : l'écran n'envoie pas les colonnes à la corbeille ; restaurée, la variable retrouve ses valeurs."""
    pid, cid, _, ids = _projet(base)
    TestDataRepo(base).supprimer_variable(pid, ids["resultat"], par="x")
    lignes = CaseDataRepo(base).lignes(cid)
    CaseDataRepo(base).remplacer(cid, pid, [{"id": l["id"], "nom": l["nom"], "valeurs": l["valeurs"]} for l in lignes])
    base.execute("UPDATE test_variable SET deleted_at='' WHERE id=?", (ids["resultat"],))
    base.commit()
    assert [v.get("resultat") for _, v in CaseDataRepo(base).niveaux(cid)] == ["Accès refusé", "Accès refusé", "Bienvenue"]


def test_falsifiable_un_nom_d_office_porte_a_un_autre_rang_est_refuse(base):
    pid, cid, _, _ = _projet(base)
    with pytest.raises(DonneeDeTestInvalide, match="nom donné d'office"):
        CaseDataRepo(base).remplacer(cid, pid, [{"nom": "Ligne 2", "valeurs": {}}, {"nom": "", "valeurs": {}}])
    CaseDataRepo(base).remplacer(cid, pid, [{"nom": "Ligne 1", "valeurs": {}}])   # à son propre rang : admis


def test_falsifiable_une_variable_d_un_autre_projet_est_refusee(base):
    pid, cid, _, _ = _projet(base)
    autre = ProjectRepo(base).create(name="Autre", connector_type="web", base_url="http://b")
    etrangere = TestDataRepo(base).creer_variable(autre, nom="age")
    with pytest.raises(DonneeDeTestInvalide, match="variable de ce projet"):
        CaseDataRepo(base).remplacer(cid, pid, [{"nom": "A", "valeurs": {etrangere: "17"}}])


def test_copier_un_cas_copie_ses_lignes(base):
    from testpilot.store.repositories import CaseGroupRepo
    pid, cid, _, _ = _projet(base)
    groupe = CaseGroupRepo(base).create(module_id=CaseRepo(base).get(cid)["module_id"], title="Copies")
    copie = CaseRepo(base).copier(cid, groupe)
    assert CaseDataRepo(base).niveaux(copie) == CaseDataRepo(base).niveaux(cid)


def test_falsifiable_l_apercu_montre_la_premiere_ligne_et_l_ecart(base):
    pid, cid, vid, _ = _projet(base)
    vu = service.apercu(base, cid, vid)
    assert vu["jeu"] == "Mineur" and 'l\'âge "16"' in vu["texte"] and vu["manques"] == []
    base.execute("UPDATE test_case_version SET feature_content=? WHERE id=?", (EN_DUR, vid))
    base.commit()
    assert any("{{age}}" in m for m in service.apercu(base, cid, vid)["manques"])


def test_l_api_dit_l_ecart(base):
    pid, cid, vid, _ = _projet(base)
    base.execute("UPDATE test_case_version SET feature_content=? WHERE id=?", (EN_DUR, vid))
    base.commit()
    assert any("{{age}}" in e for e in TestClient(app_mod.app).get(f"/api/cases/{cid}/donnees-de-test").json()["ecarts"])
