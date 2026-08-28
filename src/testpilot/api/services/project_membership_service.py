"""Service central des mutations d'accès à un projet.

Les routes historiques et V1 passent ici afin que la protection du dernier Admin, la
compatibilité des deux modèles et l'audit ne puissent pas diverger.
"""

from __future__ import annotations

from testpilot.api import access, erreurs
from testpilot.store.repositories import AccessAuditRepo, ProjectAccessRepo, ProjectMemberRepo


class ProjectMembershipService:
    def __init__(self, conn, actor_user_id: int | None):
        self.conn = conn
        self.actor_user_id = actor_user_id
        self.members = ProjectMemberRepo(conn)
        self.legacy = ProjectAccessRepo(conn)
        self.audit = AccessAuditRepo(conn)

    def _record(self, project_id: int, action: str, target_user_id: int | None,
                result: str, detail: str = "") -> None:
        self.audit.record(
            actor_user_id=self.actor_user_id, project_id=project_id, action=action,
            target_user_id=target_user_id, result=result, detail=detail,
        )

    def _protect_last_admin(self, project_id: int, user_id: int, *, role: str,
                            status: str, action: str) -> None:
        current = self.members.get(project_id, user_id)
        loses_admin = (
            current is not None and current["role"] == access.ROLE_ADMIN
            and current["status"] == "active"
            and (role != access.ROLE_ADMIN or status != "active")
        )
        if loses_admin and self.members.active_admin_count(
                project_id, exclude_user_id=user_id) == 0:
            detail = (
                "impossible : ce membre est le dernier Admin actif du projet — "
                "ajoutez ou promouvez d'abord un autre Admin"
            )
            self._record(project_id, action, user_id, "denied", detail)
            raise erreurs.ErreurMetier("etat_incompatible", detail)

    def set_active_member(self, project_id: int, user_id: int, role: str,
                          *, action: str = "MEMBER_SET") -> None:
        self._protect_last_admin(
            project_id, user_id, role=role, status="active", action=action)
        self.legacy.set_override(project_id, user_id, role)
        self._record(project_id, action, user_id, "allowed", f"role={role};status=active")

    def suspend(self, project_id: int, user_id: int, role: str) -> None:
        action = "MEMBER_SUSPENDED"
        self._protect_last_admin(
            project_id, user_id, role=role, status="suspended", action=action)
        self.legacy.set_override(project_id, user_id, access.ACCES_PROJET_REFUSE)
        self.members.set(project_id, user_id, role, status="suspended")
        self._record(project_id, action, user_id, "allowed", f"role={role}")

    def remove(self, project_id: int, user_id: int) -> None:
        action = "MEMBER_REMOVED"
        current = self.members.get(project_id, user_id)
        role = (current or {}).get("role", access.ROLE_LECTURE_SEULE)
        self._protect_last_admin(
            project_id, user_id, role=role, status="removed", action=action)
        self.legacy.set_override(project_id, user_id, access.ACCES_PROJET_REFUSE)
        self._record(project_id, action, user_id, "allowed", f"previous_role={role}")

    def remove_legacy_override(self, project_id: int, user_id: int) -> None:
        current = self.members.get(project_id, user_id)
        self.legacy.remove_override(project_id, user_id)
        updated = self.members.get(project_id, user_id)
        if (current and current["role"] == access.ROLE_ADMIN and current["status"] == "active"
                and (not updated or updated["role"] != access.ROLE_ADMIN
                     or updated["status"] != "active")
                and self.members.active_admin_count(project_id) == 0):
            # Restaure l'état précédent avant de rendre le refus.
            self.legacy.set_override(project_id, user_id, access.ROLE_ADMIN)
            detail = "impossible : cette modification retirerait le dernier Admin actif du projet"
            self._record(project_id, "LEGACY_OVERRIDE_REMOVED", user_id, "denied", detail)
            raise erreurs.ErreurMetier("etat_incompatible", detail)
        self._record(project_id, "LEGACY_OVERRIDE_REMOVED", user_id, "allowed")

    def set_default_access(self, project_id: int, default_access: str) -> None:
        # Pré-valide le résultat historique pour tous les comptes actifs.
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM user u"
            " LEFT JOIN project_access pa ON pa.project_id=? AND pa.user_id=u.id"
            " WHERE u.is_active=1"
            " AND COALESCE(pa.role, NULLIF(?,''), u.role)='admin'",
            (project_id, default_access),
        ).fetchone()
        if int(row["n"]) == 0:
            detail = "impossible : cet accès par défaut laisserait le projet sans Admin actif"
            self._record(project_id, "DEFAULT_ACCESS_CHANGED", None, "denied", detail)
            raise erreurs.ErreurMetier("etat_incompatible", detail)
        self.legacy.set_default_access(project_id, default_access)
        self._record(project_id, "DEFAULT_ACCESS_CHANGED", None, "allowed",
                     f"default_access={default_access}")
