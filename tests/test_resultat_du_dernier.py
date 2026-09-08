"""Le DERNIER résultat d'un cas — et la bascule entre les deux MODES D'EXÉCUTION, dans les deux sens.

⚠️ **Le défaut le plus probable de tout ce chantier, écrit ici avant d'exister.** Un cas porte un
raccourci de son dernier résultat (`last_*`), lu par toutes les listes. Un statut SAISI À LA MAIN y
court-circuite la dérivation des deux axes — c'est ce qui permet à une exécution manuelle de
s'afficher. Mais si l'exécution automatique suivante oublie de **remettre `last_statut_manuel` à
vide**, la saisie continue de court-circuiter : le cas affiche indéfiniment le statut constaté à la
main, quels que soient les runs qui suivent.

Ce défaut ne lève rien, ne casse aucun test d'exécution, et ne se voit qu'en croisant deux écrans
— la liste dit « Passed » pendant que le rapport dit « erreur technique ». D'où ce fichier, qui
exerce la bascule dans les **deux** sens.

Le second invariant : **un résultat manuel n'écrit JAMAIS les deux axes.** Saisir « passed » ne
doit pas produire « exécution=succès, fonctionnel=conforme » — ce serait fabriquer une mesure que
personne n'a faite, exactement ce que le produit refuse.

⚠️ **Deux campagnes, et c'est le décor obligé depuis que le mode vit sur la campagne** (2026-08-04)
: un cas se joue à la machine dans une campagne automatique, et à la main dans une campagne
manuelle. Le raccourci `last_*` du CAS, lui, est global — c'est justement là que les deux modes se
croisent, et donc là que la bascule doit être juste.
"""
import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ResultRepo,
    RunRepo,
    VersionRepo,
)
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE, statut_de_test


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "resultats.db")
    yield c
    c.close()


@pytest.fixture
def campagne(conn):
    """Un projet, un cas, et ses DEUX campagnes — automatique et manuelle."""
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="# f", steps_content="# s")
    auto = RunRepo(conn).create(project_id=pid, name="Recette auto", case_ids=[cid],
                                mode=MODE_AUTOMATIQUE)
    manuel = RunRepo(conn).create(project_id=pid, name="Recette manuelle", case_ids=[cid],
                                  mode=MODE_MANUELLE)
    return {"projet": pid, "cas": cid, "version": vid, "run": auto, "manuel": manuel}


def _executer(conn, campagne, *, execution="success", fonctionnel="conforme"):
    """Une exécution COMPLÈTE : la ligne, sa clôture, et le raccourci sur le cas — l'enchaînement
    exact de `run_service`."""
    eid = ExecutionRepo(conn).create(test_case_id=campagne["cas"], version_id=campagne["version"])
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (campagne["run"], eid))
    conn.commit()
    ExecutionRepo(conn).finalize(
        eid, execution_status=execution, functional_status=fonctionnel, scenarios_total=1,
        scenarios_passed=1 if execution == "success" else 0,
        scenarios_failed=0 if execution == "success" else 1,
        cost_usd=0.0, iterations=1, duration_seconds=0.1)
    CaseRepo(conn).update_last_outcome(
        campagne["cas"], execution_status=execution, functional_status=fonctionnel,
        executed_at="2026-08-04T10:00:00+00:00")
    return eid


def _saisir(conn, campagne, statut, **kwargs):
    """Une exécution MANUELLE : elle a lieu dans la campagne manuelle, jamais dans l'automatique."""
    return ResultRepo(conn).saisir(run_id=campagne["manuel"], case_id=campagne["cas"],
                                   statut=statut, **kwargs)


def _statut_affiche(conn, case_id: int) -> str:
    """Ce que l'écran montre, calculé comme le serveur le calcule."""
    c = CaseRepo(conn).get(case_id)
    return statut_de_test(c["last_execution_status"], c["last_functional_status"],
                          c["last_statut_manuel"])


# ── La bascule, dans les deux sens ───────────────────────────────────────────

def test_une_saisie_manuelle_prime_sur_la_derniere_execution(conn, campagne):
    _executer(conn, campagne, execution="success", fonctionnel="conforme")
    assert _statut_affiche(conn, campagne["cas"]) == "passed"

    _saisir(conn, campagne, "blocked", comment="environnement indisponible", created_by="Romaric")

    assert _statut_affiche(conn, campagne["cas"]) == "blocked"


def test_une_execution_EFFACE_la_saisie_manuelle_precedente(conn, campagne):
    """🔴 **LE test de ce fichier.** Sans le `last_statut_manuel=''` de `update_last_outcome`,
    ce cas afficherait « blocked » pour toujours — y compris après dix runs verts."""
    _saisir(conn, campagne, "blocked", created_by="Romaric")
    assert _statut_affiche(conn, campagne["cas"]) == "blocked"

    _executer(conn, campagne, execution="success", fonctionnel="conforme")

    cas = CaseRepo(conn).get(campagne["cas"])
    assert cas["last_statut_manuel"] == "", "la saisie manuelle n'a PAS été effacée"
    assert cas["last_result_mode"] == MODE_AUTOMATIQUE
    assert _statut_affiche(conn, campagne["cas"]) == "passed"


