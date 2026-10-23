"""A107 (porteur, 2026-10-23) — « de la ligne X à la ligne Y » des lignes propres aux cas, choisi au lancement d'une campagne
automatique, comme « Run from row … to row … » du Data Table de QTP/UFT. Par défaut, rien ne change : chaque cas joue toutes
ses lignes (celles proposées par l'IA et validées par une personne).

Ce que ces tests gardent :
1. la plage joue EXACTEMENT les lignes X à Y de chaque cas, dans l'ordre, et rien d'autre ;
2. « la plage doit être exactement celle qui existe » : un cas qui n'a pas la ligne Y fait refuser le lancement (rien n'est
   joué), jamais une plage raccourcie en silence (l'écran annoncerait des lignes jamais jouées) ;
3. un cas sans lignes propres n'est pas concerné ;
4. le dépôt refuse une plage incohérente.
"""

from __future__ import annotations

import json

import pytest

from testpilot.api.services import campaign_service
from testpilot.api.services import donnees_de_test_service as service
from testpilot.store.repositories import CaseDataRepo, CaseRepo, ModuleRepo, RunRepo, VersionRepo
from tests.test_lignes_du_cas import AGE, _execution, _projet, base  # noqa: F401 (fixture)


def _iterations(conn, eid) -> list[str]:
    consignees = json.loads(conn.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0])
    return [i["jeu"] for i in consignees.get("iterations") or [consignees]]


def test_falsifiable_la_plage_joue_exactement_les_lignes_choisies(base):
    pid, cid, vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], plage_des_lignes=(2, 3))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)

    service.preparer_le_script(base, eid, cid, vid, "acces")

    assert _iterations(base, eid) == ["Limite basse", "Majeur"], "les lignes 2 et 3, pas la 1"


def test_sans_plage_rien_ne_change_toutes_les_lignes(base):
    pid, cid, vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    eid = _execution(base, run_id, cid, vid)
    service.preparer_le_script(base, eid, cid, vid, "acces")
    assert _iterations(base, eid) == ["Mineur", "Limite basse", "Majeur"]


def test_falsifiable_une_plage_qu_un_cas_n_a_pas_en_entier_refuse_le_lancement(base):
    pid, cid, _vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], plage_des_lignes=(2, 4))
    with pytest.raises(service.PlageIncomplete, match="Accès"):
        service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    assert not (RunRepo(base).get(run_id)["parametres_figes"] or "").strip(), "rien n'est figé : rien ne sera joué"


def test_au_lancement_la_plage_absente_est_une_erreur_de_campagne_nommee(base, monkeypatch):
    pid, cid, _vid, _ = _projet(base)
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], plage_des_lignes=(1, 3))
    CaseDataRepo(base).remplacer(cid, pid, CaseDataRepo(base).lignes(cid)[:2])   # une ligne retirée depuis la création
    monkeypatch.setattr("testpilot.connectors.runtime_env.verifier_connexion", lambda *_a, **_k: None)
    with pytest.raises(campaign_service.CampaignError) as err:
        campaign_service.start_campaign(base, run_id)
    assert err.value.code == "range_missing" and "Accès" in str(err.value.detail)
    assert RunRepo(base).get(run_id)["status"] == "draft"


def test_un_cas_sans_lignes_propres_n_est_pas_concerne(base):
    pid, cid, _vid, _ = _projet(base)
    autre = CaseRepo(base).create(title="Sans lignes", module_id=ModuleRepo(base).create(project_id=pid, name="N"),
                                  feature_slug="sans")
    v2 = VersionRepo(base).create(test_case_id=autre, spec_content="", spec_hash="", feature_content=AGE, steps_content="")
    base.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (v2, autre))
    base.commit()
    assert service.cas_hors_plage(base, pid, [cid, autre], 3) == []
    assert service.cas_hors_plage(base, pid, [cid, autre], 4) == ["Accès"]


@pytest.mark.parametrize("plage, lignes_des_cas", [((0, 1), "toutes"), ((3, 2), "toutes"), ((1, 2), "premiere"),
                                                   ((True, 2), "toutes")])
def test_le_depot_refuse_une_plage_incoherente(base, plage, lignes_des_cas):
    pid, cid, _vid, _ = _projet(base)
    with pytest.raises(ValueError, match="plage"):
        RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid], plage_des_lignes=plage, lignes_des_cas=lignes_des_cas)
