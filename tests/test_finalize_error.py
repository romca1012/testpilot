"""Le filet d'un run planté ne doit pas tomber avec ce qu'il rattrape.

`_finalize_error` écrivait le verdict d'échec avec la connexion DU RUN — celle-là même qui peut
être la cause du plantage. L'échec de l'écriture était avalé par un `except` muet et la ligne
restait `not_executed` **alors que le test avait tourné** : « affiché ≠ réel » (§4.6), et un
statut qui n'est pas la conséquence d'une exécution réelle (§4.2).

Motif de la journée, une fois de plus : *l'absence de signal prise pour un signal positif* — une
ligne `not_executed` se lit « n'a jamais tourné », l'état le plus rassurant, alors qu'elle
signifie ici « a tourné, a planté, verdict perdu ».
"""

from __future__ import annotations

import logging

import pytest

from testpilot.api.services import run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, VersionRepo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "f.db")
    yield c
    c.close()


def _cas(conn):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


class _ConnMorte:
    """Une connexion qui échoue à tout — le cas où la base EST la cause du plantage."""

    def execute(self, *a, **k):
        raise RuntimeError("database is locked")

    def commit(self):
        raise RuntimeError("database is locked")


def test_le_verdict_est_ecrit_par_le_chemin_normal(conn):
    cid, _vid, eid = _cas(conn)
    run_service._finalize_error(conn, eid, cid, "Odoo injoignable")

    execution = ExecutionRepo(conn).get(eid)
    assert execution["execution_status"] == "technical_error"
    assert execution["functional_status"] == "indetermine"
    assert "Odoo injoignable" in execution["error_message"]


def test_la_raison_du_plantage_est_PERSISTEE_pas_seulement_loguee(conn):
    """`message` était un paramètre MORT : reçu, jamais écrit.

    L'écran affichait « erreur technique » sans le moindre pourquoi — la seule trace vivait dans
    les logs du serveur, hors de portée de l'humain qui doit trancher.
    """
    cid, _vid, eid = _cas(conn)
    run_service._finalize_error(conn, eid, cid, "ConnectionRefusedError: [Errno 111] port 10017")

    assert "port 10017" in ExecutionRepo(conn).get(eid)["error_message"]


def test_le_filet_tient_quand_la_connexion_du_run_est_morte(conn, tmp_path, monkeypatch):
    """LE test du défaut : la connexion passée échoue, le verdict doit être écrit quand même.

    Avant, l'exception de `finalize()` était avalée et la ligne restait `not_executed`.
    """
    cid, _vid, eid = _cas(conn)
    # `_finalize_error` doit se rabattre sur une connexion NEUVE, ouverte sur la même base.
    monkeypatch.setattr(run_service.config, "DB_PATH", tmp_path / "f.db")

    run_service._finalize_error(_ConnMorte(), eid, cid, "boom pendant le run")

    execution = ExecutionRepo(conn).get(eid)
    assert execution["execution_status"] == "technical_error"   # et NON 'not_executed'
    assert "boom pendant le run" in execution["error_message"]
    assert CaseRepo(conn).get(cid)["last_execution_status"] == "technical_error"


def test_conn_None_est_traite_comme_une_connexion_morte(conn, tmp_path, monkeypatch):
    """Le cas où l'OUVERTURE elle-même a échoué : `run_execution` passe alors `conn=None`."""
    cid, _vid, eid = _cas(conn)
    monkeypatch.setattr(run_service.config, "DB_PATH", tmp_path / "f.db")

    run_service._finalize_error(None, eid, cid, "get_initialized_db a échoué")

    assert ExecutionRepo(conn).get(eid)["execution_status"] == "technical_error"


def test_la_perte_du_verdict_est_CRITICAL_jamais_silencieuse(conn, tmp_path, monkeypatch, caplog):
    """Si même le secours échoue, on ne se tait pas : un statut faux doit être bruyant.

    C'est la seule issue honnête restante — mais elle ne doit jamais ressembler à un succès.
    """
    cid, _vid, eid = _cas(conn)

    def _pas_de_secours(*a, **k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(run_service, "get_initialized_db", _pas_de_secours)

    with caplog.at_level(logging.CRITICAL):
        run_service._finalize_error(_ConnMorte(), eid, cid, "cause initiale")

    critiques = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert critiques, "la perte d'un verdict ne doit jamais passer inaperçue"
    assert "PERDU" in critiques[0].getMessage()
    assert "cause initiale" in critiques[0].getMessage()   # la cause n'est pas jetée
    # Le constat honnête : la ligne EST restée fausse — on l'a signalée, pas maquillée.
    assert ExecutionRepo(conn).get(eid)["execution_status"] == "not_executed"


def test_un_echec_d_ouverture_ne_laisse_pas_l_execution_bloquee_en_cours(tmp_path, monkeypatch):
    """`get_initialized_db` vivait HORS du `try` : son échec sautait le filet ET le `finally`.

    L'exécution restait alors dans `_RUNNING` pour toujours — « en cours » à l'écran, à jamais.
    """
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "g.db")
    cid, vid, eid = _cas(conn)
    conn.close()

    monkeypatch.setattr(run_service.config, "DB_PATH", tmp_path / "g.db")
    appels = {"n": 0}

    def _ouvre(*a, **k):
        # Le 1er appel (celui de `run_execution`) échoue ; le secours de `_finalize_error` passe.
        appels["n"] += 1
        if appels["n"] == 1:
            raise RuntimeError("base indisponible")
        return get_initialized_db(tmp_path / "g.db")

    monkeypatch.setattr(run_service, "get_initialized_db", _ouvre)
    run_service._RUNNING.add(eid)

    run_service.run_execution(eid, "cas", cid, vid)

    assert eid not in run_service._RUNNING          # plus jamais « en cours » pour toujours
    verif = get_initialized_db(tmp_path / "g.db")
    assert ExecutionRepo(verif).get(eid)["execution_status"] == "technical_error"
    assert "base indisponible" in ExecutionRepo(verif).get(eid)["error_message"]
    verif.close()
