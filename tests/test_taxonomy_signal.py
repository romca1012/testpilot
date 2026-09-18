"""Décision 0015 — la taxonomie classe sur le SIGNAL, jamais sur le texte de l'agent.

Ces tests gardent une propriété, pas une implémentation : **rien de ce que l'agent rédige ne
doit changer un classement**. Le test central (`test_meme_exception_meme_classement_quel_que_soit_le_step`)
ÉCHOUAIT sur la version d'avant `0015` — c'est ce qui en fait une garde et non une description.

Rappel du risque (§4.4) : classer un `vrai_bug` en `test_a_reparer` lance la boucle de
réparation (`0014`) contre une application cassée — le faux négatif inacceptable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt


@dataclass
class FakeFailure:
    """Miroir de `behave_result.StepFailure` — seuls les champs lus par la taxonomie."""
    scenario_name: str = "Scénario"
    step_text: str = ""
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = ""


TYPE_ERROR = (
    'File "steps/helpdesk_steps.py", line 42, in step_impl\n'
    "    ticket = tickets[0][\"team_id\"]\n"
    "TypeError: 'int' object is not subscriptable"
)

# Les quatre libellés de la note 0015 : ils donnaient QUATRE classements pour ce seul TypeError.
STEPS_PIEGEUX = [
    'Alors le dernier ticket créé a le champ "team_id" pointant vers "Matériel"',
    "Alors le ticket est créé",
    'Alors la route "/tickets" répond',
    "Alors le timeout est respecté",
    "",
]


# ── Le défaut de 0015, en garde ───────────────────────────────────────────────
@pytest.mark.parametrize("step", STEPS_PIEGEUX)
def test_meme_exception_meme_classement_quel_que_soit_le_step(step):
    """Le nom du step n'a AUCUN effet : seul le type d'exception décide.

    ÉCHOUAIT avant 0015 — le même TypeError recevait quatre causes différentes.
    """
    cause = dt.classify_failure(FakeFailure(step_text=step, raw=TYPE_ERROR))
    assert cause == dt.BROKEN_TEST_CODE


def test_vrai_bug_reste_vrai_bug_meme_avec_un_step_piegeux():
    """La porte du faux négatif est fermée : le §4.4 tient quoi qu'écrive l'agent.

    Avant 0015, le mot « team_id » dans le libellé faisait basculer ce vrai bug applicatif en
    `test_a_reparer` — la boucle 0014 aurait réparé un test CORRECT.
    """
    bug = "AssertionError: le ticket devrait être en état 'validé', obtenu 'brouillon'"
    for step in ("Alors le ticket est validé",
                 'Alors le champ "team_id" du ticket est correct',
                 "Alors le timeout est respecté"):
        f = FakeFailure(step_text=step, raw=bug, failure_type="assertion")
        assert dt.classify_failure(f) == dt.ASSERTION_MISMATCH
        assert do.diagnose([f]).defect_origin == do.VRAI_BUG


def test_message_d_assertion_ecrit_par_l_agent_ne_decide_pas():
    """Le texte APRÈS le préfixe d'assertion est écrit par l'agent : il ne classe pas non plus.

    C'est le défaut exact de 0012 — le mot « rôle » dans un message d'agent avait produit un
    « Rôle manquant » ; la vraie cause (session anonyme) n'avait rien à voir. B (retirer le seul
    `step_text`) n'aurait pas fermé cette porte : d'où A.
    """
    f = FakeFailure(step_text="Alors le ticket est visible",
                    raw="AssertionError: permission refusée ? droit manquant ? introuvable",
                    failure_type="assertion")
    assert dt.classify_failure(f) == dt.ASSERTION_MISMATCH


# ── Le format que Behave produit VRAIMENT ─────────────────────────────────────
# Le premier jet de 0015 testait « AssertionError: … » — une forme que Behave n'émet JAMAIS
# (`model.py:1888` la remplace par « ASSERT FAILED: »). Le test passait donc en validant un monde
# qui n'existe pas, pendant que les assertions réelles retombaient sur les mots-clés. Ces
# tests-ci partent des messages RÉELLEMENT en base.

BEHAVE_ASSERT_REEL = (
    "ASSERT FAILED: Le formulaire achat vehicule a ete rendu malgre l'absence du role "
    "group_expert_metier. URL courante : http://localhost:10017/en/achat_vehicule/114. "
    "Verifier la logique _get_access_dei() du controleur."
)


def test_le_rendu_d_assertion_de_behave_est_reconnu():
    """Le vrai message du cas 6 (scenario_result #40) — sans « AssertionError » nulle part."""
    assert "AssertionError" not in BEHAVE_ASSERT_REEL          # le format réel, pas le supposé
    f = FakeFailure(step_text="Alors l'accès est refusé", raw=BEHAVE_ASSERT_REEL,
                    failure_type="unknown")
    assert dt.classify_failure(f) == dt.ASSERTION_MISMATCH


def test_le_faux_role_manquant_de_0012_ne_revient_pas():
    """Le témoin du cas 6 : « group_expert_metier » dans le message d'agent donnait `missing_role`.

    C'était une fausse piste suivie deux fois. Désormais : `assertion_mismatch` → `vrai_bug` → un
    humain tranche, ce qui est le régime honnête pour une assertion.
    """
    f = FakeFailure(raw=BEHAVE_ASSERT_REEL, failure_type="unknown")
    assert dt.classify_failure(f) != dt.MISSING_ROLE
    assert do.diagnose([f]).defect_origin == do.VRAI_BUG


@pytest.mark.parametrize("message", [
    "ASSERT FAILED: permission denied pour cet utilisateur",   # → sinon missing_role
    "ASSERT FAILED: le sélecteur est introuvable",             # → sinon wrong_field_name
    "ASSERT FAILED: mauvaise route /tickets",                   # → sinon wrong_navigation
    "ASSERT FAILED: le champ caché est resté vide",             # → sinon missing_server_context
])
def test_une_assertion_reste_une_assertion_quoi_qu_ecrive_l_agent(message):
    """LA garde du faux négatif sur données réalistes.

    Behave a déjà tranché « c'est une assertion » ; ce que l'agent raconte ensuite ne peut pas
    transformer un possible vrai bug en défaut d'environnement réparable.
    """
    f = FakeFailure(raw=message, failure_type="unknown")
    assert dt.classify_failure(f) == dt.ASSERTION_MISMATCH
    assert do.classify_defect_origin(dt.classify_failure(f)) == do.VRAI_BUG


def test_le_parser_reconnait_enfin_les_assertions_reelles():
    """Symptôme : `failure_type` valait `unknown` pour TOUTES les assertions réelles.

    Signal et symptôme étaient donc aveugles ensemble — seuls les mots-clés parlaient.
    """
    from testpilot.execution.behave_result import classify_failure as parse_symptome

    ftype, resume = parse_symptome(BEHAVE_ASSERT_REEL)
    assert ftype == "assertion"
    assert "achat vehicule" in resume


def test_le_parser_ne_confond_pas_une_assertion_avec_un_probleme_de_droits():
    from testpilot.execution.behave_result import classify_failure as parse_symptome

    ftype, _ = parse_symptome("ASSERT FAILED: permission denied pour cet utilisateur")
    assert ftype == "assertion"          # et non « permission »
    # Un VRAI refus de droits, lui, reste un problème de droits.
    ftype, _ = parse_symptome("odoo.exceptions.AccessError: Permission denied")
    assert ftype == "permission"


# ── Le signal décide ──────────────────────────────────────────────────────────
def test_broken_test_code_est_reparable_par_son_type():
    """Un TypeError dans NOTRE code : l'app n'y est pour rien → réparable, par construction.

    Avant 0015, un TypeError nu tombait en `unknown` → `indetermine` → le circuit refusait de
    réparer le cas le plus évidemment réparable.
    """
    f = FakeFailure(step_text="Alors le ticket est créé", raw=TYPE_ERROR)
    assert do.diagnose([f]).defect_origin == do.TEST_A_REPARER


@pytest.mark.parametrize("exc,attendu", [
    ("TypeError: 'int' object is not subscriptable", dt.BROKEN_TEST_CODE),
    ("AttributeError: 'NoneType' object has no attribute 'id'", dt.BROKEN_TEST_CODE),
    ("KeyError: 'team_id'", dt.BROKEN_TEST_CODE),
    ("NameError: name 'ticket' is not defined", dt.BROKEN_TEST_CODE),
    ("ModuleNotFoundError: No module named 'odoorpc'", dt.BROKEN_TEST_CODE),
    ("playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.",
     dt.WRONG_FIELD_NAME),
    ("AssertionError: attendu 3, obtenu 0", dt.ASSERTION_MISMATCH),
    ("odoo.exceptions.AccessError: Vous n'avez pas les droits", dt.MISSING_ROLE),
])
def test_le_type_d_exception_decide(exc, attendu):
    assert dt.classify_failure(FakeFailure(raw=exc)) == attendu


# ── Un même TimeoutError, deux causes distinctes (backlog 1.4) ────────────────────────────────
#
# Mesuré en run réel (résultat #1, staging Sapian, 2026-09-18) : un TimeoutError sur
# `wait_for_url` (session de connexion bloquée sur un formulaire SSO replié) classé
# `wrong_field_name` — alors qu'aucun champ ni sélecteur n'était en cause. Le nom de la classe
# seul ne distingue pas « élément introuvable » de « navigation qui n'arrive jamais » ; le
# journal d'appel Playwright, lui, le dit.

def test_un_timeout_sur_une_navigation_est_distingue_d_un_element_introuvable():
    """Le cas réel rejoué : même classe d'exception, cause différente selon ce qui était attendu."""
    navigation_bloquee = FakeFailure(raw=(
        "playwright._impl._errors.TimeoutError: Timeout 15000ms exceeded.\n"
        "=========================== logs ===========================\n"
        "waiting for navigation to \"https://sapian.example.com/web\" until 'load'\n"
        "============================================================"))
    element_introuvable = FakeFailure(raw=(
        "playwright._impl._errors.TimeoutError: Locator.click: Timeout 8000ms exceeded.\n"
        "waiting for get_by_text(\"Nouveau\", exact=True).first"))

    assert dt.classify_failure(navigation_bloquee) == dt.WRONG_NAVIGATION
    assert dt.classify_failure(element_introuvable) == dt.WRONG_FIELD_NAME


def test_exception_type_retient_la_derniere_de_la_chaine():
    """Dans un `raise ... from ...`, c'est la DERNIÈRE qui a interrompu le step."""
    chaine = ("ValueError: rien trouvé\n"
              "\nThe above exception was the direct cause of the following exception:\n\n"
              "TypeError: 'NoneType' object is not subscriptable")
    assert dt.exception_type(chaine) == "TypeError"


def test_exception_type_vide_si_aucune():
    assert dt.exception_type("le test a échoué") == ""
    assert dt.exception_type("") == ""


def test_valueError_reste_ambigu_et_ne_court_circuite_pas_le_symptome():
    """`ValueError` est volontairement HORS du signal : odoorpc le lève légitimement.

    Il doit donc retomber sur le symptôme du parser, pas être classé de force.
    """
    f = FakeFailure(raw="ValueError: aucun enregistrement", failure_type="odoo_data")
    assert dt.classify_failure(f) == dt.MISSING_SERVER_CONTEXT


# ── Arbitrage Q4 : missing_server_context est une VOIE DÉGRADÉE ───────────────
def test_missing_server_context_ne_decide_jamais_seul_de_la_reparabilite():
    """Aucune exception ne produit cette cause : elle ne vient que d'un texte.

    Elle INFORME (le libellé s'affiche) mais passe par `indetermine` → confirmation humaine,
    et n'autorise donc jamais la boucle 0014 sur une simple correspondance de mots.
    """
    assert do.classify_defect_origin(dt.MISSING_SERVER_CONTEXT) == do.INDETERMINE
    f = FakeFailure(raw="le champ caché est resté vide", failure_type="odoo_data")
    verdict = do.diagnose([f])
    assert verdict.cause_category == dt.MISSING_SERVER_CONTEXT  # informe
    assert verdict.requires_human_confirmation                   # mais ne tranche pas


@pytest.mark.parametrize("mot", ["team_id", "many2one", "accesserror", "group_"])
def test_les_mots_cles_de_domaine_ont_quitte_la_taxonomie_generique(mot):
    """Odoo ne doit pas être câblé dans un module qui se déclare connector-agnostic."""
    source = dt.__file__
    with open(source, encoding="utf-8") as fh:
        contenu = fh.read()
    tous_les_mots = [kw for mots in dt._KEYWORDS.values() for kw in mots]
    assert mot not in tous_les_mots, f"{mot!r} est encore un mot-clé de classement"
    assert contenu.count(mot) <= 3, f"{mot!r} apparaît hors commentaire dans {source}"


# ── step_text : persisté pour l'audit, jamais lu pour classer ─────────────────
def test_step_text_est_persiste_mais_ne_classe_pas():
    """Migration 10 : la trace existe (auditable) ET reste hors du classement."""
    from testpilot.store import db as store_db
    from testpilot.store.repositories import ExecutionRepo

    conn = store_db.get_initialized_db(":memory:")
    assert "step_text" in store_db._column_names(conn, "scenario_result")

    conn.execute("INSERT INTO project (name, created_at) VALUES ('P','now')")
    conn.execute("INSERT INTO test_case (title, created_at, updated_at) VALUES ('C','now','now')")
    conn.execute("INSERT INTO test_case_version (test_case_id, version_number, created_at)"
                 " VALUES (1, 1, 'now')")
    conn.commit()

    execs = ExecutionRepo(conn)
    eid = execs.create(test_case_id=1, version_id=1)
    execs.add_scenario_result(
        execution_id=eid, scenario_name="S", execution_status="technical_error",
        functional_status="indetermine", cause_category=dt.BROKEN_TEST_CODE,
        step_text='Alors le champ "team_id" pointe vers "Matériel"',
    )
    row = execs.list_scenario_results(eid)[0]
    assert row["step_text"] == 'Alors le champ "team_id" pointe vers "Matériel"'
    # …et il n'a pas influencé la cause : le signal seul l'a décidée.
    assert row["cause_category"] == dt.BROKEN_TEST_CODE
    conn.close()


def test_le_step_en_echec_remonte_du_parser_jusqu_au_verdict():
    """Le chaînon qui manquait : sans lui, la colonne serait un champ MORT (cf. migration 7)."""
    from testpilot.verdict import status

    @dataclass
    class FakeScenario:
        name: str = "S"
        status: str = "failed"
        error: str = "boom"

    v = status.scenario_verdict(
        FakeScenario(),
        [FakeFailure(step_text="Alors le ticket est créé", raw=TYPE_ERROR)],
    )
    assert v.step_text == "Alors le ticket est créé"
    assert v.cause_category == dt.BROKEN_TEST_CODE
