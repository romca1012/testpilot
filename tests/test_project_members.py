"""Migration 34 — appartenances projet explicites, sans changement des droits historiques."""

from testpilot.api import access
from testpilot.store.db import _migrate_34_project_members, get_initialized_db
from testpilot.store.repositories import (
    ProjectAccessRepo,
    ProjectMemberRepo,
    ProjectRepo,
    UserRepo,
)


def _user(conn, name: str, role: str, *, active: bool = True) -> int:
    uid = UserRepo(conn).create(username=name, password_hash="hash", role=role)
    if not active:
        UserRepo(conn).set_active(uid, False)
    return uid


def test_backfill_preserve_role_global_defaut_et_exception(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        global_user = _user(conn, "Global", access.ROLE_TESTEUR)
        override_user = _user(conn, "Override", access.ROLE_TESTEUR)
        ProjectAccessRepo(conn).set_override(pid, override_user, access.ROLE_DEV)

        _migrate_34_project_members(conn)

        repo = ProjectMemberRepo(conn)
        assert repo.get(pid, global_user)["role"] == access.ROLE_TESTEUR
        assert repo.get(pid, override_user)["role"] == access.ROLE_DEV
    finally:
        conn.close()


def test_backfill_exclut_no_access_et_suspend_un_compte_inactif(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        hidden = _user(conn, "Hidden", access.ROLE_TESTEUR)
        inactive = _user(conn, "Inactive", access.ROLE_LECTURE_SEULE, active=False)
        ProjectAccessRepo(conn).set_override(pid, hidden, access.ACCES_PROJET_REFUSE)

        _migrate_34_project_members(conn)

        repo = ProjectMemberRepo(conn)
        assert repo.get(pid, hidden)["status"] == "removed"
        assert repo.effective_role(pid, hidden) == access.ACCES_PROJET_REFUSE
        assert repo.get(pid, inactive)["status"] == "suspended"
    finally:
        conn.close()


def test_repo_met_a_jour_et_retire_sans_effacement_physique(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        uid = _user(conn, "Awa", access.ROLE_TESTEUR)
        repo = ProjectMemberRepo(conn)

        repo.set(pid, uid, access.ROLE_DEV)
        assert repo.get(pid, uid)["role"] == access.ROLE_DEV
        repo.remove(pid, uid)
        assert repo.get(pid, uid)["status"] == "removed"
    finally:
        conn.close()


def test_migration_rejouable_sans_dupliquer(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        ProjectRepo(conn).create(name="P")
        _user(conn, "Awa", access.ROLE_TESTEUR)
        _migrate_34_project_members(conn)
        _migrate_34_project_members(conn)
        assert conn.execute("SELECT COUNT(*) FROM project_member").fetchone()[0] == 1
    finally:
        conn.close()


def test_nouveau_projet_synchronise_les_utilisateurs_existants(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        uid = _user(conn, "Awa", access.ROLE_TESTEUR)
        pid = ProjectRepo(conn).create(name="Nouveau")
        assert ProjectMemberRepo(conn).effective_role(pid, uid) == access.ROLE_TESTEUR
    finally:
        conn.close()


def test_nouvel_utilisateur_synchronise_les_projets_existants(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="Existant")
        uid = _user(conn, "Awa", access.ROLE_DEV)
        assert ProjectMemberRepo(conn).effective_role(pid, uid) == access.ROLE_DEV
    finally:
        conn.close()


def test_defaut_exception_et_retrait_restent_synchronises(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        uid = _user(conn, "Awa", access.ROLE_TESTEUR)
        membres = ProjectMemberRepo(conn)
        acces = ProjectAccessRepo(conn)

        acces.set_default_access(pid, access.ROLE_LECTURE_SEULE)
        assert membres.effective_role(pid, uid) == access.ROLE_LECTURE_SEULE

        acces.set_override(pid, uid, access.ROLE_DEV)
        assert membres.effective_role(pid, uid) == access.ROLE_DEV

        acces.remove_override(pid, uid)
        assert membres.effective_role(pid, uid) == access.ROLE_LECTURE_SEULE

        acces.set_default_access(pid, access.ACCES_PROJET_REFUSE)
        assert membres.effective_role(pid, uid) == access.ACCES_PROJET_REFUSE
    finally:
        conn.close()


def test_role_global_et_desactivation_resynchronisent_les_membres(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        uid = _user(conn, "Awa", access.ROLE_TESTEUR)
        users = UserRepo(conn)
        membres = ProjectMemberRepo(conn)

        users.set_role(uid, access.ROLE_DEV)
        assert membres.effective_role(pid, uid) == access.ROLE_DEV

        users.set_active(uid, False)
        assert membres.effective_role(pid, uid) == access.ACCES_PROJET_REFUSE
    finally:
        conn.close()


def test_resolveur_officiel_lit_project_member(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "members.db")
    try:
        pid = ProjectRepo(conn).create(name="P")
        uid = _user(conn, "Awa", access.ROLE_TESTEUR)
        utilisateur = UserRepo(conn).get(uid)

        assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_TESTEUR
        ProjectAccessRepo(conn).set_override(pid, uid, access.ROLE_DEV)
        assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_DEV
    finally:
        conn.close()
