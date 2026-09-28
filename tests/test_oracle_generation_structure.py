"""Lot 07e (C5, D7) — même garantie STRUCTURELLE que D8 pour les comptes : l'agent de génération ne
voit JAMAIS l'adresse, l'authentification ni la définition d'une requête d'oracle — seulement les
NOMS déclarés (`oracle_requetes_disponibles`), exactement comme il ne voit que des libellés de
compte (D8, précision 2).
"""

from __future__ import annotations

from pathlib import Path

from testpilot.connectors import oracle_config as _oracle
from testpilot.generation.prompt import _section_oracle
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo

RACINE = Path(__file__).resolve().parent.parent


def _sources(*dossiers) -> list[Path]:
    fichiers: list[Path] = []
    for d in dossiers:
        p = RACINE / d
        fichiers += [p] if p.is_file() else sorted(p.rglob("*.py"))
    return [f for f in fichiers if "__pycache__" not in f.parts and "generated" not in f.parts]


def test_structure_la_generation_n_a_aucun_chemin_vers_un_secret_ni_une_definition_d_oracle():
    """Rien de `src/testpilot/generation/` ne touche la config brute de l'oracle (adresse,
    authentification, définition de requête) ni la variable qui la transporte au sous-processus —
    seul `oracle_requetes_disponibles` (des noms) doit y circuler."""
    interdits = ("oracle_auth", "oracle_base_url", "OracleHttp", "oracle_http",
                 "oracle_config", _oracle.ENV_ORACLE, "oracle_queries")
    fautifs = [(f.relative_to(RACINE).as_posix(), mot) for f in _sources("src/testpilot/generation")
               for mot in interdits if mot in f.read_text(encoding="utf-8")]
    assert fautifs == []


def test_le_message_de_generation_liste_les_noms_et_interdit_d_en_inventer():
    section = _section_oracle(["tickets_ouverts", "clients_actifs"])

    assert '« tickets_ouverts »' in section and '« clients_actifs »' in section
    assert 'l\'oracle "<nom>" renvoie' in section
    assert "N'invente JAMAIS" in section
    assert _section_oracle([]) == "" and _section_oracle(None) == ""


def test_repo_get_expose_les_noms_de_requetes_jamais_l_adresse_ni_l_authentification(tmp_path, monkeypatch):
    """Bout en bout depuis le dépôt : `ProjectRepo.get()` calcule `oracle_requetes_disponibles`
    (comme `comptes_libelles`) — c'est CE champ, et rien d'autre sur l'oracle, que `agent.py`
    transmet à `build_initial_message`."""
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "d.db")
    import json

    pid = ProjectRepo(conn).create(
        name="Portail", connector_type="web", base_url="https://exemple.invalid",
        oracle_type="http", oracle_base_url="https://api.interne.invalid",
        oracle_auth=json.dumps({"type": "bearer", "token": "SECRET-JETON"}),
        oracle_queries=json.dumps([{"name": "tickets_ouverts", "method": "GET", "path": "/t"}]))

    projet = ProjectRepo(conn).get(pid)
    conn.close()

    assert projet["oracle_requetes_disponibles"] == ["tickets_ouverts"]
    dump = json.dumps(projet["oracle_requetes_disponibles"])
    assert "SECRET-JETON" not in dump and "/t" not in dump and "bearer" not in dump
