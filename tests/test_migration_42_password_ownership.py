"""Migration 42 (appropriation des mots de passe + fermeture des projets par défaut).

Ce correctif fait DEUX choses en une seule migration : imposer un changement de mot de passe
et fermer chaque projet en `no_access` par défaut (audit `docs/AUDIT-AVANT-SCALEWAY-2026-09-07.md`,
point 2). La seconde partie, seule, est dangereuse pour une base déjà en service : si la migration
se contentait de fermer les projets sans rien accorder en échange, TOUS les comptes existants qui
ne devaient leur accès qu'au repli historique (rôle global, aucune ligne `project_access`) le
perdraient d'un coup au redémarrage. C'est exactement ce que ce test vérifie : personne ne perd
l'accès qu'il avait, mais plus aucun accès n'est accordé PAR DÉFAUT après coup.
"""

from __future__ import annotations

from testpilot import config
from testpilot.api import access
from testpilot.store import db as db_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectAccessRepo, ProjectRepo, UserRepo


def test_migration_preserve_l_acces_existant_et_ferme_les_projets_futurs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "m42.db")

    # Berceau d'AVANT ce correctif : un compte, un projet ouvert par héritage (aucune ligne
    # `project_access`, `default_access` vide) — le cas normal de toute base déjà en service.
    uid = UserRepo(conn).create(username="Awa", password_hash="x", role=access.ROLE_TESTEUR)
    pid = ProjectRepo(conn).create(name="Ancien projet", base_url="http://x", database="db",
                                   username="qa", password="p")
    conn.execute("DELETE FROM project_access WHERE project_id=?", (pid,))
    conn.execute("UPDATE project SET default_access='' WHERE id=?", (pid,))
    conn.execute("ALTER TABLE user DROP COLUMN must_change_password")
    conn.execute("ALTER TABLE user DROP COLUMN password_expires_at")
    conn.commit()

    db_mod._migrate_42_password_ownership(conn)

    # Le compte existant garde EXACTEMENT l'accès qu'il avait avant la fermeture — aucune
    # régression pour une équipe déjà en place.
    utilisateur = UserRepo(conn).get(uid)
    assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_TESTEUR
    assert ProjectAccessRepo(conn).default_access(pid) == access.ACCES_PROJET_REFUSE

    # Un compte qui arrive APRÈS la migration, lui, ne reçoit plus rien par défaut sur cet ancien
    # projet : c'est la fermeture qu'on voulait, elle ne s'applique qu'à l'avenir.
    nouveau_uid = UserRepo(conn).create(username="Ben", password_hash="x", role=access.ROLE_TESTEUR)
    nouveau = UserRepo(conn).get(nouveau_uid)
    assert access.role_effectif_projet(conn, nouveau, pid) == access.ACCES_PROJET_REFUSE

    # Et un projet créé après la migration reste fermé pour un tiers non explicitement invité —
    # son propriétaire, lui, y a bien accès (admin explicite du projet qu'il vient de créer).
    pid2 = ProjectRepo(conn).create(name="Nouveau projet", base_url="http://x", database="db",
                                    username="qa", password="p", private=True, owner_id=uid)
    assert access.role_effectif_projet(conn, utilisateur, pid2) == access.ROLE_ADMIN
    assert access.role_effectif_projet(conn, nouveau, pid2) == access.ACCES_PROJET_REFUSE

    conn.close()


def test_migration_est_idempotente(tmp_path, monkeypatch):
    """Rejouée deux fois (redémarrage après une migration déjà appliquée), elle ne doit ni
    dupliquer les lignes `project_access` ni planter sur les colonnes déjà présentes."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "m42-bis.db")
    db_mod._migrate_42_password_ownership(conn)  # colonnes déjà là -> no-op, ne doit pas lever
    conn.close()
