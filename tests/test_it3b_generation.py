"""IT-3b (décisions A57 à A59, porteur, 2026-10-19) — l'IA technique écrit UN test qui emploie les variables que les lignes
du cas font varier ; son essai sur le bac à sable joue la PREMIÈRE ligne.

Ce que ces tests gardent :
1. les variables des lignes du cas sont REQUISES dans le test, comme une variable que le cas cite (A39) — même PT-02f éteint ;
   un test qui ne les écrit pas est refusé à l'écriture (sinon A59 le bloquerait à l'exécution) ;
2. l'agent apprend que le cas est joué une fois par ligne et doit écrire un seul scénario — il ne reçoit que des NOMS,
   jamais une valeur ; sans ligne, son message est celui d'avant, octet pour octet ;
3. l'essai joue la première ligne, posée par-dessus le jeu « Par défaut » ;
4. l'automatisation d'un cas transmet ses lignes à l'agent.
Aucun appel au modèle de langage : la boucle est arrêtée avant.
"""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.generation import interrupteurs, variables_de_test

VARIABLES = [{"nom": "client", "description": ""}, {"nom": "age", "description": "âge saisi"},
             {"nom": "resultat", "description": ""}]
METIER = {"title": "Accès selon l'âge", "preconditions": "", "steps": ["Je renseigne l'âge"],
          "expected_result": "Le message attendu s'affiche", "variables_des_lignes": ["age", "resultat"]}
PREMIERE_LIGNE = {"age": "16", "resultat": "Accès refusé"}


@pytest.mark.parametrize("pt02f", ["1", "0"])
def test_falsifiable_les_variables_des_lignes_sont_requises_meme_pt02f_eteint(monkeypatch, pt02f):
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, pt02f)

    montrees, requises, _ = variables_de_test.du_cas(VARIABLES, METIER)

    assert requises == frozenset({"age", "resultat"})
    assert {"age", "resultat"} <= {v["nom"] for v in montrees}
    feature_en_dur = 'Fonctionnalité: F\n  Scénario: S\n    Quand je renseigne l\'âge "16"\n'
    assert len(variables_de_test.refus_variables_du_cas(feature_en_dur, requises)) == 2, "écrire « 16 » en dur est refusé"


def test_sans_ligne_rien_de_plus_n_est_requis(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "0")
    sans = {k: v for k, v in METIER.items() if k != "variables_des_lignes"}
    assert variables_de_test.du_cas(VARIABLES, sans)[1] == frozenset()


def test_falsifiable_l_agent_apprend_que_le_cas_est_joue_par_ligne_sans_aucune_valeur():
    section = variables_de_test.section_prompt(VARIABLES, ["age", "resultat"])

    assert "UNE FOIS PAR LIGNE" in section and "`{{age}}`, `{{resultat}}`" in section and "UN SEUL" in section
    assert "16" not in section and "Accès refusé" not in section
    assert variables_de_test.section_prompt(VARIABLES, []) == variables_de_test.section_prompt(VARIABLES), "sans ligne : d'avant"
    assert "UNE FOIS PAR LIGNE" not in variables_de_test.section_prompt(VARIABLES, ["inconnue"])


def _plan():
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[])


def test_falsifiable_l_essai_joue_la_premiere_ligne_et_le_message_ne_montre_aucune_valeur(monkeypatch, tmp_path):
    from testpilot.generation import agent as agent_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_mod.domain_model, "DOMAIN_DIR", tmp_path / "domain")   # jamais l'annuaire réel du poste
    monkeypatch.setenv(interrupteurs.ENV_VARIABLES_DE_TEST, "1")
    monkeypatch.setenv(interrupteurs.ENV_CAS_DIT_SES_DONNEES, "1")
    vus = []

    def _boucle(**kw):
        vus.append((kw["ctx"], kw["state"].messages[0]["content"]))
        raise RuntimeError("arrêt du test")

    monkeypatch.setattr(agent_mod, "run_loop", _boucle)
    projet = {"id": 1, "connector_type": "web", "variables_de_test": VARIABLES,
              "valeurs_de_test_par_defaut": {"client": "Dupont SARL", "age": "30"}}
    with pytest.raises(RuntimeError, match="arrêt du test"):
        agent_mod.GenerationAgent(llm=object(), connector=None, dry_runner=None).generate(
            _plan(), metier=METIER, projet=projet, valeurs_d_essai=PREMIERE_LIGNE)

    [(ctx, message)] = vus
    assert ctx.valeurs_de_test == {"client": "Dupont SARL", "age": "16", "resultat": "Accès refusé"}
    assert {"age", "resultat"} <= set(ctx.variables_du_cas)
    texte = message if isinstance(message, str) else message[0]["text"]
    assert "UNE FOIS PAR LIGNE" in texte
    assert "Accès refusé" not in texte and "Dupont SARL" not in texte, "l'agent ne reçoit que des noms"


