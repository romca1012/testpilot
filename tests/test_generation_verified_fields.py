"""Parc IT, 2026-09-18 : equipment.order observé par RPC, absent du crawl portail."""
import json
from types import SimpleNamespace

from testpilot.api.services.generation_service import lint_warnings_for_version
from testpilot.generation.react_loop import _apply_effect
from testpilot.generation.smoke_check import check_champs_existants, smoke_check
from testpilot.generation.state import AgentState
from testpilot.generation.tools import ToolContext, ToolOutcome, dispatch
from testpilot.store.db import _migrate_46_verified_fields, get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo


def feature(*names):
    return "\n".join(f'Et je renseigne le champ "{name}" avec "test"' for name in names)


def test_parc_it_equipment_order_product_id_observe_passe_champs_absents_signales(tmp_path):
    connector = SimpleNamespace(get_schema=lambda _: {"product_id": {"type": "many2one"}})
    ctx = ToolContext("parc_it", tmp_path, connector=connector)
    state = AgentState("parc_it")
    outcome = dispatch("inspect_schema", {"model": "equipment.order"}, ctx)
    _apply_effect(state, "inspect_schema", outcome)
    warnings = check_champs_existants(
        feature("product_id", "company_id", "equipment_type_id"),
        {"pages": {"/portail": {"champs": [{"name": "name"}]}}}, state.verified_fields)
    assert [w["step"] for w in warnings] == ["company_id", "equipment_type_id"]
    assert state.verified_fields == {"inspect_schema:equipment.order": ["product_id"]}


def test_inspect_schema_signale_le_step_a_utiliser_pour_un_champ_many2one(tmp_path):
    """Refus SILENCIEUX mesuré en conditions réelles (Sapian, 2026-09-23, cas 127) : un champ
    relationnel Odoo rempli via `fill_field` (« je renseigne … avec la valeur … ») pose la valeur
    dans le DOM sans jamais sélectionner un enregistrement réel — Odoo refuse l'enregistrement
    sans message lisible. `inspect_schema` doit dire, dès l'observation, quel step utiliser."""
    connector = SimpleNamespace(get_schema=lambda _: {
        "partner_id": {"type": "many2one", "required": True},
        "name": {"type": "char", "required": True}})
    ctx = ToolContext("assistance", tmp_path, connector=connector)

    outcome = dispatch("inspect_schema", {"model": "helpdesk.ticket"}, ctx)

    assert "champ RELATIONNEL" in outcome.observation
    assert 'je sélectionne "<valeur>" dans le champ "partner_id"' in outcome.observation
    ligne_name = next(l for l in outcome.observation.splitlines() if l.startswith("- name "))
    assert "RELATIONNEL" not in ligne_name


def test_champ_absent_crawl_et_registre_vide_est_signale():
    assert smoke_check(feature("invented"), verified_fields={})[0]["step"] == "invented"
    assert smoke_check(feature("invented")) == []


def test_inspection_echouee_et_declaration_llm_ne_sont_pas_des_preuves():
    state = AgentState("parc_it")
    outcome = ToolOutcome("product_id existe", ok=False,
                          verified_fields={"inspect_schema:equipment.order": ["product_id"]})
    _apply_effect(state, "inspect_schema", outcome)
    outcome.ok = True
    _apply_effect(state, "write_feature_file", outcome)
    assert state.verified_fields == {}
    assert AgentState("autre").verified_fields == {}


def test_seuls_champs_schema_effectivement_transmis_sont_enregistres(tmp_path):
    schema = {f"field_{i}": {} for i in range(51)}
    ctx = ToolContext("parc_it", tmp_path, connector=SimpleNamespace(get_schema=lambda _: schema))
    outcome = dispatch("inspect_schema", {"model": "equipment.order"}, ctx)
    assert "field_49" in outcome.observation
    assert "field_50" not in outcome.observation
    assert outcome.verified_fields["inspect_schema:equipment.order"] == list(schema)[:50]