def test_une_execution_en_ECHEC_efface_aussi_la_saisie_manuelle(conn, campagne):
    """La bascule ne doit pas dépendre du VERDICT : ce qui compte est qu'une mesure a eu lieu.
    Ne l'effacer que sur un succès laisserait un « passed » saisi à la main masquer une erreur
    technique — le mensonge exact que le produit combat."""
    _saisir(conn, campagne, "passed")

    _executer(conn, campagne, execution="technical_error", fonctionnel="indetermine")

    assert CaseRepo(conn).get(campagne["cas"])["last_statut_manuel"] == ""
    # Le fonctionnel prime sur le déroulement : `indetermine` après un test qui a démarré donne
    # « retest » (à rejouer), pas « blocked ». Ce qui compte ici est que le « passed » saisi à la
    # main ne s'affiche plus.
    assert _statut_affiche(conn, campagne["cas"]) == "retest"


def test_saisir_n_invente_JAMAIS_les_deux_axes(conn, campagne):
    """Saisir « passed » ne doit pas écrire « exécution=succès / fonctionnel=conforme » : aucune
    machine n'a rien constaté. Les axes restent tels qu'ils étaient — vides ici."""
    _saisir(conn, campagne, "passed")

    cas = CaseRepo(conn).get(campagne["cas"])
    assert cas["last_execution_status"] is None
    assert cas["last_functional_status"] is None
    assert cas["last_statut_manuel"] == "passed"
    assert cas["last_result_mode"] == MODE_MANUELLE


# ── Le registre lui-même ─────────────────────────────────────────────────────

def test_clore_une_execution_l_inscrit_au_registre_avec_le_compte_de_service(conn, campagne):
    from testpilot import config

    eid = _executer(conn, campagne)
    dernier = ResultRepo(conn).dernier(campagne["run"], campagne["cas"])

    assert (dernier["mode"], dernier["execution_id"]) == (MODE_AUTOMATIQUE, eid)
    assert dernier["statut_manuel"] == ""
    # L'auteur est le compte de service, RECOPIÉ à l'écriture (le changer ensuite ne réécrit rien).
    assert dernier["created_by"] == config.SERVICE_ACCOUNT_NAME


def test_une_execution_HORS_campagne_n_entre_pas_au_registre(conn, campagne):
    """Le registre répond à « résultat du cas C DANS la campagne R ». Sans campagne, la question
    n'existe pas — et y inscrire la ligne casserait la mesure de qualité de la génération, qui
    compte les exécutions."""
    eid = ExecutionRepo(conn).create(test_case_id=campagne["cas"], version_id=campagne["version"])
    ExecutionRepo(conn).finalize(
        eid, execution_status="success", functional_status="conforme", scenarios_total=1,
        scenarios_passed=1, scenarios_failed=0, cost_usd=0.0, iterations=1, duration_seconds=0.1)

    assert conn.execute("SELECT COUNT(*) AS n FROM test_result").fetchone()["n"] == 0


def test_clore_deux_fois_la_meme_execution_n_inscrit_qu_une_ligne(conn, campagne):
    """`finalize` peut être rejoué (chemin d'échec, reprise). Le registre compte des RÉSULTATS,
    pas des appels."""
    eid = _executer(conn, campagne)
    ExecutionRepo(conn).finalize(
        eid, execution_status="success", functional_status="conforme", scenarios_total=1,
        scenarios_passed=1, scenarios_failed=0, cost_usd=0.0, iterations=1, duration_seconds=0.2)

    assert len(ResultRepo(conn).historique(campagne["run"], campagne["cas"])) == 1


def test_corriger_un_resultat_c_est_en_AJOUTER_un(conn, campagne):
    """Aucune suppression, aucune modification : l'erreur de saisie reste visible dans
    l'historique. C'est la même règle que la suppression douce — on ne réécrit pas le passé."""
    resultats = ResultRepo(conn)
    _saisir(conn, campagne, "failed", comment="je me suis trompé", created_by="Romaric")
    _saisir(conn, campagne, "passed", comment="correction", created_by="Romaric")

    historique = resultats.historique(campagne["manuel"], campagne["cas"])
    assert [r["statut_manuel"] for r in historique] == ["failed", "passed"]
    assert resultats.dernier(campagne["manuel"], campagne["cas"])["comment"] == "correction"


def test_untested_n_est_pas_saisissable(conn, campagne):
    """« Non testé » est l'ABSENCE de résultat. Le saisir fabriquerait une ligne qui n'affirme
    rien, indiscernable de « pas encore de résultat » — l'absence le dit déjà, et gratuitement."""
    with pytest.raises(ValueError):
        _saisir(conn, campagne, "untested")
    with pytest.raises(ValueError):
        _saisir(conn, campagne, "")


def test_les_derniers_du_run_rendent_UNE_ligne_par_cas(conn, campagne):
    """L'écran d'une campagne lit tous ses cas d'un coup : une requête, pas une par cas."""
    autre = CaseRepo(conn).create(title="Second", module_id=None, feature_slug="second")
    resultats = ResultRepo(conn)
    _saisir(conn, campagne, "failed")
    _saisir(conn, campagne, "passed")
    resultats.saisir(run_id=campagne["manuel"], case_id=autre, statut="retest")

    derniers = resultats.derniers_du_run(campagne["manuel"])
    assert set(derniers) == {campagne["cas"], autre}
    assert derniers[campagne["cas"]]["statut_manuel"] == "passed"   # le DERNIER, pas le premier
    assert derniers[autre]["statut_manuel"] == "retest"