def test_falsifiable_automatiser_un_cas_transmet_ses_lignes(tmp_path, monkeypatch):
    from testpilot.api.services import generation_service
    from testpilot.connectors import runtime_env
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseDataRepo, CaseRepo, ModuleRepo, ProjectRepo, TestDataRepo, VersionRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(runtime_env, "verifier_connexion", lambda projet: None)
    conn = get_initialized_db(tmp_path / "db.sqlite")
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Accès", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="", steps_content="",
                                   title="Accès", test_steps='["Je renseigne l\'âge"]', expected_result="Le message s'affiche")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    ids = {n: depot.creer_variable(pid, nom=n) for n in ("age", "resultat")}
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": "Mineur", "valeurs": {ids["age"]: "16", ids["resultat"]: "Non"}},
                                            {"nom": "Majeur", "valeurs": {ids["age"]: "18"}}])

    _, travail = generation_service.start_automation(conn, cid)

    assert travail["metier"]["variables_des_lignes"] == ["age", "resultat"]
    # Revue du 2026-10-19 : aucune VALEUR dans le métier — il part dans la file des tâches et peut être sérialisé en entier.
    assert "16" not in str(travail) and "Non" not in str(travail)
    conn.close()


# ── Point de vigilance : aucun « Alors » n'emploie les variables des lignes (revue du 2026-10-19) ───────────────────────────

ALORS_EN_DUR = """# language: fr
Fonctionnalité: F
  Scénario: Accès
    Quand je renseigne l'âge "{{age}}"
    Et je note "{{resultat}}"
    Alors la page affiche le texte "Accès refusé"
    Et le bouton "Entrer" n'est pas affiché
"""


def test_falsifiable_un_alors_qui_n_emploie_aucune_variable_des_lignes_est_signale():
    """`{{resultat}}` écrit dans une étape qui ne vérifie rien, l'« Alors » en dur : les deux gardes de présence passent,
    une application qui refuse aussi à 18 ans sortirait « conforme » sur toutes les lignes. Le relecteur doit le voir."""
    avis = variables_de_test.lint_alors_sans_variable_des_lignes(ALORS_EN_DUR, ["age", "resultat"])
    assert [a["kind"] for a in avis] == [variables_de_test.ALORS_IDENTIQUE] and "{{resultat}}" in avis[0]["message"]

    # Le test sain : `{{resultat}}` VÉRIFIÉ dans l'« Alors », jamais saisi ailleurs (2e passe : saisi puis relu ne compte pas).
    sain = ALORS_EN_DUR.replace('    Et je note "{{resultat}}"\n', '')
    employe = sain.replace('affiche le texte "Accès refusé"', 'affiche le texte "{{resultat}}"')
    assert variables_de_test.lint_alors_sans_variable_des_lignes(employe, ["age", "resultat"]) == []
    # « Et » après « Alors » est un « Alors » (type de step de Behave, jamais le libellé)
    dans_le_et = sain.replace("le bouton \"Entrer\" n'est pas affiché", 'le texte "{{resultat}}" est affiché')
    assert variables_de_test.lint_alors_sans_variable_des_lignes(dans_le_et, ["age", "resultat"]) == []
    assert variables_de_test.lint_alors_sans_variable_des_lignes(ALORS_EN_DUR, []) == [], "sans ligne : rien"


def test_le_libelle_du_point_de_vigilance_existe_a_l_ecran():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "ReviewGate.vue").read_text(encoding="utf-8")
    assert f"{variables_de_test.ALORS_IDENTIQUE}: 'donnée'" in source


def test_falsifiable_un_alors_qui_relit_la_saisie_ne_fait_pas_taire_le_signal():
    """Revue, 2e passe : « Alors le champ "Âge" contient "{{age}}" » relit la valeur saisie, il ne vérifie aucun résultat."""
    relit = ALORS_EN_DUR.replace('Alors la page affiche le texte "Accès refusé"',
                                 'Alors le champ "Âge" contient "{{age}}"\n    Et la page affiche le texte "Accès refusé"')
    assert [a["kind"] for a in variables_de_test.lint_alors_sans_variable_des_lignes(relit, ["age", "resultat"])] == [
        variables_de_test.ALORS_IDENTIQUE]