def test_inspect_page_form_conserve_aussi_les_champs_optionnels(tmp_path):
    ctx = ToolContext("web", tmp_path, connector=SimpleNamespace(inspect_form=lambda _: {
        "fields": [{"name": "optional", "required": False}, {"name": "required", "required": True}]
    }))
    outcome = dispatch("inspect_page_form", {"page_url": "/form"}, ctx)
    assert "optional" in outcome.observation
    assert outcome.verified_fields == {"inspect_page_form:/form": ["optional", "required"]}


def test_registre_persiste_par_version_et_relecture_sans_crawl(tmp_path, monkeypatch):
    from testpilot.generation import domain_model
    from testpilot.store.repositories import ModuleRepo, ProjectRepo
    monkeypatch.setattr(domain_model, "charger_modele", lambda _: None)
    conn = get_initialized_db(tmp_path / "registry.db")
    try:
        pid = ProjectRepo(conn).create(name="Parc IT")
        mid = ModuleRepo(conn).create(project_id=pid, name="Equipements")
        cid = CaseRepo(conn).create(title="Parc IT", module_id=mid)
        repo = VersionRepo(conn)
        registry = json.dumps({"inspect_schema:equipment.order": ["product_id"]})
        vid = repo.create(test_case_id=cid, spec_content="", spec_hash="", steps_content="",
                          feature_content=feature("product_id", "company_id"), verified_fields=registry)
        _migrate_46_verified_fields(conn)
        assert repo.get(vid)["verified_fields"] == registry
        warnings = lint_warnings_for_version(conn, CaseRepo(conn).get(cid), repo.list_for_case(cid), vid)
        assert [w["step"] for w in warnings] == ["company_id"]
        other = repo.create(test_case_id=cid, spec_content="", spec_hash="", steps_content="",
                            feature_content=feature("product_id"), verified_fields="{}")
        warnings = lint_warnings_for_version(conn, CaseRepo(conn).get(cid), repo.list_for_case(cid), other)
        assert [w["step"] for w in warnings] == ["product_id"]
        assert repo.get(vid)["verified_fields"] == registry
    finally:
        conn.close()


def test_migration_46_base_existante_conserve_versions_et_identifie_legacy(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE test_case_version (id INTEGER PRIMARY KEY, feature_content TEXT)")
        conn.execute("INSERT INTO test_case_version VALUES (7, 'original')")
        _migrate_46_verified_fields(conn)
        _migrate_46_verified_fields(conn)
        row = conn.execute("SELECT * FROM test_case_version").fetchone()
        assert dict(row) == {"id": 7, "feature_content": "original", "verified_fields": ""}
    finally:
        conn.close()


def test_copie_ne_transporte_pas_les_preuves_vers_une_autre_application(tmp_path):
    from testpilot.store.repositories import CaseGroupRepo, ModuleRepo, ProjectRepo
    conn = get_initialized_db(tmp_path / "copy.db")
    try:
        pid = ProjectRepo(conn).create(name="Integration")
        mid = ModuleRepo(conn).create(project_id=pid, name="Parc IT")
        cid = CaseRepo(conn).create(title="Equipement", module_id=mid)
        registry = json.dumps({"inspect_schema:equipment.order": ["product_id"]})
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       steps_content="", feature_content="", verified_fields=registry)
        CaseRepo(conn).set_current_version(cid, vid)
        same = CaseGroupRepo(conn).create(module_id=mid, title="Meme application")
        copy_id = CaseRepo(conn).copier(cid, same)
        assert VersionRepo(conn).latest_for_case(copy_id)["verified_fields"] == registry
        other_pid = ProjectRepo(conn).create(name="Autre application")
        other_mid = ModuleRepo(conn).create(project_id=other_pid, name="Parc IT")
        other = CaseGroupRepo(conn).create(module_id=other_mid, title="Autre application")
        copy_id = CaseRepo(conn).copier(cid, other)
        assert VersionRepo(conn).latest_for_case(copy_id)["verified_fields"] == "{}"
    finally:
        conn.close()