def test_une_regle_un_plan_et_un_bloc_de_texte_sont_lus_une_seule_fois():
    regle = ('# language: fr\nFonctionnalité: F\n  Règle: R\n    Scénario: S\n      Quand je renseigne l\'âge "{{age}}"\n'
             '      Alors la page affiche le texte "Accès refusé"\n')
    assert len(variables_de_test.lint_alors_sans_variable_des_lignes(regle, ["age"])) == 1, "sous une Règle : lu"
    bloc = ('# language: fr\nFonctionnalité: F\n  Scénario: S\n    Quand je renseigne l\'âge "{{age}}"\n'
            '    Alors la page contient :\n      """\n      {{resultat}}\n      """\n')
    assert variables_de_test.lint_alors_sans_variable_des_lignes(bloc, ["age", "resultat"]) == [], "bloc de texte : lu"
    plan = ('# language: fr\nFonctionnalité: F\n  Plan du scénario: P\n    Quand je saisis "<q>" et "{{age}}"\n'
            '    Alors la page affiche le texte "Non"\n    Exemples: E\n      | q |\n      | 1 |\n      | 2 |\n')
    assert len(variables_de_test.lint_alors_sans_variable_des_lignes(plan, ["age"])) == 1, "un plan : un avis, pas un par instance"


def test_falsifiable_l_automatisation_donne_la_premiere_ligne_a_l_essai(tmp_path, monkeypatch):
    """Câblage (revue, 2e passe) : `run_automation` relit la première ligne du cas et la passe à `generate`."""
    from testpilot.api.services import generation_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseDataRepo, CaseRepo, ModuleRepo, ProjectRepo, TestDataRepo

    db = tmp_path / "db.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(db)
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Accès", module_id=mid, feature_slug="acces")
    age = TestDataRepo(conn).creer_variable(pid, nom="age")
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": "Mineur", "valeurs": {age: "16"}}, {"nom": "Majeur", "valeurs": {age: "18"}}])
    conn.close()
    vus = {}

    class _Arret(Exception):
        pass

    class _Agent:
        def __init__(self, **kw):
            pass

        def generate(self, plan, **kw):
            vus.update(kw)
            raise _Arret()

    class _Connecteur:
        def connect(self):
            pass

        def close(self):
            pass

    class _Analyse:   # aucun appel au modèle de langage
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return object()

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.connectors.factory as factory
    import testpilot.generation.agent as agent_mod
    monkeypatch.setattr(agent_mod, "GenerationAgent", _Agent)
    monkeypatch.setattr(factory, "build_connector", lambda projet: _Connecteur())
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    try:
        generation_service.run_automation("j", case_id=cid, module_id=mid, slug="acces", spec_content="spec",
                                          metier={"title": "Accès", "steps": ["x"], "expected_result": "y"})
    except Exception:   # l'arrêt du faux agent finit en échec de la tâche : seul l'appel compte ici
        pass
    assert vus.get("valeurs_d_essai") == {"age": "16"}, vus


def test_falsifiable_le_signal_arrive_sur_la_fiche_du_cas_sans_appel_de_correction(tmp_path, monkeypatch):
    """Câblage (revue, 2e passe) : l'avis passe par `lint_warnings_for_version` (fiche, auto-approbation) ; il ne déclenche
    AUCUNE correction par l'IA (le relecteur décide)."""
    from testpilot.api.services import generation_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseDataRepo, CaseRepo, ModuleRepo, ProjectRepo, TestDataRepo, VersionRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(tmp_path / "db.sqlite")
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Accès", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="acces")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=ALORS_EN_DUR, steps_content="")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    ids = {n: TestDataRepo(conn).creer_variable(pid, nom=n) for n in ("age", "resultat")}
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": "A", "valeurs": {ids["age"]: "16", ids["resultat"]: "Non"}}])

    avis = generation_service.lint_warnings_for_version(conn, CaseRepo(conn).get(cid), VersionRepo(conn).list_for_case(cid), vid)
    assert variables_de_test.ALORS_IDENTIQUE in [a["kind"] for a in avis]

    from testpilot.generation import correction_agent
    appels = []
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: appels.append(kw))
    generation_service._finaliser_version_generee(conn, cid, vid, module_name="acces", dry_runner=object())
    assert appels == [], "aucun appel de correction pour ce seul avis"
    conn.close()
