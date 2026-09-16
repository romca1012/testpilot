"""Repositories — accès au référentiel TestPilot.

Chaque classe encapsule une table (ou un agrégat proche). Entrées/sorties = dict
simples pour garder le socle léger et portable vers PostgreSQL. Les valeurs d'enum
font autorité dans ``verdict/status.py`` ; la base les reflète via des CHECK (schema.sql).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import psycopg

from testpilot import config
from testpilot.store import secrets as secrets_mod
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE, MODES_EXECUTION

logger = logging.getLogger(__name__)
INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)


# ── Suppression douce (§7 du brief, 2026-07-24) ───────────────────────────────
# `deleted_at` vide = VIVANT. On n'utilise pas NULL : `deleted_at = ''` s'oublie moins
# facilement dans une condition composee que `IS NULL`, et s'indexe aussi bien.
#
# ⚠️ La visibilite est HIERARCHIQUE : un element n'est visible que si ni lui, ni aucun de ses
# parents n'est a la corbeille. Masquer un module sans masquer ses cas laisserait des cas
# orphelins visibles dans la liste du projet — un etat qui n'existe dans aucun ecran.
_VIVANT = "deleted_at = ''"


class DuplicateName(ValueError):
    """Un nom déjà pris à sa portée d'unicité (projet global, module/projet, cas/module).

    Levée par les repos — donc honorée par l'API *et* la CLI. Les routes la traduisent en
    HTTP 409 ; l'index UNIQUE en base reste le filet de dernier recours.
    """


class VersionConflict(ValueError):
    """Édition concurrente du même cas (audit 2026-09-07, point « plusieurs comptes en même
    temps ») — l'appelant a ouvert le formulaire sur une version qui n'est déjà plus la version
    courante : quelqu'un d'autre a enregistré entre-temps. Sans ce garde-fou, `update_metier`/
    `update_script` fabriquaient quand même une nouvelle version à partir du contenu PÉRIMÉ que
    l'appelant avait sous les yeux — pas une corruption (l'historique garde tout), mais une perte
    silencieuse : le champ que l'autre venait de changer se retrouvait écrasé par une valeur
    obsolète, sans qu'aucune des deux personnes ne le sache. Levée par les repos, traduite en
    HTTP 409 par les routes — jamais un `UPDATE` accepté sur la base d'un état qu'on n'a plus."""


class NotEmpty(ValueError):
    """Un conteneur qu'on refuse de supprimer parce qu'il porte encore des enfants.

    Levée par les repos, traduite en HTTP 409 par les routes. Le refus est DÉLIBÉRÉ et non un
    manque : supprimer une spécification en cascade emporterait des cas qui portent des versions,
    des exécutions et des coûts — c'est-à-dire de l'historique, que le projet ne détruit jamais
    en silence (§2.10 : « on n'efface jamais un run, on annote »). L'utilisateur vide d'abord.
    """


class ProfondeurInvalide(ValueError):
    """Une Sous-section qu'on tente de placer sous une AUTRE sous-section (migration 28).

    Une seule profondeur d'imbrication, comme TestRail par défaut : une Section peut avoir des
    Sous-sections, mais une Sous-section n'en a jamais elle-même. Levée par les repos, traduite
    en HTTP 422 par les routes.
    """


def _key(value: str) -> str:
    """Clé de comparaison des noms : insensible à la casse ET aux accents composés.

    `casefold()` (contrairement à `lower()`) gère l'Unicode — « Café »/« CAFÉ » comparent égal.
    C'est la raison d'être de cette garde applicative : l'index UNIQUE de la base s'appuie sur
    `COLLATE NOCASE`, qui ne replie **que l'ASCII** et laisserait donc passer « CAFÉ » à côté de
    « Café ». Les deux couches sont complémentaires, pas redondantes.
    """
    return " ".join(value.split()).casefold()


def now_iso() -> str:
    """Horodatage ISO-8601 UTC (format TEXT portable)."""
    return datetime.now(timezone.utc).isoformat()


def period_of(ts: str | None = None) -> str:
    """Clé de période mensuelle 'YYYY-MM' pour l'agrégation budgétaire."""
    dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


class ProjectRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_name_free(self, name: str, *, excluding: int | None = None) -> None:
        """Le nom d'un projet est unique GLOBALEMENT. Lève `DuplicateName` sinon.

        `excluding` : l'id à ignorer (renommage — un projet ne rentre pas en conflit avec
        lui-même).
        """
        for row in self.conn.execute(f"SELECT id, name FROM project WHERE {_VIVANT}"):
            if row["id"] != excluding and _key(row["name"]) == _key(name):
                raise DuplicateName(f"un projet nommé « {row['name']} » existe déjà")

    def create(self, *, name: str, description: str = "", connector_type: str = "odoo",
               connector_version: str = "", base_url: str = "", database: str = "",
               username: str = "", password: str = "", private: bool = False,
               owner_id: int | None = None) -> int:
        self.ensure_name_free(name)
        cur = self.conn.execute(
            "INSERT INTO project (name, description, connector_type, connector_version,"
            " base_url, database, username, password, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, description, connector_type, connector_version, base_url, database, username,
             secrets_mod.chiffrer(password), now_iso()))
        self.conn.commit()
        project_id = int(cur.lastrowid)
        if private:
            self.conn.execute("UPDATE project SET default_access='no_access' WHERE id=?", (project_id,))
            if owner_id is not None:
                self.conn.execute("INSERT INTO project_access (project_id,user_id,role) VALUES (?,?,'admin')",
                                  (project_id, owner_id))
            self.conn.commit()
        ProjectMemberRepo(self.conn).sync_project(project_id)
        return project_id

    @staticmethod
    def _en_clair(row) -> dict:
        """Une ligne de projet utilisable par l'appelant : le secret **déchiffré**.

        ⚠️ Le déchiffrement vit ICI, dans le dépôt, et nulle part ailleurs — sinon chaque appelant
        déciderait pour lui-même, et l'un d'eux finirait par lire la colonne brute en croyant
        tenir un mot de passe (il tiendrait un jeton chiffré). L'API, elle, ne renvoie de toute
        façon jamais ce champ (write-only depuis `0005`).
        """
        projet = dict(row)
        if "password" in projet:
            projet["password"] = secrets_mod.dechiffrer(projet["password"])
        return projet

    def get(self, project_id: int) -> dict | None:
        row = self.conn.execute(f"SELECT * FROM project WHERE id=? AND {_VIVANT}",
                                (project_id,)).fetchone()
        return self._en_clair(row) if row else None

    def list_all(self) -> list[dict]:
        """Projets + compteurs de modules et de cas (pour l'accueil / le sélecteur)."""
        return [self._en_clair(r) for r in self.conn.execute(
            "SELECT p.*,"
            " (SELECT COUNT(*) FROM module m WHERE m.project_id=p.id AND m.deleted_at='')"
            "   AS module_count,"
            " (SELECT COUNT(*) FROM test_case tc JOIN module m ON tc.module_id=m.id"
            "  WHERE m.project_id=p.id AND tc.deleted_at='' AND m.deleted_at='')"
            "   AS case_count"
            " FROM project p WHERE p.deleted_at='' ORDER BY p.id")]

    def find_by_name(self, name: str) -> dict | None:
        row = self.conn.execute(f"SELECT * FROM project WHERE name=? AND {_VIVANT}",
                                (name,)).fetchone()
        return self._en_clair(row) if row else None

    def first(self) -> dict | None:
        """Projet par défaut (le plus ancien). Source unique de la règle « projet courant »
        hors interface : rattachement automatique ET connexion du runtime en CLI."""
        row = self.conn.execute(
            f"SELECT * FROM project WHERE {_VIVANT} ORDER BY id LIMIT 1").fetchone()
        return self._en_clair(row) if row else None

    def rename(self, project_id: int, *, name: str, description: str | None = None) -> None:
        self.ensure_name_free(name, excluding=project_id)
        if description is None:
            self.conn.execute("UPDATE project SET name=? WHERE id=?", (name, project_id))
        else:
            self.conn.execute("UPDATE project SET name=?, description=? WHERE id=?",
                              (name, description, project_id))
        self.conn.commit()

    # Champs de connexion éditables. Le `connector_type` en fait partie : changer d'ERP sur un
    # projet existant est rare, mais l'interdire obligerait à recréer le projet — donc à perdre
    # ses modules, ses cas et son historique. On préfère l'autoriser et le tracer.
    # `connector_version` (migration 38) suit la même logique : une application peut monter de
    # version sans changer de projet — l'interdire forcerait, là encore, à tout recréer.
    _CONNEXION = ("connector_type", "connector_version", "base_url", "database", "username")

    def update_connection(self, project_id: int, **champs) -> None:
        """Édite la connexion d'un projet (décision `0005` : elle vit sur le PROJET).

        ⚠️ **Le mot de passe suit une règle à part** : `None` ou absent = « ne touche pas ».
        L'API ne renvoie JAMAIS le mot de passe (write-only), donc un écran d'édition le raffiche
        forcément vide — et renvoyer ce vide effacerait le secret enregistré. Un formulaire ouvert
        puis enregistré sans y toucher casserait toutes les exécutions du projet. Pour vider
        volontairement le mot de passe, il faut donc passer une chaîne vide EXPLICITEMENT ;
        `None` ne le fait jamais.
        """
        sets, params = [], []
        for col in self._CONNEXION:
            if champs.get(col) is not None:
                sets.append(f"{col}=?")
                params.append(champs[col])
        if champs.get("password") is not None:
            sets.append("password=?")
            params.append(secrets_mod.chiffrer(champs["password"]))
        if not sets:
            return
        params.append(project_id)
        self.conn.execute(f"UPDATE project SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()

    def delete(self, project_id: int, par: str = "") -> None:
        """Met le projet A LA CORBEILLE — lui et toute sa descendance disparaissent des ecrans.

        ⚠️ **Ne DÉTRUIT rien** (§7 du brief, 2026-07-24) : la ligne reste, marquee de la date et
        de l'auteur. Elle disparait de toutes les listes et de tous les compteurs, et se restaure.
        La destruction definitive existe — c'est `purger()`, un geste distinct et explicite.

        Les enfants ne sont PAS marques un par un : leur visibilite est hierarchique (un cas dont
        le projet est a la corbeille est invisible). Les marquer aussi rendrait la restauration
        ambigue — il faudrait savoir lesquels etaient deja supprimes AVANT.
        """
        self.conn.execute("UPDATE project SET deleted_at=?, deleted_by=? WHERE id=?",
                          (now_iso(), par, project_id))
        self.conn.commit()

    def restaurer(self, project_id: int) -> None:
        """Sort le projet de la corbeille. Sa descendance redevient visible avec lui."""
        self.conn.execute("UPDATE project SET deleted_at='', deleted_by='' WHERE id=?",
                          (project_id,))
        self.conn.commit()

    def corbeille(self, project_id: int) -> list[dict]:
        """Ce qui a ete supprime DANS ce projet — le projet lui-meme, ses modules, ses
        specifications et ses cas.

        ⚠️ On ne liste que ce qui a ete supprime EXPLICITEMENT. Un cas masque parce que son
        module est a la corbeille n'y figure pas : le montrer laisserait croire qu'on peut le
        restaurer seul, alors qu'il resterait invisible tant que son module l'est.
        """
        requetes = [
            ("projet", "SELECT id, name AS titre, deleted_at, deleted_by FROM project"
                       " WHERE id=? AND deleted_at<>''"),
            ("module", "SELECT id, name AS titre, deleted_at, deleted_by FROM module"
                       " WHERE project_id=? AND deleted_at<>''"),
            # ⚠️ Les ENVELOPPES AUTOMATIQUES sont exclues : ce sont des artefacts techniques
            # que l'utilisateur n'a jamais créés (la génération les fabrique autour d'un cas).
            # Les montrer exposerait un concept interne (§8 du brief) et proposerait de
            # « restaurer » un objet dont la restauration seule n'a aucun sens.
            ("specification", "SELECT g.id, g.title AS titre, g.deleted_at, g.deleted_by"
                              " FROM case_group g JOIN module m ON g.module_id=m.id"
                              " WHERE m.project_id=? AND g.deleted_at<>''"
                              " AND g.auto_enveloppe=0"),
            ("cas", "SELECT tc.id, tc.title AS titre, tc.deleted_at, tc.deleted_by"
                    " FROM test_case tc JOIN module m ON tc.module_id=m.id"
                    " WHERE m.project_id=? AND tc.deleted_at<>''"),
        ]
        out = []
        for type_, sql in requetes:
            for r in self.conn.execute(sql, (project_id,)):
                out.append(dict(r) | {"type": type_})
        return sorted(out, key=lambda e: e["deleted_at"], reverse=True)

    def purger(self, project_id: int) -> None:
        """DETRUIT definitivement un projet et toute sa descendance — dans l'ordre des FK.

        ⚠️ Refuse un projet qui n'est pas DEJA a la corbeille : purger directement contournerait
        la suppression douce et la rendrait decorative. Detruire reste possible ; jamais comme
        effet de bord d'une suppression ordinaire.
        """
        ligne = self.conn.execute("SELECT deleted_at FROM project WHERE id=?",
                                  (project_id,)).fetchone()
        if ligne is None:
            return
        if not ligne["deleted_at"]:
            raise ValueError("ce projet n'est pas a la corbeille : supprimez-le d'abord")
        mod_sub = "SELECT id FROM module WHERE project_id=?"
        case_sub = f"SELECT id FROM test_case WHERE module_id IN ({mod_sub})"
        exec_sub = f"SELECT id FROM execution WHERE test_case_id IN ({case_sub})"
        cur = self.conn
        try:
            cur.execute(f"DELETE FROM scenario_result WHERE execution_id IN ({exec_sub})", (project_id,))
            cur.execute(f"DELETE FROM repair_attempt  WHERE execution_id IN ({exec_sub})", (project_id,))
            # Par test_case_id AUSSI : une ligne de génération n'a pas d'exécution (migration 12).
            # Sans ce OR, la FK cost_ledger→test_case bloque le DELETE du cas. Même correctif
            # que `CaseRepo.delete`, même raison, même preuve (test de cascade projet).
            cur.execute(f"DELETE FROM cost_ledger      WHERE execution_id IN ({exec_sub})"
                        f"    OR test_case_id IN ({case_sub})", (project_id, project_id))
            # ⚠️ Le REGISTRE des résultats (migration 25) — même défaut que celui déjà corrigé sur
            # `CaseRepo.purger` (2026-08-07, `test_delete_case_...`), jamais répercuté ICI : un
            # projet ayant eu ne serait-ce qu'UNE campagne exécutée finalise au moins une ligne
            # `test_result`, qui porte une FK vers `execution` — sans ce nettoyage, le `DELETE
            # FROM execution` juste en dessous échouait en `IntegrityError`, rollback, purge
            # DÉFINITIVE IMPOSSIBLE (audit 2026-08-07, B3). `result_attachment` part d'abord, il
            # référence `test_result`. `run_case_assignment` porte la même FK vers `execution` via
            # `test_case`/`run_id` — même raison, même ordre que `CaseRepo.purger`.
            cur.execute("DELETE FROM result_attachment WHERE result_id IN"
                        f"    (SELECT id FROM test_result WHERE case_id IN ({case_sub}))",
                        (project_id,))
            cur.execute(f"DELETE FROM test_result       WHERE case_id IN ({case_sub})",
                        (project_id,))
            cur.execute(f"DELETE FROM run_case_assignment WHERE case_id IN ({case_sub})",
                        (project_id,))
            cur.execute(f"DELETE FROM execution        WHERE test_case_id IN ({case_sub})", (project_id,))
            # ⚠️ `test_run_case` : la liaison campagne ↔ cas. Sans elle, le `DELETE FROM test_case`
            # échoue sur la clé étrangère et TOUTE la purge est annulée. C'est le MÊME défaut que
            # celui déjà corrigé au niveau du cas en 2026-07 — revenu au niveau du projet, parce
            # que personne ne tenait la liste des conséquences au même endroit.
            cur.execute(f"DELETE FROM test_run_case    WHERE case_id IN ({case_sub})", (project_id,))
            cur.execute("DELETE FROM test_run          WHERE project_id=?", (project_id,))
            cur.execute(f"DELETE FROM review_decision  WHERE test_case_id IN ({case_sub})", (project_id,))
            cur.execute(f"DELETE FROM test_case_version WHERE test_case_id IN ({case_sub})", (project_id,))
            cur.execute(f"DELETE FROM test_case        WHERE module_id IN ({mod_sub})", (project_id,))
            # case_group AVANT module : FK case_group→module sous foreign_keys=ON (migration 13).
            cur.execute(f"DELETE FROM case_group        WHERE module_id IN ({mod_sub})", (project_id,))
            cur.execute("DELETE FROM module  WHERE project_id=?", (project_id,))
            cur.execute("DELETE FROM project WHERE id=?", (project_id,))
            cur.commit()
        except Exception:
            cur.rollback()
            raise


class ModuleRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_name_free(self, project_id: int, name: str, *, excluding: int | None = None) -> None:
        """Le nom d'un module est unique DANS SON PROJET — deux projets peuvent légitimement
        avoir un module « Facturation », ce n'est pas une duplication. Lève `DuplicateName`."""
        for row in self.conn.execute(
                f"SELECT id, name FROM module WHERE project_id=? AND {_VIVANT}", (project_id,)):
            if row["id"] != excluding and _key(row["name"]) == _key(name):
                raise DuplicateName(f"ce projet a déjà un module nommé « {row['name']} »")

    def create(self, *, project_id: int, name: str, description: str = "") -> int:
        self.ensure_name_free(project_id, name)
        cur = self.conn.execute(
            "INSERT INTO module (project_id, name, description, created_at) VALUES (?,?,?,?)",
            (project_id, name, description, now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, module_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT m.*, p.name AS project_name FROM module m JOIN project p ON m.project_id=p.id"
            " AND m.deleted_at='' AND p.deleted_at=''"
            " WHERE m.id=?", (module_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT m.*,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.module_id=m.id AND tc.deleted_at='')"
            "   AS case_count"
            " FROM module m JOIN project p ON m.project_id=p.id"
            " WHERE m.project_id=? AND m.deleted_at='' AND p.deleted_at='' ORDER BY m.id",
        (project_id,)))

    def rename(self, module_id: int, *, name: str, description: str | None = None) -> None:
        """Renomme un module (bouton « Éditer la section »). Nom unique DANS le projet (§2.9)."""
        current = self.get(module_id)
        if current is None:
            raise ValueError(f"module {module_id} introuvable")
        self.ensure_name_free(current["project_id"], name, excluding=module_id)
        if description is None:
            self.conn.execute("UPDATE module SET name=? WHERE id=?", (name, module_id))
        else:
            self.conn.execute("UPDATE module SET name=?, description=? WHERE id=?",
                              (name, description, module_id))
        self.conn.commit()

    def delete(self, module_id: int, par: str = "") -> None:
        """Met le module A LA CORBEILLE : lui, ses specifications et ses cas quittent les ecrans.

        ⚠️ **Ne DÉTRUIT rien** (§7 du brief, 2026-07-24) : la ligne reste, marquee de la date et
        de l'auteur. Elle disparait de toutes les listes et de tous les compteurs, et se restaure.
        La destruction definitive existe — c'est `purger()`, un geste distinct et explicite.
        """
        self.conn.execute("UPDATE module SET deleted_at=?, deleted_by=? WHERE id=?",
                          (now_iso(), par, module_id))
        self.conn.commit()

    def restaurer(self, module_id: int) -> None:
        self.conn.execute("UPDATE module SET deleted_at='', deleted_by='' WHERE id=?", (module_id,))
        self.conn.commit()

    def purger(self, module_id: int) -> None:
        """Supprime un module ET toute sa descendance (spécifications, cas, versions, exécutions,
        résultats, réparations, coûts) — en réutilisant la cascade éprouvée de `CaseRepo.delete`
        cas par cas, puis en retirant les spécifications devenues vides, puis le module.

        Cascade et non refus-si-non-vide (contrairement à la Spécification) : le porteur veut
        pouvoir supprimer un module même peuplé. La perte d'historique reste EXPLICITE — l'écran
        confirme en montrant ce qui partira (même dispositif que la suppression de projet). §2.10
        interdit d'effacer un run *en silence*, pas de l'effacer sur demande claire.
        """
        case_ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM test_case WHERE module_id=?", (module_id,))]
        cases = CaseRepo(self.conn)
        for cid in case_ids:
            # ⚠️ `purger`, pas `delete` : depuis la suppression douce (2026-07-24), `delete` ne
            # fait plus que MASQUER — les lignes resteraient, et la suppression des
            # spécifications puis du module échouerait sur les clés étrangères. Purger appelle
            # purger, à chaque étage.
            cases.purger(cid)
        # Les spécifications du module n'ont plus de cas (on vient de tous les retirer).
        self.conn.execute("DELETE FROM case_group WHERE module_id=?", (module_id,))
        self.conn.execute("DELETE FROM module WHERE id=?", (module_id,))
        self.conn.commit()

    def find_by_name(self, project_id: int, name: str) -> dict | None:
        row = self.conn.execute(
            f"SELECT * FROM module WHERE project_id=? AND name=? AND {_VIVANT}",
            (project_id, name)).fetchone()
        return dict(row) if row else None


def ensure_default_module(conn: sqlite3.Connection, feature_slug: str) -> int:
    """Trouve-ou-crée le module métier par défaut pour un slug technique.

    Rattache au PREMIER projet existant (le connecteur vit sur le projet — décision 0005) ;
    si aucun projet n'existe, en crée un depuis la config (connexion env). Module nommé d'après
    le slug (``demande_materiel`` → ``Demande materiel``). Sert à la génération/CLI sans
    imposer de saisie projet/module. Ne recrée jamais un projet nommé « Odoo » (un connecteur).
    """
    from testpilot import config as _cfg

    modules = ModuleRepo(conn)
    existing = ProjectRepo(conn).first()
    project_id = existing["id"] if existing else ProjectRepo(conn).create(
        name="Portail Sapian", connector_type="odoo", base_url=_cfg.ODOO_URL,
        database=_cfg.ODOO_DB, username=_cfg.ODOO_USER, password=_cfg.ODOO_PASSWORD)
    name = _prettify_slug(feature_slug)
    module = modules.find_by_name(project_id, name)
    return module["id"] if module else modules.create(project_id=project_id, name=name)


def _prettify_slug(slug: str) -> str:
    s = (slug or "").replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:] if s else "Sans module"


class CaseGroupRepo:
    """La SPÉCIFICATION (décision 2026-07-19, rouvre 0006) : un regroupement organisationnel de
    cas testant la même fonctionnalité. Conteneur SIMPLE — ni statut, ni version, ni gate, ni
    coût (tout cela reste sur le cas). Libellé UI : « Spécification »."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def est_residu(self, group_id: int) -> bool:
        """Cette Spécification n'est-elle qu'une **enveloppe technique abandonnée** ?

        Trois conditions, toutes nécessaires : **créée automatiquement**, **aucun cas**, **aucun
        document**. C'est LA règle qui distingue un déchet d'un actif, et elle vit ici, en un seul
        endroit : la suppression d'un cas s'en sert pour ne pas laisser de fantôme, la création
        s'en sert pour ne pas se laisser bloquer par un.

        ⚠️ **« Vide » ne suffit PAS, et c'est le piège dans lequel je suis tombé** (2026-07-22).
        Une Spécification que l'utilisateur vient de créer depuis l'écran est vide elle aussi :
        avec le seul critère du vide, créer un homonyme l'**effaçait en silence** au lieu de
        refuser le doublon. Quatre tests existants l'ont attrapé. C'est la PROVENANCE qui décide —
        d'où `auto_enveloppe` (migration 17).

        ⚠️ **Une Spécification qui porte un document est un ACTIF**, même sans aucun cas : on peut
        vouloir en regénérer. Elle survit à ses cas — c'est voulu, pas un oubli.
        """
        row = self.conn.execute(
            "SELECT g.spec_content, g.auto_enveloppe,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id AND tc.deleted_at='')"
            "   AS n"
            " FROM case_group g WHERE g.id=?", (group_id,)).fetchone()
        return (bool(row) and bool(row["auto_enveloppe"]) and row["n"] == 0
                and not (row["spec_content"] or "").strip())

    def ensure_title_free(self, module_id: int, title: str, *, excluding: int | None = None) -> None:
        """Titre de spécification unique DANS SON MODULE (comme les modules dans leur projet).

        ⚠️ **Un résidu ne bloque pas : il est RÉCUPÉRÉ.** Mesuré le 2026-07-22 — le banc de mesure
        s'est arrêté sur « ce module a déjà une spécification "Création d'une demande de
        remboursement…" » alors que cette Spécification n'avait **ni cas ni document** : une
        enveloppe vide laissée par une suppression antérieure au nettoyage automatique.

        Le nettoyage à la suppression ne fait que **prévenir les nouveaux fantômes** ; il n'efface
        pas ceux d'avant. Récupérer ici rend la correction **rétroactive et auto-guérissante** :
        chaque résidu disparaît le jour où son titre est réclamé, sans migration ni balayage.

        C'est la **troisième fois** que le banc bute sur sa propre non-rejouabilité. Un instrument
        de mesure qu'on ne peut pas relancer ne mesure pas une évolution — il ne dit rien.
        """
        # ⚠️ Seules les spécifications VIVANTES occupent un titre (2026-07-24). Une spécification
        # à la corbeille ne bloque plus rien — et surtout on ne cherche pas à la détruire ici :
        # elle porte encore ses cas (eux aussi à la corbeille), donc la clé étrangère refuserait.
        # C'est exactement ce qui cassait le cycle « créer → supprimer → recréer le même titre ».
        for row in self.conn.execute(
                f"SELECT id, title FROM case_group WHERE module_id=? AND {_VIVANT}", (module_id,)):
            if row["id"] == excluding or _key(row["title"]) != _key(title):
                continue
            if self.est_residu(row["id"]):
                logger.info("[spécification] résidu #%s « %s » récupéré : ni cas ni document",
                            row["id"], row["title"])
                self.delete(row["id"], par="récupération de résidu")
                continue
            raise DuplicateName(f"ce module a déjà une spécification « {row['title']} »")

    def create(self, *, module_id: int, title: str, description: str = "",
               spec_content: str = "", spec_hash: str = "", auto_enveloppe: bool = False,
               parent_group_id: int | None = None) -> int:
        """Crée une spécification. `spec_content` est LE DOCUMENT source (2026-07-19) ; `spec_hash`
        son empreinte, que chaque cas généré référencera. Vides à l'auto-enveloppement d'un cas
        (la spec vit encore sur la version jusqu'à l'étape 3).

        ⚠️ `auto_enveloppe=True` **uniquement** depuis `CaseRepo.create`, qui fabrique un conteneur
        1:1 autour d'un cas qui n'en avait pas. Ce drapeau donne à cette enveloppe le droit d'être
        récupérée quand son cas disparaît. Par défaut **False** : tout ce qui vient de l'écran est
        délibéré, donc protégé — en cas de doute, on protège (migration 17).

        `parent_group_id` (migration 28) : crée une SOUS-section sous une Section existante du
        MÊME module. ⚠️ **Une seule profondeur** — placer une sous-section sous une AUTRE
        sous-section lève `ProfondeurInvalide` (parité TestRail par défaut, pas de niveau 3).
        """
        if parent_group_id is not None:
            parent = self.get(parent_group_id)
            if parent is None:
                raise ValueError(f"section parente {parent_group_id} introuvable")
            if parent["module_id"] != module_id:
                raise ValueError("la section parente n'appartient pas à ce module")
            if parent["parent_group_id"] is not None:
                raise ProfondeurInvalide(
                    "impossible de créer une sous-section sous une sous-section — "
                    "une seule profondeur d'imbrication est autorisée")
        self.ensure_title_free(module_id, title)
        ts = now_iso()
        row = self.conn.execute("SELECT MAX(position) AS m FROM case_group WHERE module_id=?",
                                (module_id,)).fetchone()
        position = 0 if row["m"] is None else int(row["m"]) + 1
        cur = self.conn.execute(
            "INSERT INTO case_group (module_id, title, description, spec_content, spec_hash,"
            " position, auto_enveloppe, parent_group_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (module_id, title, description, spec_content, spec_hash, position,
             int(auto_enveloppe), parent_group_id, ts, ts))
        self.conn.commit()
        return int(cur.lastrowid)

    def deplacer(self, group_id: int, parent_group_id: int | None) -> None:
        """Glisser-déposer d'une Section (étape 2bis, 2026-08-06) — la réattache à un autre
        parent (ou la promeut au premier niveau si `parent_group_id` est `None`), SANS jamais la
        dupliquer : contrairement à un cas, une Section ne se copie pas — copier reviendrait à
        dupliquer en cascade tous les cas qu'elle contient.

        Mêmes règles de profondeur qu'à la création (`create`, une seule profondeur, parité
        TestRail) : la cible doit être une Section de premier niveau du MÊME module, et la
        Section déplacée ne doit porter AUCUNE sous-section (sinon l'imbriquer romprait la
        limite d'une profondeur).
        """
        groupe = self.get(group_id)
        if groupe is None:
            raise ValueError(f"section {group_id} introuvable")
        if parent_group_id == group_id:
            raise ValueError("une section ne peut pas devenir sa propre sous-section")
        if parent_group_id is not None:
            parent = self.get(parent_group_id)
            if parent is None:
                raise ValueError(f"section {parent_group_id} introuvable")
            if parent["module_id"] != groupe["module_id"]:
                raise ValueError("la section cible n'appartient pas au même module")
            if parent["parent_group_id"] is not None:
                raise ProfondeurInvalide(
                    "impossible de déplacer une section sous une sous-section — "
                    "une seule profondeur d'imbrication est autorisée")
            if self.count_children(group_id) > 0:
                raise ProfondeurInvalide(
                    "cette section a elle-même des sous-sections — "
                    "elle ne peut pas devenir une sous-section")
        self.conn.execute(
            "UPDATE case_group SET parent_group_id=?, updated_at=? WHERE id=?",
            (parent_group_id, now_iso(), group_id))
        self.conn.commit()

    def get(self, group_id: int) -> dict | None:
        # Visibilité HIÉRARCHIQUE, comme partout : une spécification dont le module ou le projet
        # est à la corbeille n'existe plus pour l'écran. Sans ces jointures, elle restait
        # accessible par son identifiant — un lien direct rouvrait un document censé avoir disparu.
        row = self.conn.execute(
            "SELECT g.* FROM case_group g"
            " JOIN module m ON g.module_id=m.id"
            " JOIN project p ON m.project_id=p.id"
            " WHERE g.id=? AND g.deleted_at='' AND m.deleted_at='' AND p.deleted_at=''",
            (group_id,)).fetchone()
        return dict(row) if row else None

    def list_for_module(self, module_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT g.*,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id AND tc.deleted_at='')"
            "   AS case_count"
            " FROM case_group g JOIN module m ON g.module_id=m.id"
            " JOIN project p ON m.project_id=p.id"
            " WHERE g.module_id=? AND g.deleted_at='' AND m.deleted_at='' AND p.deleted_at=''"
            " ORDER BY g.position, g.id", (module_id,)))

    def list_for_project(self, project_id: int) -> list[dict]:
        """Toutes les spécifications d'un projet (jointes au module), pour l'arbre latéral.

        `parent_group_id` (migration 28) voyage avec la ligne : c'est ce qui permet à l'écran de
        reconstruire l'arbre Section → Sous-section côté client, sans requête supplémentaire.
        """
        return _rows(self.conn.execute(
            "SELECT g.id, g.module_id, g.title, g.position, g.parent_group_id,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id AND tc.deleted_at='')"
            "   AS case_count"
            " FROM case_group g JOIN module m ON g.module_id=m.id"
            " JOIN project p ON m.project_id=p.id"
            " WHERE m.project_id=? AND g.deleted_at='' AND m.deleted_at='' AND p.deleted_at=''"
            " ORDER BY g.module_id, g.position, g.id", (project_id,)))

    def case_count(self, group_id: int) -> int:
        return int(self.conn.execute(
            f"SELECT COUNT(*) AS n FROM test_case WHERE group_id=? AND {_VIVANT}",
            (group_id,)).fetchone()["n"])

    def count_children(self, group_id: int) -> int:
        """Combien de sous-sections VIVANTES cette Section porte encore (migration 28) — même
        rôle que `case_count` pour les cas : `delete`/`purger` s'en servent pour refuser tant
        qu'il en reste, plutôt que de les emporter en cascade."""
        return int(self.conn.execute(
            "SELECT COUNT(*) AS n FROM case_group WHERE parent_group_id=? AND deleted_at=''",
            (group_id,)).fetchone()["n"])

    def update(self, group_id: int, *, title: str | None = None, description: str | None = None,
               spec_content: str | None = None) -> None:
        """Édition partielle : seul ce qui est fourni change (None = « ne touche pas »).

        ⚠️ `spec_hash` n'est JAMAIS reçu de l'appelant — il est RECALCULÉ ici dès que le document
        change. Laisser passer un couple (contenu, empreinte) fourni de l'extérieur permettrait à
        l'empreinte de mentir sur le document qu'elle référence, et c'est exactement ce que le
        hash sert à détecter (« ce cas est né d'une spec dépassée »). Un champ dont la valeur peut
        contredire la réalité est le `position` décoratif de `0006`, appliqué à la traçabilité.

        La spécification est un conteneur SIMPLE : éditer son document ne crée aucune version et
        ne rebloque aucun gate — le versionnement et le gate vivent sur le CAS (décision `0022`
        n°10). C'est la RÉGÉNÉRATION d'un cas depuis cette spec qui portera la conséquence, via
        l'écart de `spec_hash` (décision `0022` n°6, patron déjà éprouvé).
        """
        current = self.get(group_id)
        if current is None:
            raise ValueError(f"spécification {group_id} introuvable")

        sets, params = [], []
        if title is not None:
            # `excluding=group_id` est le SEUL mécanisme qui autorise une ligne à garder son
            # propre nom (renommage à l'identique, changement de casse). Pas de pré-comparaison
            # `_key` ici : elle ferait le même travail en doublon et rendrait ce garde-ci
            # inatteignable — donc non testé, donc libre de pourrir. Un seul chemin, éprouvé.
            self.ensure_title_free(current["module_id"], title, excluding=group_id)
            sets.append("title=?")
            params.append(title)
        if description is not None:
            sets.append("description=?")
            params.append(description)
        if spec_content is not None:
            from testpilot.analysis.spec_analyzer import spec_hash
            sets.extend(["spec_content=?", "spec_hash=?"])
            params.extend([spec_content, spec_hash(spec_content)])
        if not sets:
            return

        sets.append("updated_at=?")
        params.extend([now_iso(), group_id])
        self.conn.execute(f"UPDATE case_group SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()

    def delete(self, group_id: int, par: str = "") -> None:
        """Met la spécification À LA CORBEILLE — **si elle ne porte plus de cas**.

        ⚠️ **Ne DÉTRUIT rien** (§7 du brief, 2026-07-24) : la ligne reste, marquée de la date et
        de l'auteur. Elle disparaît de toutes les listes et de tous les compteurs, et se restaure.
        La destruction définitive existe — c'est `purger()`, un geste distinct et explicite.

        ⚠️ **Le refus `NotEmpty` est CONSERVÉ**, et ce n'est pas une survivance : une spécification
        qui emporterait ses cas à la corbeille en cascade les rendrait invisibles sans que
        personne l'ait demandé, et la restauration deviendrait ambiguë (lesquels étaient déjà
        supprimés avant ?). L'utilisateur traite ses cas d'abord ; le refus dit combien il en
        reste. *Failli disparaître en réécrivant cette méthode — rattrapé par son test.*

        Même refus pour les SOUS-sections (migration 28) : une Section qui en porte encore ne se
        supprime pas tant qu'elles n'ont pas été traitées, cas par cas, sous-section par
        sous-section — même discipline, jamais de cascade silencieuse.
        """
        n = self.case_count(group_id)
        if n:
            raise NotEmpty(f"cette spécification porte encore {n} cas — supprimez-les d'abord")
        n_enfants = self.count_children(group_id)
        if n_enfants:
            raise NotEmpty(
                f"cette section porte encore {n_enfants} sous-section(s) — supprimez-les d'abord")
        self.conn.execute("UPDATE case_group SET deleted_at=?, deleted_by=? WHERE id=?",
                          (now_iso(), par, group_id))
        self.conn.commit()

    def restaurer(self, group_id: int) -> None:
        self.conn.execute("UPDATE case_group SET deleted_at='', deleted_by='' WHERE id=?",
                          (group_id,))
        self.conn.commit()

    def purger(self, group_id: int) -> None:
        """Supprime une spécification VIDE. Refuse (NotEmpty) tant qu'elle porte des cas ou des
        sous-sections (migration 28).

        Pas de cascade : un cas porte des versions, des exécutions, des résultats et des lignes de
        coût. Les emporter sur la suppression de leur conteneur détruirait de l'historique sans
        que personne l'ait demandé — le contraire de la ligne du projet (§2.10). L'utilisateur
        supprime (ou déplace) ses cas d'abord ; le refus dit combien il en reste.
        """
        n = self.case_count(group_id)
        if n:
            raise NotEmpty(f"cette spécification porte encore {n} cas — supprimez-les d'abord")
        n_enfants = self.count_children(group_id)
        if n_enfants:
            raise NotEmpty(
                f"cette section porte encore {n_enfants} sous-section(s) — supprimez-les d'abord")
        self.conn.execute("DELETE FROM case_group WHERE id=?", (group_id,))
        self.conn.commit()


# Colonnes cas + jointure métier (module/projet) réutilisées par get/list.
# `last_verdict_version_id` : la version qui a RÉELLEMENT produit `last_execution_status`
# (décision 0016, option (iii)). Les `last_*` du cas sont écrits à CHAQUE run — y compris une
# tentative de réparation qui ne sera pas adoptée. Le statut peut donc décrire une version qui
# n'est plus la référence : on l'affiche au lieu de le corriger en silence, conformément à la
# ligne du projet (0007 B+, 0008 lint, 0013). On ne recalcule PAS le statut depuis la version
# courante : ce serait masquer un run réel.
_CASE_SELECT = (
    "SELECT tc.*, m.name AS module_name, m.project_id AS project_id, p.name AS project_name,"
    " g.title AS group_title,"
    " (SELECT e.version_id FROM execution e WHERE e.test_case_id = tc.id"
    "  ORDER BY e.id DESC LIMIT 1) AS last_verdict_version_id"
    " FROM test_case tc"
    " LEFT JOIN module m ON tc.module_id = m.id"
    " LEFT JOIN project p ON m.project_id = p.id"
    " LEFT JOIN case_group g ON tc.group_id = g.id"
)

# La visibilite d'un cas est HIERARCHIQUE : lui-meme vivant, ET son module, ET son projet.
# Les `IS NULL` couvrent le cas sans module (cree par la CLI) : il n'a pas de parent a
# consulter, et l'exclure le rendrait invisible pour de mauvaises raisons.
_CASE_VIVANT = ("tc.deleted_at = ''"
                " AND (m.id IS NULL OR m.deleted_at = '')"
                " AND (p.id IS NULL OR p.deleted_at = '')")


class CaseRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_title_free(self, group_id: int | None, title: str,
                          *, excluding: int | None = None) -> None:
        """Le titre d'un cas est unique DANS SA SPÉCIFICATION (plus par module, décision 2026-07-19).
        Deux spécifications peuvent chacune avoir un « Nominal ». Lève `DuplicateName`.

        `group_id=None` : aucune portée d'unicité à faire respecter (rien à quoi comparer).
        """
        if group_id is None:
            return
        rows = self.conn.execute(
            f"SELECT id, title FROM test_case WHERE group_id=? AND {_VIVANT}", (group_id,))
        for row in rows:
            if row["id"] != excluding and _key(row["title"]) == _key(title):
                raise DuplicateName(f"cette spécification a déjà un cas intitulé « {row['title']} »")

    def ensure_slug_free(self, feature_slug: str, *, excluding: int | None = None) -> None:
        """Le `feature_slug` est unique GLOBALEMENT : il nomme le fichier `{slug}.feature` dans
        un répertoire commun. Deux cas au même slug écriraient dans le MÊME fichier — l'un
        écraserait silencieusement les tests de l'autre. Lève `DuplicateName`.

        Slug vide = pas de fichier, donc pas de collision possible : rien à faire respecter.
        """
        if not feature_slug:
            return
        rows = self.conn.execute(
            f"SELECT id, title FROM test_case WHERE feature_slug=? AND {_VIVANT}",
                                 (feature_slug,))
        for row in rows:
            if row["id"] != excluding:
                raise DuplicateName(
                    f"le fichier de test « {feature_slug}.feature » est déjà utilisé par le cas "
                    f"« {row['title']} »")

    def create(self, *, title: str, module_id: int | None = None, group_id: int | None = None,
               feature_slug: str = "", author: str = "", description: str = "",
               origin: str = "ia_generated", priority: str = "medium", refs: str = "") -> int:
        """Crée un cas. `group_id` OBLIGATOIRE pour tout cas RANGÉ dans un module : s'il n'est pas
        fourni mais qu'un module l'est, on AUTO-ENVELOPPE le cas dans sa propre spécification 1:1
        (même geste que la migration legacy). L'appelant historique (la génération) continue donc
        de marcher sans changement — l'étape 3 lui fera passer un `group_id` explicite.

        Un cas SANS module (module_id=None) reste sans groupe : il n'a pas de place dans la
        hiérarchie Module→Spécification→Cas, donc aucune spécification à lui donner. C'est un cas
        de bord (hors arbre), pas le chemin de production — qui passe toujours par un module.

        `refs` — texte libre comme TestRail (§9, 2026-08-05) : la génération multi-cas l'auto-remplit
        avec le nom de la user story dont ce cas est issu. Vide par défaut, comme avant.
        """
        if group_id is None and module_id is not None:
            group_id = CaseGroupRepo(self.conn).create(module_id=module_id, title=title,
                                                       auto_enveloppe=True)
        self.ensure_title_free(group_id, title)
        self.ensure_slug_free(feature_slug)
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_case (title, module_id, group_id, feature_slug, description,"
            " origin, priority, refs, position, author, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, module_id, group_id, feature_slug, description, origin, priority, refs,
             self._next_position(module_id), author, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def create_manual(self, *, module_id: int, title: str, preconditions: str = "",
                      test_steps: str = "", expected_result: str = "",
                      author: str = "ui", group_id: int | None = None) -> int:
        """Crée un cas À LA MAIN — le bouton « Ajouter un cas de test », SANS IA (décision `0022`).

        Le cas naît avec son **document métier** (titre, préconditions, étapes, résultat attendu)
        mais **sans Gherkin** : il n'est donc pas exécutable tant qu'un test technique n'a pas été
        généré (décision `0022` n°6, bouton « Régénérer le test technique » à venir). Ce n'est PAS
        le « cas fantôme » que `0006` refusait — un cas fantôme ne testait rien *et* ne décrivait
        rien ; celui-ci porte une intention métier lisible, assumée par un humain (décision n°7).

        `origin='manual_converted'` : marque un cas d'origine humaine (par opposition à
        `ia_generated`), la seule valeur non-IA que le schéma autorise. Une version est créée
        d'emblée : c'est elle qui porte le métier (le métier vit sur la version, décision n°10).

        `group_id` (2026-09-11) : quand l'appelant l'a choisi (venu d'une Section précise, jamais
        du bouton générique), le cas y atterrit DIRECTEMENT — `CaseRepo.create` ne l'auto-enveloppe
        alors plus dans une Section neuve rien que pour lui. Parité TestRail : plusieurs cas créés
        depuis la MÊME Section se retrouvent ensemble, sans glisser-déposer après coup.
        """
        cid = self.create(title=title, module_id=module_id, group_id=group_id, author=author,
                          origin="manual_converted", feature_slug="")
        VersionRepo(self.conn).create(
            test_case_id=cid, spec_content="", spec_hash="",
            feature_content="", steps_content="",   # pas de Gherkin : cas non exécutable en l'état
            change_summary="Création manuelle", created_by=author,
            title=title, preconditions=preconditions, test_steps=test_steps,
            expected_result=expected_result)
        # `set_current_version` pointe le cas sur la version qu'on vient d'écrire.
        vid = self.conn.execute("SELECT id FROM test_case_version WHERE test_case_id=?"
                                " ORDER BY id DESC LIMIT 1", (cid,)).fetchone()["id"]
        self.set_current_version(cid, vid)
        return cid

    def _next_position(self, module_id: int | None) -> int:
        """Place un nouveau cas EN FIN de son module (décision 0009).

        Sans ça, tout nouveau cas naîtrait à 0 et s'empilerait en tête de liste — un ordre que
        personne n'a choisi, qui plus est instable entre deux créations.
        """
        if module_id is None:
            return 0
        row = self.conn.execute("SELECT MAX(position) AS m FROM test_case WHERE module_id=?",
                                (module_id,)).fetchone()
        return 0 if row["m"] is None else int(row["m"]) + 1

    def rename(self, case_id: int, title: str) -> None:
        case = self.get(case_id)
        group_id = case["group_id"] if case else None
        self.ensure_title_free(group_id, title, excluding=case_id)
        self.conn.execute("UPDATE test_case SET title=?, updated_at=? WHERE id=?",
                          (title, now_iso(), case_id))
        self.conn.commit()

    def deplacer(self, case_id: int, group_id: int) -> None:
        """Déplace un cas vers une autre Section (migration 28, étape 2) — réattribution PURE,
        jamais une copie.

        ⚠️ **Même `id`, aucun historique touché.** `test_result.case_id`/`execution.test_case_id`
        ne bougent jamais : tous les résultats et exécutions passés du cas restent exactement les
        siens après le déplacement — comportement mesuré de TestRail (déplacer un cas dans une
        même suite ne supprime jamais son historique ; seul un déplacement entre SUITES le
        ferait, une notion que TestPilot n'a pas). Le module suit la Section cible : un cas ne
        peut pas appartenir à un module différent de celui de sa propre Section.
        """
        case = self.get(case_id)
        if case is None:
            raise ValueError(f"cas {case_id} introuvable")
        groupe = CaseGroupRepo(self.conn).get(group_id)
        if groupe is None:
            raise ValueError(f"section {group_id} introuvable")
        self.ensure_title_free(group_id, case["title"], excluding=case_id)
        self.conn.execute(
            "UPDATE test_case SET group_id=?, module_id=?, updated_at=? WHERE id=?",
            (group_id, groupe["module_id"], now_iso(), case_id))
        self.conn.commit()
        # L'ancienne Section a pu devenir une enveloppe vide : même nettoyage qu'à la suppression
        # (`_nettoyer_specification_orpheline` ne touche qu'un résidu technique, jamais un actif).
        self._nettoyer_specification_orpheline(case["group_id"])

    def copier(self, case_id: int, group_id: int, *, author: str = "") -> int:
        """Copie un cas dans une autre Section (migration 28, étape 2) — un cas RÉELLEMENT NEUF
        (nouvel `id`, nouveau `feature_slug`), SANS le moindre historique partagé : aucune
        exécution, aucun résultat — il démarre « Untested ». Rend l'`id` du nouveau cas.

        ⚠️ Comportement mesuré de TestRail : copier duplique le CONTENU (document métier + script
        Gherkin), jamais les résultats — c'est `deplacer` qui préserve l'historique, jamais
        `copier`. Confondre les deux fragmenterait la traçabilité (un même historique éclaté
        entre deux cas qui prétendent chacun en être l'origine).
        """
        source = self.get(case_id)
        if source is None:
            raise ValueError(f"cas {case_id} introuvable")
        groupe = CaseGroupRepo(self.conn).get(group_id)
        if groupe is None:
            raise ValueError(f"section {group_id} introuvable")

        titre = source["title"]
        try:
            self.ensure_title_free(group_id, titre)
        except DuplicateName:
            # Collision dans la Section cible (rare, mais réelle si on copie vers une Section qui
            # a déjà un cas du même nom) : un suffixe, pas un refus — l'intention était de copier.
            titre = f"{titre} (copie)"
            self.ensure_title_free(group_id, titre)

        version = (VersionRepo(self.conn).get(source["current_version_id"])
                   if source.get("current_version_id") else None)

        # Un `feature_slug` neuf UNIQUEMENT si la version courante porte un script réel : un cas
        # sans Gherkin (saisie manuelle non encore automatisée) reste sans slug, comme à sa
        # création — `ensure_slug_free`/`unique_feature_slug` n'ont rien à garantir pour lui.
        slug = ""
        if version and (version.get("feature_content") or "").strip():
            from testpilot.api.services.generation_service import slugify, unique_feature_slug
            slug = unique_feature_slug(self.conn, slugify(titre))

        new_id = self.create(
            title=titre, module_id=groupe["module_id"], group_id=group_id,
            feature_slug=slug, author=author, description=source.get("description") or "",
            origin=source.get("origin") or "ia_generated",
            priority=source.get("priority") or "medium", refs=source.get("refs") or "")

        if version:
            vid = VersionRepo(self.conn).create(
                test_case_id=new_id, spec_content=version.get("spec_content") or "",
                spec_hash=version.get("spec_hash") or "",
                feature_content=version.get("feature_content") or "",
                steps_content=version.get("steps_content") or "",
                change_summary=f"Copié depuis le cas #{case_id}", created_by=author,
                title=version.get("title") or titre,
                preconditions=version.get("preconditions") or "",
                test_steps=version.get("test_steps") or "",
                expected_result=version.get("expected_result") or "")
            self.set_current_version(new_id, vid)

            # ⚠️ Le RUNNER lit le script SUR DISQUE (`config.GENERATED_DIR/{slug}.feature`),
            # jamais depuis la base — sans cette recopie, le cas copié serait « exécutable » en
            # apparence (une version avec du Gherkin) mais échouerait au premier run, fichier
            # introuvable. Même chemin que `write_feature_file`/`write_steps_file` (génération).
            if slug and (version.get("feature_content") or "").strip():
                config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
                (config.GENERATED_DIR / f"{slug}.feature").write_text(
                    version["feature_content"], encoding="utf-8")
                (config.GENERATED_DIR / f"{slug}_steps.py").write_text(
                    version.get("steps_content") or "", encoding="utf-8")

        return new_id

    def delete(self, case_id: int, par: str = "") -> None:
        """Met le cas A LA CORBEILLE — avec ses versions, ses executions et ses couts, qui le
        suivent puisqu'ils n'existent que par lui.

        ⚠️ **Ne DÉTRUIT rien** (§7 du brief, 2026-07-24) : la ligne reste, marquee de la date et
        de l'auteur. Elle disparait de toutes les listes et de tous les compteurs, et se restaure.
        La destruction definitive existe — c'est `purger()`, un geste distinct et explicite.
        """
        ligne = self.conn.execute("SELECT group_id FROM test_case WHERE id=?",
                                  (case_id,)).fetchone()
        self.conn.execute("UPDATE test_case SET deleted_at=?, deleted_by=? WHERE id=?",
                          (now_iso(), par, case_id))
        self.conn.commit()
        # ⚠️ L'enveloppe AUTO-créée par la génération suit son cas — comportement d'origine, qu'il
        # aurait été facile de perdre en remplaçant la suppression : une spécification résiduelle
        # bloque la regénération d'un cas du même titre (défaut des migrations 17/18).
        self._nettoyer_specification_orpheline(ligne["group_id"] if ligne else None, par)

    def restaurer(self, case_id: int) -> None:
        """Sort le cas de la corbeille.

        ⚠️ Ne ressuscite PAS un module ou un projet supprime : restaurer un enfant ne doit pas
        faire reapparaitre un parent que personne n'a demande. Le cas reste alors invisible — et
        c'est la verite, pas un defaut.
        """
        self.conn.execute("UPDATE test_case SET deleted_at='', deleted_by='' WHERE id=?",
                          (case_id,))
        self.conn.commit()

    def purger(self, case_id: int) -> None:
        """Supprime un cas ET sa descendance (versions, relectures, exécutions, résultats,
        réparations, coûts) — dans l'ordre des FK, en une transaction.

        Même patron que `ProjectRepo.delete` : le schéma ne déclare aucun `ON DELETE CASCADE`,
        la cascade est donc explicite ici. `current_version_id` n'a volontairement pas de FK
        dure (cycle cas↔version), il n'impose donc pas d'ordre.

        ⚠️ **Le coût se supprime par `test_case_id`, PAS par `execution_id`** — corrigé le
        2026-07-17. La migration 12 a fait de `test_case_id` le lien de référence du ledger,
        précisément parce qu'une **génération n'a pas d'exécution** (elle la précède). Cette
        cascade, écrite avant, ne nettoyait que par `execution_id` : la ligne de coût de
        génération d'un cas créé par l'écran ne matchait aucun `execution_id`. Comme la colonne
        porte une FK vers `test_case` (migration 12) sous `PRAGMA foreign_keys = ON`, le `DELETE
        FROM test_case` final **échouait en `IntegrityError`** — le cas devenait insupprimable.
        Prouvé par `test_delete_case_emporte_le_cout_de_generation_sans_execution` (rouge sur
        l'ancienne cascade).
        """
        cur = self.conn
        # Retenu AVANT la suppression : après, le cas n'existe plus pour dire à quelle
        # spécification il appartenait.
        row = cur.execute("SELECT group_id FROM test_case WHERE id=?", (case_id,)).fetchone()
        group_id = row["group_id"] if row else None
        exec_sub = "SELECT id FROM execution WHERE test_case_id=?"
        try:
            cur.execute(f"DELETE FROM scenario_result WHERE execution_id IN ({exec_sub})", (case_id,))
            cur.execute(f"DELETE FROM repair_attempt  WHERE execution_id IN ({exec_sub})", (case_id,))
            cur.execute(f"DELETE FROM cost_ledger      WHERE execution_id IN ({exec_sub})"
                        "    OR test_case_id = ?", (case_id, case_id))
            # ⚠️ Le REGISTRE des résultats (migration 25, 2026-08-06) — oublié à sa création,
            # trouvé le 2026-08-07 sur une VRAIE purge (« FOREIGN KEY constraint failed » à la
            # suppression finale de `test_case`, exactement le même défaut déjà payé deux fois
            # pour `cost_ledger` et `test_run_case`, voir la note plus bas). `test_result` porte
            # une FK vers `execution` : il DOIT partir AVANT elle, pas après — sinon la ligne de
            # registre pointerait sur une exécution déjà détruite. Ses pièces jointes
            # (`result_attachment`) partent d'abord, elles référencent `test_result`.
            cur.execute("DELETE FROM result_attachment WHERE result_id IN"
                        " (SELECT id FROM test_result WHERE case_id=?)", (case_id,))
            cur.execute("DELETE FROM test_result       WHERE case_id=?", (case_id,))
            cur.execute("DELETE FROM run_case_assignment WHERE case_id=?", (case_id,))
            cur.execute("DELETE FROM execution         WHERE test_case_id=?", (case_id,))
            # ⚠️ L'appartenance à une CAMPAGNE doit partir aussi (migration 15). Oubliée à
            # l'ajout de `test_run_case`, elle rendait tout cas inclus dans un run
            # **INSUPPRIMABLE** (`FOREIGN KEY constraint failed`) — exactement le défaut décrit
            # plus haut pour `cost_ledger`, rejoué un mois plus tard. Trouvé par le banc de
            # mesure, qui supprime ses artefacts : une suite verte ne l'avait pas vu.
            # Supprimer un cas le RETIRE des campagnes ; le run survit avec ses autres cas.
            cur.execute("DELETE FROM test_run_case     WHERE case_id=?", (case_id,))
            cur.execute("DELETE FROM review_decision   WHERE test_case_id=?", (case_id,))
            cur.execute("DELETE FROM test_case_version WHERE test_case_id=?", (case_id,))
            cur.execute("DELETE FROM test_case         WHERE id=?", (case_id,))
            self._nettoyer_specification_orpheline(group_id)
            cur.commit()
        except Exception:
            cur.rollback()
            raise

    def _nettoyer_specification_orpheline(self, group_id: int | None, par: str = "") -> None:
        """Supprime la Spécification devenue VIDE **si elle n'était qu'une enveloppe automatique**.

        ⚠️ **Le défaut que ça corrige** (mesuré le 2026-07-21) : `create()` auto-enveloppe un cas
        sans `group_id` dans sa propre Spécification 1:1. `delete()` retirait le cas mais **pas
        cette enveloppe** — d'où des Spécifications fantômes à 0 cas (8 constatées dans la vraie
        base), visibles dans l'arbre latéral, et qui **bloquaient toute regénération du même
        titre** (unicité par module, §2.9). Le banc de mesure est tombé dessus deux fois.

        ⚠️ **Règle prudente** : on ne supprime QUE si la spécification ne porte **aucun document**
        (`spec_content` vide). Une Spécification rédigée par un humain est un actif : elle doit
        survivre à ses cas — on peut vouloir en regénérer depuis elle. C'est ce qui distingue
        « résidu technique » et « conteneur voulu ».

        La règle elle-même vit dans `CaseGroupRepo.est_residu` — un seul endroit, parce que la
        création s'en sert aussi (`ensure_title_free` récupère un résidu au lieu de refuser le
        titre). Deux copies de cette règle divergeraient, et l'écart serait invisible : l'une
        laisserait un fantôme que l'autre refuserait d'effacer.
        """
        if group_id is None:
            return
        if CaseGroupRepo(self.conn).est_residu(group_id):
            # Douce comme tout le reste depuis le 2026-07-24 : une enveloppe résiduelle est un
            # détail technique, mais la détruire resterait une destruction — et le §7 n'en fait
            # pas d'exception pour les détails.
            CaseGroupRepo(self.conn).delete(group_id, par=par)

    def update_metier(self, case_id: int, *, title: str | None = None,
                      preconditions: str | None = None, test_steps: str | None = None,
                      expected_result: str | None = None,
                      refs: str | None = None, estimate: str | None = None,
                      editor: str = "ui", expected_version_id: int | None = None) -> int | None:
        """Édite le contenu métier d'un cas → **crée une NOUVELLE version** (décision `0022` n°10).

        ⚠️ **Jamais un `UPDATE` en place sur la version courante.** Une version est un état figé :
        l'écraser détruirait l'historique que l'onglet Historique doit pouvoir differ, et
        modifierait sous ses pieds un contenu que le gate a peut-être déjà approuvé.

        Le contenu TECHNIQUE (Gherkin + steps) est **recopié tel quel** : éditer le métier ne
        régénère rien (décision `0022` n°6 — on signale la divergence, l'humain régénère quand il
        veut). Conséquence voulue : la nouvelle version n'étant pas approuvée, **le gate bloque
        l'exécution** jusqu'à relecture — automatiquement, sans règle supplémentaire.

        `refs`/`estimate` sont des métadonnées : elles vivent sur le CAS et ne créent pas de
        version (elles ne changent pas ce que le test vérifie).

        `expected_version_id` (audit 2026-09-07, point « plusieurs comptes en simultané ») : la
        version que l'appelant avait sous les yeux en ouvrant le formulaire. Fournie, et
        différente de la version courante RÉELLE du cas → `VersionConflict` : quelqu'un d'autre a
        déjà enregistré une édition depuis. `None` (appelant qui n'envoie rien, ex. anciens
        clients/scripts) désactive le contrôle — comportement d'avant, inchangé.

        Rend l'id de la nouvelle version, ou `None` si aucun champ versionné n'a changé.
        """
        case = self.get(case_id)
        if case is None:
            return None
        if expected_version_id is not None and case.get("current_version_id") != expected_version_id:
            raise VersionConflict(
                f"le cas {case_id} a été modifié par quelqu'un d'autre entre-temps")
        versions = VersionRepo(self.conn)
        current = versions.get(case.get("current_version_id")) if case.get("current_version_id") else None

        # Métadonnées : simple mise à jour sur le cas, sans version.
        meta = {k: v for k, v in (("refs", refs), ("estimate", estimate)) if v is not None}
        if meta:
            sets = ", ".join(f"{k}=?" for k in meta)
            self.conn.execute(f"UPDATE test_case SET {sets}, updated_at=? WHERE id=?",
                              (*meta.values(), now_iso(), case_id))
            self.conn.commit()

        # Contenu versionné : valeur fournie, sinon celle de la version courante (repli sur le
        # cas pour le titre, car les versions d'avant la migration 14 n'en portaient pas).
        def pick(new, key, fallback):
            if new is not None:
                return new
            return (current or {}).get(key) or fallback

        new_title = pick(title, "title", case.get("title", ""))
        new_pre = pick(preconditions, "preconditions", "")
        new_steps = pick(test_steps, "test_steps", "")
        new_expected = pick(expected_result, "expected_result", "")

        inchange = (current is not None
                    and new_title == (current.get("title") or case.get("title", ""))
                    and new_pre == (current.get("preconditions") or "")
                    and new_steps == (current.get("test_steps") or "")
                    and new_expected == (current.get("expected_result") or ""))
        if inchange:
            return None   # rien de versionné n'a bougé : pas de version fantôme

        if title is not None and title != case.get("title"):
            self.ensure_title_free(case.get("group_id"), title, excluding=case_id)

        version_id = versions.create(
            test_case_id=case_id,
            spec_content=(current or {}).get("spec_content", ""),
            spec_hash=(current or {}).get("spec_hash", ""),
            feature_content=(current or {}).get("feature_content", ""),
            steps_content=(current or {}).get("steps_content", ""),
            change_summary="Édition manuelle du contenu métier",
            created_by=editor,
            title=new_title, preconditions=new_pre, test_steps=new_steps,
            expected_result=new_expected,
        )
        # Le CAS porte une COPIE courante du titre pour les listes et les filtres.
        # La VERSION fait foi — même règle que le raccourci de résultat.
        self.conn.execute(
            "UPDATE test_case SET title=?, current_version_id=?, updated_at=? WHERE id=?",
            (new_title, version_id, now_iso(), case_id))
        self.conn.commit()
        return version_id

    def update_script(self, case_id: int, *, feature_content: str, steps_content: str,
                      editor: str = "ui", expected_version_id: int | None = None) -> int | None:
        """Édite directement le SCRIPT généré (Gherkin + Python) → **nouvelle version** (rôle
        Dev, 2026-08-07) — le MIROIR de `update_metier` : ici c'est le contenu MÉTIER qui est
        recopié tel quel, le contenu TECHNIQUE qui change.

        ⚠️ **Contrairement à `update_metier`, la nouvelle version n'est PAS auto-approuvée** —
        une main humaine sur un script généré, sans dry-run pour la valider, est un geste plus
        risqué qu'éditer le texte métier : le gate bloque donc l'exécution jusqu'à relecture,
        automatiquement, sans règle supplémentaire à écrire.

        `expected_version_id` : même garde-fou anti-édition-concurrente que `update_metier`
        (voir sa docstring) — lève `VersionConflict` si fourni et périmé.

        Rend `None` si rien n'a changé (pas de version fantôme) — sinon l'id de la NOUVELLE
        version.
        """
        case = self.get(case_id)
        if case is None:
            return None
        if expected_version_id is not None and case.get("current_version_id") != expected_version_id:
            raise VersionConflict(
                f"le cas {case_id} a été modifié par quelqu'un d'autre entre-temps")
        versions = VersionRepo(self.conn)
        current = (versions.get(case["current_version_id"])
                  if case.get("current_version_id") else None)
        if (current is not None
                and feature_content == (current.get("feature_content") or "")
                and steps_content == (current.get("steps_content") or "")):
            return None

        version_id = versions.create(
            test_case_id=case_id,
            spec_content=(current or {}).get("spec_content", ""),
            spec_hash=(current or {}).get("spec_hash", ""),
            feature_content=feature_content, steps_content=steps_content,
            change_summary="Édition manuelle du script", created_by=editor,
            title=(current or {}).get("title") or case.get("title", ""),
            preconditions=(current or {}).get("preconditions", ""),
            test_steps=(current or {}).get("test_steps", ""),
            expected_result=(current or {}).get("expected_result", ""))
        self.set_current_version(case_id, version_id)

        # ⚠️ Le RUNNER lit le script SUR DISQUE (`config.GENERATED_DIR/{slug}.feature`), jamais
        # depuis la base (même raison que `CaseRepo.copier`) — sans cette recopie, l'édition
        # semblerait prise en compte à l'écran mais le prochain run rejouerait l'ANCIEN script.
        slug = case.get("feature_slug")
        if slug:
            config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            (config.GENERATED_DIR / f"{slug}.feature").write_text(feature_content, encoding="utf-8")
            (config.GENERATED_DIR / f"{slug}_steps.py").write_text(steps_content, encoding="utf-8")
        return version_id

    # Les métadonnées de LECTURE d'un cas : elles ne changent pas ce que le test VÉRIFIE, donc
    # elles ne sont pas versionnées (même famille que `refs`/`estimate`, décision 0022 n°3b).
    CHAMPS_DE_LECTURE = ("priority", "type", "etat")

    def set_metadonnees(self, case_id: int, **champs) -> None:
        """Écrit une ou plusieurs métadonnées de lecture (`priority`, `type`, `etat`).

        Une seule méthode plutôt qu'un `set_x` par champ : les trois ont exactement la même
        mécanique (écrire, horodater), et la liste s'allongera — l'administrateur pourra ajouter
        des valeurs, et le produit d'autres colonnes du même genre.

        ⚠️ **Les VALEURS ne sont pas validées ici**, délibérément : `type` et `etat` sont du texte
        libre sans `CHECK` (précédent `angle`), justement pour qu'étendre la liste ne demande pas
        de migration. C'est la couche API qui refuse une valeur hors vocabulaire — un seul endroit,
        celui qui a le contexte pour rendre un message utile.
        """
        inconnus = set(champs) - set(self.CHAMPS_DE_LECTURE)
        if inconnus:
            raise ValueError(f"champ de lecture inconnu : {sorted(inconnus)}")
        if not champs:
            return
        sets = ", ".join(f"{nom}=?" for nom in champs)
        self.conn.execute(f"UPDATE test_case SET {sets}, updated_at=? WHERE id=?",
                          (*champs.values(), now_iso(), case_id))
        self.conn.commit()

    def set_priority(self, case_id: int, priority: str) -> None:
        """Raccourci historique — `set_metadonnees` est la porte d'entrée générale."""
        self.set_metadonnees(case_id, priority=priority)

    def get(self, case_id: int) -> dict | None:
        row = self.conn.execute(_CASE_SELECT + f" WHERE tc.id=? AND {_CASE_VIVANT}",
                                (case_id,)).fetchone()
        return dict(row) if row else None

    def list_all(self, *, project_id: int | None = None, module_id: int | None = None) -> list[dict]:
        """Cas, triés par l'ORDRE D'AFFICHAGE manuel du module (décision 0009), puis `id`.

        Tri de LECTURE uniquement : il ne préjuge pas de l'ordre d'exécution, dicté par l'ordre
        des scénarios dans le `.feature` (0006). `tc.id` en second critère rend l'affichage
        **déterministe** malgré l'absence de contrainte UNIQUE sur `position` : sans lui, deux
        ex æquo pourraient s'afficher dans un ordre différent d'un chargement à l'autre.

        ⚠️ La **priorité n'ordonne plus** la liste (elle le faisait avant 0009) : c'est une
        étiquette d'importance, pas un tri — conforme à 0006/§2.4 qui la dit « étiquette de
        lecture assumée ». Les deux coexistent et sont indépendantes.
        Le tri reste groupé par module sur les vues transverses, sinon des positions propres à
        chaque module s'entremêleraient en un ordre qui ne veut rien dire.
        """
        # La visibilite d'abord : un cas supprime, ou dont le module/projet l'est, ne figure
        # dans AUCUNE liste. C'est ici que le filtre doit vivre — le poser dans chaque appelant
        # garantirait qu'un appelant l'oublie.
        clauses, params = [_CASE_VIVANT], []
        if project_id is not None:
            clauses.append("m.project_id = ?"); params.append(project_id)
        if module_id is not None:
            clauses.append("tc.module_id = ?"); params.append(module_id)
        where = " WHERE " + " AND ".join(clauses)
        order = " ORDER BY tc.module_id, tc.position, tc.id"
        return _rows(self.conn.execute(_CASE_SELECT + where + order, params))

    def page(self, *, project_id: int | None = None, module_id: int | None = None,
             group_id: int | None = None, recherche: str = "", statut: str = "",
             apres: tuple | None = None, limite: int = 100) -> tuple[list[dict], tuple | None, int]:
        """Une PAGE de cas, plus le curseur suivant et le total.

        ⚠️ **Curseur, pas décalage** (`OFFSET`). Un décalage se décale : si quelqu'un crée un cas
        pendant qu'on feuillette, la page suivante saute une ligne ou en répète une, sans que
        personne s'en aperçoive. Le curseur pointe la DERNIÈRE ligne rendue — les écritures
        concurrentes ne le déplacent pas.

        Le curseur est le triplet de tri lui-même `(module_id, position, id)` : c'est la seule
        façon d'être cohérent avec l'ordre d'affichage. SQLite compare les n-uplets directement,
        ce qui donne une reprise exacte sans arithmétique fragile.

        ⚠️ **Recherche et filtre sont ICI, pas dans l'écran.** Filtrer côté navigateur ne
        porterait que sur la page chargée : chercher « sinistre » ne trouverait rien s'il est en
        page 3, et l'utilisateur conclurait que le cas n'existe pas. Un filtre qui ment sur
        l'absence est pire que pas de filtre.
        """
        from testpilot.verdict.status import sql_statut

        clauses, params = [_CASE_VIVANT], []
        if project_id is not None:
            clauses.append("m.project_id = ?"); params.append(project_id)
        if module_id is not None:
            clauses.append("tc.module_id = ?"); params.append(module_id)
        if group_id is not None:
            clauses.append("tc.group_id = ?"); params.append(group_id)
        if recherche.strip():
            # Sur le TITRE et le module — ce que l'utilisateur lit. L'identifiant se cherche par
            # son nombre : l'écran affiche « C12 », on accepte donc « 12 » comme « C12 ».
            motif = f"%{recherche.strip().lstrip('cC')}%"
            clauses.append("(tc.title LIKE ? OR m.name LIKE ? OR CAST(tc.id AS TEXT) LIKE ?)")
            params += [f"%{recherche.strip()}%", f"%{recherche.strip()}%", motif]
        statut_sql = sql_statut("tc.last_execution_status", "tc.last_functional_status")
        if statut:
            clauses.append(f"({statut_sql}) = ?"); params.append(statut)

        where = " WHERE " + " AND ".join(clauses)
        total = int(self.conn.execute(
            f"SELECT COUNT(*) AS n FROM test_case tc"
            f" LEFT JOIN module m ON tc.module_id = m.id"
            f" LEFT JOIN project p ON m.project_id = p.id{where}", params).fetchone()["n"])

        clauses_page, params_page = list(clauses), list(params)
        if apres is not None:
            # ⚠️ `COALESCE` : `module_id` peut être NULL (cas créé par la CLI). Sans lui, la
            # comparaison de n-uplets rendrait NULL — ni vrai ni faux — et la pagination
            # s'arrêterait net sur ces cas-là, en silence.
            clauses_page.append(
                "(COALESCE(tc.module_id, 0), tc.position, tc.id) > (?, ?, ?)")
            params_page += list(apres)
        requete = (_CASE_SELECT + " WHERE " + " AND ".join(clauses_page)
                   + " ORDER BY COALESCE(tc.module_id, 0), tc.position, tc.id LIMIT ?")
        lignes = _rows(self.conn.execute(requete, params_page + [limite + 1]))

        # On demande UN de plus que la limite : c'est ce qui permet de savoir s'il reste quelque
        # chose sans faire un second COUNT — et donc de ne pas proposer « charger plus » sur une
        # liste déjà complète.
        suivant = None
        if len(lignes) > limite:
            lignes = lignes[:limite]
            d = lignes[-1]
            suivant = (d.get("module_id") or 0, d.get("position") or 0, d["id"])
        return lignes, suivant, total

    def reorder(self, module_id: int, case_ids: list[int]) -> None:
        """Fixe l'ordre d'affichage des cas d'un module (décision 0009). Transactionnel.

        `case_ids` doit décrire EXACTEMENT l'ensemble des cas du module — ni id étranger, ni
        manquant, ni doublon. Sinon `ValueError` : accepter une liste partielle laisserait des
        cas à une position périmée (donc un ordre affiché que personne n'a demandé), et un id
        étranger déplacerait un cas hors de son module par un endpoint qui ne parle que d'ordre.

        Les positions sont RECALCULÉES ici (0, 1, 2…) : on ne fait pas confiance à des indices
        envoyés par le client.
        """
        actuels = [r["id"] for r in self.conn.execute(
            "SELECT id FROM test_case WHERE module_id=?", (module_id,))]
        if sorted(case_ids) != sorted(actuels):
            raise ValueError(
                "la liste doit contenir exactement les cas du module "
                f"(attendu {sorted(actuels)}, reçu {sorted(case_ids)})")
        try:
            ts = now_iso()
            for index, case_id in enumerate(case_ids):
                self.conn.execute("UPDATE test_case SET position=?, updated_at=? WHERE id=?",
                                  (index, ts, case_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def feature_slug_taken(self, slug: str) -> bool:
        """Un slug = un fichier .feature sur disque : il doit être unique GLOBALEMENT."""
        row = self.conn.execute("SELECT 1 FROM test_case WHERE feature_slug=? LIMIT 1",
                                (slug,)).fetchone()
        return row is not None

    def set_current_version(self, case_id: int, version_id: int) -> None:
        self.conn.execute(
            "UPDATE test_case SET current_version_id=?, updated_at=? WHERE id=?",
            (version_id, now_iso(), case_id),
        )
        self.conn.commit()

    def set_feature_slug(self, case_id: int, feature_slug: str) -> None:
        """Assigne le nom du fichier `.feature`. Utilisé quand on AUTOMATISE un cas manuel : il
        naît sans slug (pas de test technique), et un run le retrouve par ce champ (§7 / `0004`).
        L'unicité GLOBALE est garantie par l'appelant (`unique_feature_slug`)."""
        self.ensure_slug_free(feature_slug, excluding=case_id)
        self.conn.execute("UPDATE test_case SET feature_slug=?, updated_at=? WHERE id=?",
                          (feature_slug, now_iso(), case_id))
        self.conn.commit()

    # ⚠️ `set_validation_status` a été SUPPRIMÉ (migration 25). Le statut de validation était
    # DÉRIVÉ des exécutions et écrit automatiquement en cinq endroits ; il se donnait des airs de
    # cycle de vie sans en être un — on ne pouvait ni le poser, ni le retirer. `etat` le remplace
    # (Nouveau/Conception/Prêt/Obsolète), écrit UNIQUEMENT par un humain via `set_metadonnees`.

    def update_last_outcome(self, case_id: int, *, execution_status: str,
                            functional_status: str, executed_at: str) -> None:
        """Le RACCOURCI du dernier résultat, après une EXÉCUTION.

        ⚠️ **`last_statut_manuel` est remis à VIDE, et c'est le point le plus important de cette
        méthode.** Sans ça, une saisie humaine ancienne continuerait de court-circuiter la
        dérivation (`statut_de_test` donne la priorité au statut manuel) : le cas afficherait
        indéfiniment le statut saisi à la main, quels que soient les runs verts qui suivent. Le
        défaut ne se voit qu'en croisant deux écrans — la liste dirait « Passed » pendant que le
        rapport d'exécution dit « erreur technique ».

        `last_result_mode='automatique'` : le mode est écrit en même temps que le résultat, jamais
        déduit après coup.
        """
        self.conn.execute(
            "UPDATE test_case SET last_execution_status=?, last_functional_status=?,"
            " last_executed_at=?, last_statut_manuel='', last_result_mode=?,"
            " last_result_at=?, updated_at=? WHERE id=?",
            (execution_status, functional_status, executed_at, MODE_AUTOMATIQUE, executed_at,
             now_iso(), case_id),
        )
        self.conn.commit()

    def update_last_manuel(self, case_id: int, *, statut: str, saisi_at: str) -> None:
        """Le RACCOURCI du dernier résultat, après une exécution MANUELLE.

        ⚠️ **Les deux axes ne sont PAS touchés** (`last_execution_status` /
        `last_functional_status`). Saisir « passed » ne doit jamais écrire « exécution=succès,
        fonctionnel=conforme » : ce serait prétendre qu'une machine a constaté quelque chose. Ils
        gardent donc la dernière MESURE réelle, s'il y en a eu une, et le statut affiché vient du
        statut manuel (qui court-circuite la dérivation dans `statut_de_test`).
        """
        self.conn.execute(
            "UPDATE test_case SET last_statut_manuel=?, last_result_mode=?,"
            " last_result_at=?, updated_at=? WHERE id=?",
            (statut, MODE_MANUELLE, saisi_at, now_iso(), case_id),
        )
        self.conn.commit()


class VersionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, spec_content: str, spec_hash: str,
               feature_content: str, steps_content: str, feature_path: str = "",
               steps_path: str = "", change_summary: str = "", created_by: str = "",
               title: str = "", preconditions: str = "", test_steps: str = "",
               expected_result: str = "") -> int:
        """Crée une version — **le CAS ENTIER**, métier ET technique (décision `0022` n°10).

        Les champs métier (`title`, `preconditions`, `test_steps`, `expected_result`)
        sont figés ici avec le Gherkin : c'est ce qui rend l'historique diffable et ce que le gate
        approuve d'un seul geste. `test_steps` est une **liste JSON**, pas du texte multi-lignes.
        """
        number = self.conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS n"
            " FROM test_case_version WHERE test_case_id=?",
            (test_case_id,),
        ).fetchone()["n"]
        cur = self.conn.execute(
            "INSERT INTO test_case_version (test_case_id, version_number, spec_content,"
            " spec_hash, feature_content, steps_content, feature_path, steps_path,"
            " change_summary, created_at, created_by,"
            " title, preconditions, test_steps, expected_result)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (test_case_id, number, spec_content, spec_hash, feature_content, steps_content,
             feature_path, steps_path, change_summary, now_iso(), created_by,
             title, preconditions, test_steps, expected_result),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, version_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM test_case_version WHERE id=?", (version_id,)).fetchone()
        return dict(row) if row else None

    def latest_for_case(self, test_case_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM test_case_version WHERE test_case_id=?"
            " ORDER BY version_number DESC LIMIT 1",
            (test_case_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM test_case_version WHERE test_case_id=? ORDER BY version_number",
            (test_case_id,)))


class ReviewRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, version_id: int, decision: str,
               reviewer: str = "", comment: str = "",
               repair_budget: int | None = None) -> int:
        """Enregistre une décision de relecture.

        `repair_budget` : tentatives de réparation que cette approbation autorise (0014). `None`
        → le défaut de configuration. Sans objet sur un rejet (rien ne sera exécuté), mais
        stocké tel quel plutôt que forcé à 0 : la colonne dit ce que le relecteur a autorisé,
        pas ce que le système en fera.
        """
        budget = config.REPAIR_BUDGET_DEFAULT if repair_budget is None else max(0, int(repair_budget))
        cur = self.conn.execute(
            "INSERT INTO review_decision (test_case_id, version_id, decision, reviewer,"
            " comment, repair_budget, decided_at) VALUES (?,?,?,?,?,?,?)",
            (test_case_id, version_id, decision, reviewer, comment, budget, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def repair_budget_for_version(self, version_id: int) -> int:
        """Tentatives de réparation autorisées pour cette version — 0 si non approuvée.

        Lit la DERNIÈRE décision : une version rejetée puis ré-approuvée suit la plus récente.
        Une version non relue rend 0 — pas de gate, pas d'exécution, donc pas de réparation
        (§4.3). C'est la seule lecture qui ne contourne pas le gate.
        """
        latest = self.latest_for_version(version_id)
        if not latest or latest["decision"] != "approved":
            return 0
        return int(latest["repair_budget"] or 0)

    def latest_for_version(self, version_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM review_decision WHERE version_id=? ORDER BY id DESC LIMIT 1",
            (version_id,)).fetchone()
        return dict(row) if row else None

    def is_version_approved(self, version_id: int) -> bool:
        latest = self.latest_for_version(version_id)
        return bool(latest and latest["decision"] == "approved")

    def approved_version_ids(self, version_ids: list[int]) -> set[int]:
        """Parmi CES versions, celles dont la DERNIÈRE décision est `approved` — en UNE requête.

        Sert à trouver les cas bloqués sur tout un projet sans évaluer le gate un par un (2026-09-
        15, `GET /api/cases/needing-review`) : un projet de plusieurs centaines de cas ferait
        sinon autant d'allers-retours que de cas, pour une question qui se répond en un seul.
        Même forme que `ResultRepo.derniers_du_run` (MAX(id) par groupe, jamais 2×N requêtes).
        """
        ids = [int(v) for v in version_ids if v]
        if not ids:
            return set()
        marqueurs = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT rd.version_id FROM review_decision rd"
            f" JOIN (SELECT version_id, MAX(id) AS dernier FROM review_decision"
            f"       WHERE version_id IN ({marqueurs}) GROUP BY version_id) d"
            f" ON d.dernier = rd.id"
            f" WHERE rd.decision = 'approved'", ids)
        return {int(r["version_id"]) for r in rows}

    def list_for_case(self, test_case_id: int) -> list[dict]:
        """Historique des décisions de relecture d'un cas (toutes versions), anté-chronologique."""
        return _rows(self.conn.execute(
            "SELECT * FROM review_decision WHERE test_case_id=? ORDER BY id DESC",
            (test_case_id,)))


class ExecutionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def quality_summary(self, *, project_id: int | None = None,
                        allowed_project_ids: list[int] | None = None) -> dict:
        """Santé TECHNIQUE de la génération : un test fraîchement produit TOURNE-T-IL ?

        ⚠️ On mesure l'axe EXÉCUTION (`execution_status`), jamais le fonctionnel — un test qui
        tourne et détecte un vrai bug est un SUCCÈS technique (§5, invariant des deux axes). C'est
        exactement la question « faire les tests sans erreur technique » : `success` = a tourné,
        `technical_error` = n'a pas pu, `not_executed` = interrompu avant de tourner.

        **Restreint aux `first_run`** : c'est le signal de la qualité de GÉNÉRATION. Une tentative
        de réparation ou un rejeu mesureraient autre chose (le filet, pas le premier jet). Les
        mélanger gonflerait ou masquerait le vrai taux.

        ⚠️ **Rien n'est déclaratif ici** (invariant §4.2) : chaque ligne agrégée est une exécution
        RÉELLE qui a eu lieu. Le tableau de bord ne fabrique aucun chiffre — il compte des runs.
        """
        if project_id is not None and allowed_project_ids is not None:
            raise ValueError("project_id et allowed_project_ids sont mutuellement exclusifs")

        # Une ligne vient d'être créée avec le statut par défaut `not_executed` avant que le
        # worker ne démarre. Elle n'est pas encore une mesure : la compter ferait baisser le
        # tableau de bord pendant chaque exécution en cours.
        where = ("WHERE e.trigger = 'first_run'"
                 " AND NOT (e.execution_status = 'not_executed'"
                 " AND e.duration_seconds = 0 AND e.scenarios_total = 0"
                 " AND e.error_message = '')")
        params: tuple = ()
        if project_id is not None:
            where += (" AND e.test_case_id IN (SELECT tc.id FROM test_case tc"
                      " JOIN module m ON tc.module_id = m.id WHERE m.project_id = ?)")
            params = (project_id,)
        elif allowed_project_ids is not None:
            ids = list(dict.fromkeys(int(pid) for pid in allowed_project_ids))
            if not ids:
                where += " AND 0"
            else:
                marqueurs = ",".join("?" for _ in ids)
                where += (" AND e.test_case_id IN (SELECT tc.id FROM test_case tc"
                          " JOIN module m ON tc.module_id = m.id"
                          f" WHERE m.project_id IN ({marqueurs}))")
                params = tuple(ids)

        def _compte(sql_extra: str) -> list[dict]:
            return _rows(self.conn.execute(
                f"SELECT substr(e.started_at, 1, 10) AS jour, e.execution_status AS statut,"
                f" COUNT(*) AS n FROM execution e {where}{sql_extra}"
                f" GROUP BY jour, statut ORDER BY jour", params))

        lignes = _compte("")
        total = {"success": 0, "technical_error": 0, "not_executed": 0}
        par_jour: dict[str, dict] = {}
        for r in lignes:
            statut = r["statut"] if r["statut"] in total else "not_executed"
            total[statut] += r["n"]
            jour = par_jour.setdefault(r["jour"], {"jour": r["jour"], "success": 0,
                                                   "technical_error": 0, "not_executed": 0})
            jour[statut] += r["n"]

        n = sum(total.values())
        mesures_concluantes = total["success"] + total["technical_error"]
        # `ran_rate` reste None (et non 0.0) sans donnée : « aucune mesure » n'est pas « 0 % de
        # réussite » — le motif du repli silencieux qu'on refuse partout (§4.6).
        # Une interruption ne prouve ni la réussite ni l'échec de la génération. Elle reste
        # visible, mais ne dégrade pas artificiellement le taux.
        ran_rate = (total["success"] / mesures_concluantes) if mesures_concluantes else None
        return {
            "total": n,
            "ran": total["success"],
            "technical_error": total["technical_error"],
            "not_executed": total["not_executed"],
            "ran_rate": ran_rate,
            "by_day": sorted(par_jour.values(), key=lambda d: d["jour"]),
        }

    def create(self, *, test_case_id: int, version_id: int, trigger: str = "first_run",
               cible: dict | None = None, triggered_by: str = "") -> int:
        """Ouvre une ligne d'exécution.

        `cible` (migration 20) : contre quelle application on va tourner — adresse, base,
        utilisateur, **jamais le mot de passe**. Écrite à l'OUVERTURE et non à la clôture : une
        exécution qui plante avant la fin doit tout de même dire ce qu'elle visait.

        `triggered_by` (migration 32) : le compte réel qui a déclenché ce run — vide si aucun n'a
        pu être résolu (`finalize` retombe alors sur le compte de service). Écrit ICI, une seule
        fois : une réparation créée `run_once()` le passe explicitement, elle hérite ainsi de
        l'acteur du run d'origine plutôt que d'en perdre la trace.
        """
        c = cible or {}
        cur = self.conn.execute(
            "INSERT INTO execution (test_case_id, version_id, trigger, target_url,"
            " target_database, target_username, triggered_by, started_at) VALUES (?,?,?,?,?,?,?,?)",
            (test_case_id, version_id, trigger, str(c.get("target_url") or ""),
             str(c.get("target_database") or ""), str(c.get("target_username") or ""),
             triggered_by or "", now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_artifacts_path(self, execution_id: int, chemin: str) -> None:
        """Enregistre où la trace brute de cette exécution a été archivée (migration 22)."""
        self.conn.execute("UPDATE execution SET artifacts_path=? WHERE id=?",
                          (str(chemin or ""), execution_id))
        self.conn.commit()

    def finalize(self, execution_id: int, *, execution_status: str, functional_status: str,
                 scenarios_total: int, scenarios_passed: int, scenarios_failed: int,
                 cost_usd: float, iterations: int, duration_seconds: float,
                 field_fallbacks: str = "", error_message: str = "",
                 comment: str = "") -> int | None:
        """Clôt une exécution avec son verdict. Rend l'id de la ligne du registre (§A du plan
        « fiabiliser le verdict automatique », 2026-08-06) — `None` si l'exécution n'a pas sa
        place au registre (hors campagne).

        `error_message` : raison d'un plantage AVANT tout scénario (migration 11) — sans elle,
        l'écran affiche « erreur technique » sans dire pourquoi.

        `comment` : le commentaire en français clair qui accompagne ce verdict (§A). ⚠️ Écrit ICI,
        à la CRÉATION de la ligne du registre — jamais par une UPDATE ultérieure : le registre
        n'autorise aucune modification après coup (`ResultRepo`, §7 : « rien n'est jamais modifié
        ni supprimé »). L'appelant doit donc avoir généré le commentaire AVANT d'appeler
        `finalize` — cf. `run_service._persist`.

        ⚠️ `report_json_path`/`report_html_path` ont été **supprimés** (migration 7) : personne ne
        les alimentait ni ne les lisait. Le rapport est **reconstruit à la demande** depuis la
        base (`report_service.build_report_for_execution`) — c'est le seul mécanisme réel.

        ⚠️ **C'est ici, et NULLE PART AILLEURS, que le registre apprend qu'une exécution a eu un
        résultat.** `finalize` est le seul goulot : le chemin normal (`run_service._persist`) et
        le chemin d'échec (`_ecrire_erreur`) y passent tous les deux. Brancher le registre sur les
        appelants aurait demandé de n'en oublier aucun — et le jour où un troisième apparaît, le
        résultat manquerait au registre sans que rien ne le signale.
        """
        self.conn.execute(
            "UPDATE execution SET execution_status=?, functional_status=?, scenarios_total=?,"
            " scenarios_passed=?, scenarios_failed=?, cost_usd=?, iterations=?,"
            " duration_seconds=?, field_fallbacks=?, error_message=?"
            " WHERE id=?",
            (execution_status, functional_status, scenarios_total, scenarios_passed,
             scenarios_failed, cost_usd, iterations, duration_seconds,
             field_fallbacks, error_message, execution_id),
        )
        self.conn.commit()
        # Le déclencheur RÉEL (migration 32) prime : c'est lui qui a cliqué « Lancer », pas le
        # compte de service. Repli sur le compte de service SEULEMENT si aucun acteur n'a pu être
        # résolu à la création de la ligne (`triggered_by` vide) — filet pour un déclenchement
        # futur sans session (CI, tâche planifiée), aucun cas de ce genre aujourd'hui. Résolu
        # MAINTENANT et recopié dans la ligne : changer le réglage plus tard ne doit pas réécrire
        # l'auteur des résultats déjà produits.
        row = self.conn.execute(
            "SELECT triggered_by FROM execution WHERE id=?", (execution_id,)).fetchone()
        triggered_by = (row["triggered_by"] if row else "") or ""
        # ⚠️ Repli sur `config.SERVICE_ACCOUNT_NAME` DIRECT, plus via `SettingRepo` (2026-08-12) —
        # ce nom n'est plus un réglage modifiable depuis l'écran : le porteur l'a explicitement
        # demandé (« ça ne devrait pas être un paramètre modifiable », confirmé sur l'écran
        # Réglages). Reste ajustable au déploiement par la variable d'environnement
        # `TESTPILOT_SERVICE_ACCOUNT` — une configuration d'exploitant, plus un réglage produit.
        created_by = triggered_by or config.SERVICE_ACCOUNT_NAME
        return ResultRepo(self.conn).enregistrer_execution(
            execution_id, created_by=created_by, comment=comment)

    def get(self, execution_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM execution WHERE id=?", (execution_id,)).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM execution WHERE test_case_id=? ORDER BY id", (test_case_id,)))

    def has_for_version(self, version_id: int) -> bool:
        """Dit si cette version précise a déjà été jouée."""
        row = self.conn.execute(
            "SELECT 1 FROM execution WHERE version_id=? LIMIT 1", (version_id,)).fetchone()
        return row is not None

    def list_recent(self, limit: int = 50, *, project_id: int | None = None) -> list[dict]:
        """Exécutions récentes (onglet Exécution), plus récentes d'abord, avec le contexte de
        ce qui a tourné (titre du cas + module).

        Filtrées sur un projet si ``project_id`` est fourni — jamais de mélange inter-projets.
        """
        select = (
            "SELECT e.*, tc.title AS case_title, m.name AS module_name"
            " FROM execution e"
            " LEFT JOIN test_case tc ON e.test_case_id = tc.id"
            " LEFT JOIN module m ON tc.module_id = m.id"
        )
        if project_id is not None:
            return _rows(self.conn.execute(
                select + " WHERE m.project_id = ? ORDER BY e.id DESC LIMIT ?",
                (project_id, max(1, limit))))
        return _rows(self.conn.execute(select + " ORDER BY e.id DESC LIMIT ?", (max(1, limit),)))

    def add_scenario_result(self, *, execution_id: int, scenario_name: str,
                            execution_status: str, functional_status: str,
                            failure_type: str = "", cause_category: str = "",
                            error_summary: str = "", step_text: str = "") -> int:
        """`step_text` : le step en échec, gardé pour AUDITER `cause_category` (décision 0015).
        Trace, jamais critère — la taxonomie ne le lit pas."""
        cur = self.conn.execute(
            "INSERT INTO scenario_result (execution_id, scenario_name, execution_status,"
            " functional_status, failure_type, cause_category, error_summary, step_text)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (execution_id, scenario_name, execution_status, functional_status,
             failure_type, cause_category, error_summary, step_text),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_cost(self, execution_id: int, cost_usd: float) -> None:
        """AJOUTE un coût LLM à une exécution (jamais un remplacement).

        `finalize` écrit `cost_usd` une fois, à la clôture ; une réparation, elle, dépense APRÈS
        cette clôture (l'agent propose, puis on rejoue). Écraser perdrait l'un ou l'autre — d'où
        un cumul explicite.
        """
        self.conn.execute("UPDATE execution SET cost_usd = cost_usd + ? WHERE id=?",
                          (float(cost_usd), execution_id))
        self.conn.commit()

    def list_scenario_results(self, execution_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM scenario_result WHERE execution_id=? ORDER BY id", (execution_id,)))


class RunRepo:
    """Le RUN — une campagne de N cas (décision `0022` n°8). Un run REGROUPE des cas à jouer
    ensemble ; le résultat d'un cas DANS un run est une `execution` rattachée (`run_id`).

    Deux modes de sélection : `all` (VIVANT — les cas du projet, recalculés à la lecture) et
    `frozen` (FIGÉ — la liste choisie, matérialisée dans `test_run_case`). Le filtrage dynamique
    est reporté (`0022` 8.a)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, project_id: int, name: str, description: str = "", refs: str = "",
               selection_mode: str = "frozen", mode: str = MODE_AUTOMATIQUE,
               case_ids: list[int] | None = None) -> int:
        """Crée un run en BROUILLON (jamais lancé à la création — `0022` 8.c.1).

        `case_ids` n'est matérialisé que pour `frozen` : en mode `all`, la sélection est vivante,
        la stocker figerait ce qu'on veut justement garder mouvant.

        `mode` est le MODE D'EXÉCUTION de la campagne (2026-08-04) : `automatique` (la machine
        joue les cas) ou `manuelle` (un humain les joue et saisit ce qu'il a constaté). Il décide
        des gestes offerts par l'écran, et le mode de chaque résultat doit lui concorder —
        invariant tenu par un trigger de la base, pas par une politesse des routes.
        """
        if mode not in MODES_EXECUTION:
            raise ValueError(f"mode d'exécution inconnu : {mode!r} — attendu {list(MODES_EXECUTION)}")
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_run (project_id, name, description, refs, selection_mode, mode,"
            " status, created_at) VALUES (?,?,?,?,?,?,'draft',?)",
            (project_id, name, description, refs, selection_mode, mode, ts))
        run_id = int(cur.lastrowid)
        if selection_mode == "frozen":
            for cid in dict.fromkeys(case_ids or []):  # dédup en gardant l'ordre
                self.conn.execute(
                    "INSERT OR IGNORE INTO test_run_case (run_id, case_id) VALUES (?,?)",
                    (run_id, cid))
        self.conn.commit()
        return run_id

    def get(self, run_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM test_run WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        # `tested_count` = cas DISTINCTS ayant un RÉSULTAT dans ce run — la base du « % de
        # complétion » de l'écran Aperçu (note fonctionnelle). Le total dépend du mode (figé =
        # frozen_count ; vivant = calculé par l'appelant), d'où les deux exposés.
        #
        # ⚠️ Compté sur le REGISTRE et non sur `execution` depuis le 2026-08-04 : une campagne
        # testée à la main afficherait sinon 0 % pour toujours, alors qu'elle est finie. Les
        # campagnes existantes ne bougent pas — la migration 25 leur a créé une ligne de registre
        # par exécution.
        #
        # `manuel_count` = cas dont le DERNIER résultat a été joué à la MAIN. C'est ce qui permet
        # de dire « 12 cas sur 40 ont été joués à la main » plutôt que de laisser une barre verte
        # sous-entendre que tout a été prouvé par la machine.
        return _rows(self.conn.execute(
            "SELECT r.*,"
            " (SELECT COUNT(*) FROM test_run_case rc WHERE rc.run_id=r.id) AS frozen_count,"
            " (SELECT COUNT(DISTINCT tr.case_id) FROM test_result tr WHERE tr.run_id=r.id)"
            "     AS tested_count,"
            " (SELECT COUNT(*) FROM test_result tr"
            "    JOIN (SELECT case_id, MAX(id) AS dernier FROM test_result WHERE run_id=r.id"
            "          GROUP BY case_id) d ON d.dernier = tr.id"
            "    WHERE tr.mode=?) AS manuel_count"
            " FROM test_run r WHERE r.project_id=? ORDER BY r.id DESC",
            (MODE_MANUELLE, project_id)))

    def for_plan(self, plan_id: int) -> list[dict]:
        """Mêmes colonnes calculées que `list_for_project` (migration 43) — un Plan affiche
        chacun de ses runs avec son PROPRE résumé complet, jamais un chiffre fusionné."""
        return _rows(self.conn.execute(
            "SELECT r.*,"
            " (SELECT COUNT(*) FROM test_run_case rc WHERE rc.run_id=r.id) AS frozen_count,"
            " (SELECT COUNT(DISTINCT tr.case_id) FROM test_result tr WHERE tr.run_id=r.id)"
            "     AS tested_count,"
            " (SELECT COUNT(*) FROM test_result tr"
            "    JOIN (SELECT case_id, MAX(id) AS dernier FROM test_result WHERE run_id=r.id"
            "          GROUP BY case_id) d ON d.dernier = tr.id"
            "    WHERE tr.mode=?) AS manuel_count"
            " FROM test_run r WHERE r.plan_id=? ORDER BY r.id DESC",
            (MODE_MANUELLE, plan_id)))

    def case_ids(self, run_id: int) -> list[int]:
        """Les cas du run : recalculés (mode `all`) ou lus dans la liaison figée (`frozen`)."""
        run = self.get(run_id)
        if run is None:
            return []
        # ⚠️ Un cas SUPPRIMÉ ne fait plus partie d'aucune campagne — ni en mode `all` (la
        # sélection est vivante), ni en `frozen` (la liaison figée le référence encore). Sans ce
        # filtre, lancer une campagne EXÉCUTERAIT des cas que l'utilisateur croit supprimés,
        # contre la vraie application. C'est le défaut le plus grave qu'aurait pu introduire la
        # suppression douce — trouvé par un test qui portait sur tout autre chose.
        if run["selection_mode"] == "all":
            return [r["id"] for r in self.conn.execute(
                "SELECT tc.id FROM test_case tc JOIN module m ON tc.module_id=m.id"
                " JOIN project p ON m.project_id=p.id"
                " WHERE m.project_id=? AND tc.deleted_at='' AND m.deleted_at=''"
                " AND p.deleted_at='' ORDER BY tc.id", (run["project_id"],))]
        return [r["case_id"] for r in self.conn.execute(
            "SELECT trc.case_id FROM test_run_case trc"
            " JOIN test_case tc ON trc.case_id=tc.id"
            " LEFT JOIN module m ON tc.module_id=m.id"
            " LEFT JOIN project p ON m.project_id=p.id"
            " WHERE trc.run_id=? AND tc.deleted_at=''"
            " AND (m.id IS NULL OR m.deleted_at='')"
            " AND (p.id IS NULL OR p.deleted_at='') ORDER BY trc.case_id", (run_id,))]

    def cases_with_results(self, run_id: int) -> list[dict]:
        """Chaque cas du run + son résultat DANS CE run, lu au REGISTRE (2026-08-04).

        C'est le cœur de `0022` n°4 : le résultat vit sur le cas × run. Un cas sans résultat dans
        ce run est « Non testé » — on l'expose quand même (il fait partie de la campagne).

        ⚠️ **`case_ids()` reste l'UNIQUE porte d'entrée** vers les cas d'une campagne : c'est elle
        qui porte l'invariant de suppression douce (un cas à la corbeille ne fait plus partie
        d'aucune campagne, ni en mode vivant ni en figé). Lire `test_run_case` directement ici
        ferait réapparaître des cas que l'utilisateur croit supprimés — et, pire, les exécuterait.

        ⚠️ **Le résultat ne vient plus de la dernière `execution`** : il vient du registre, qui
        sait aussi porter un résultat DÉCLARÉ par un humain. Une campagne entièrement testée à la
        main afficherait sinon « Non testé » partout.

        **Deux requêtes, jamais 2×N** : une pour les cas, une pour leurs derniers résultats. La
        version précédente en faisait deux PAR CAS — 1 000 allers-retours sur une campagne de 500.
        """
        ids = self.case_ids(run_id)
        if not ids:
            return []
        marqueurs = ",".join("?" * len(ids))
        cases = {int(r["id"]): dict(r) for r in self.conn.execute(
            f"SELECT id, title, last_execution_status, last_functional_status"
            f" FROM test_case WHERE id IN ({marqueurs})", ids)}
        derniers = ResultRepo(self.conn).derniers_du_run(run_id)
        # « Qui supervise » ce cas dans CETTE campagne (2026-09-14, traçabilité — la table
        # existait depuis la migration 25, rien ne la lisait). Même discipline que `derniers`
        # ci-dessus : une requête pour TOUTE la campagne, jamais une par cas.
        assignations = AssignmentRepo(self.conn).for_run(run_id)

        out = []
        for cid in ids:
            case = cases.get(cid)
            if case is None:
                continue  # supprimé entre les deux requêtes — on ne fabrique rien
            ligne = dict(case)
            ligne["result"] = derniers.get(cid)
            assignation = assignations.get(cid)
            ligne["assigned_to"] = (assignation or {}).get("assigned_to", "")
            out.append(ligne)
        return out

    def cibles_du_run(self, run_id: int) -> list[dict]:
        """Contre quelle(s) application(s) cette campagne a RÉELLEMENT tourné.

        ⚠️ Lu sur les **exécutions de la campagne**, jamais sur la connexion actuelle du projet :
        celle-ci a pu changer depuis, et afficher la cible d'aujourd'hui sur des résultats d'hier
        serait précisément le mensonge que la migration 20 sert à empêcher.

        Rend la liste des cibles **distinctes** — normalement une seule. Plusieurs signifie que la
        connexion du projet a été modifiée en cours de campagne : c'est anormal, et l'écran doit
        le dire plutôt que d'en choisir une au hasard.
        """
        return _rows(self.conn.execute(
            "SELECT DISTINCT target_url, target_database FROM execution"
            " WHERE run_id=? AND target_url <> ''", (run_id,)))

    def archive(self, run_id: int, archived: bool = True) -> None:
        """Clôt (ou rouvre) une campagne. Un run archivé est en LECTURE SEULE : on ne le relance
        plus, ses résultats sont figés (note fonctionnelle — « bandeau exécution archivée »).

        ⚠️ **Archivage ≠ suppression** : rien n'est effacé, le run et ses résultats restent
        consultables (§2.10). Réversible aussi : une clôture faite par erreur ne doit pas être
        irrattrapable — c'est la même logique que l'arbitrage réversible d'un diagnostic.

        ⚠️ **Pas de SNAPSHOT des cas ici** (décision n°2 de la note fonctionnelle, reportée) : un
        cas modifié après la clôture s'affichera dans son état actuel. C'est un écart connu et
        assumé, pas un oubli.
        """
        self.conn.execute("UPDATE test_run SET is_archived=? WHERE id=?",
                          (1 if archived else 0, run_id))
        self.conn.commit()

    def set_status(self, run_id: int, status: str, *, launched: bool = False,
                   completed: bool = False) -> None:
        sets, params = ["status=?"], [status]
        if launched:
            sets.append("launched_at=?"); params.append(now_iso())
        if completed:
            sets.append("completed_at=?"); params.append(now_iso())
        params.append(run_id)
        self.conn.execute(f"UPDATE test_run SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()


class AssignmentRepo:
    """Qui SUPERVISE un cas dans une campagne (`run_case_assignment`, migration 25, 2026-08-04).

    ⚠️ **Table créée depuis l'origine, mais jamais alimentée avant ce correctif (2026-09-14)** —
    trouvé en auditant la traçabilité de l'application (inspiré de TestRail : chaque test d'un
    run porte un « Assigné à »). L'écran affichait un « — » figé en le disant explicitement
    dans son commentaire (`RunDetail.vue`).

    ⚠️ **`assigned_to` reste du TEXTE LIBRE, pas une FK vers `user`** — même choix que
    `created_by`/`triggered_by` partout ailleurs dans le projet : un compte supprimé plus tard
    ne doit jamais effacer la trace de qui a été assigné (c'est justement ce que la
    traçabilité protège). Le texte vient malgré tout des membres RÉELS du projet côté écran
    (`ProjectMemberRepo`), jamais tapé à la main — le champ reste libre pour ne rien casser si
    un membre quitte le projet entre-temps.

    ⚠️ **Vaut pour un cas MANUEL comme AUTOMATIQUE** (demande explicite du porteur) : superviser
    un résultat produit par une machine (relire, confirmer, investiguer un échec) est un geste
    humain identique à celui de jouer un cas à la main — la table ne distingue pas les deux, la
    campagne le fait déjà (`test_run.mode`).
    """

    def __init__(self, conn):
        self.conn = conn

    def get(self, run_id: int, case_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM run_case_assignment WHERE run_id=? AND case_id=?",
            (run_id, case_id)).fetchone()
        return dict(row) if row else None

    def for_run(self, run_id: int) -> dict[int, dict]:
        """Toutes les assignations d'une campagne, indexées par cas — UNE requête, jamais N
        (même discipline que `ResultRepo.derniers_du_run`)."""
        rows = _rows(self.conn.execute(
            "SELECT * FROM run_case_assignment WHERE run_id=?", (run_id,)))
        return {int(r["case_id"]): r for r in rows}

    def set(self, run_id: int, case_id: int, *, assigned_to: str, assigned_by: str) -> None:
        """Assigne (ou réassigne) — `ON CONFLICT` : une ligne par (run, cas), jamais un doublon
        qui laisserait deviner laquelle fait foi."""
        self.conn.execute(
            "INSERT INTO run_case_assignment (run_id, case_id, assigned_to, assigned_by, assigned_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(run_id, case_id) DO UPDATE SET"
            " assigned_to=excluded.assigned_to, assigned_by=excluded.assigned_by,"
            " assigned_at=excluded.assigned_at",
            (run_id, case_id, assigned_to, assigned_by, now_iso()))
        self.conn.commit()

    def clear(self, run_id: int, case_id: int) -> None:
        """Retire l'assignation — jamais une ligne « assigné à rien », son absence EST le fait."""
        self.conn.execute(
            "DELETE FROM run_case_assignment WHERE run_id=? AND case_id=?", (run_id, case_id))
        self.conn.commit()


class PlanRepo:
    """Plans de test (migration 43) — regroupe plusieurs campagnes SOUS UN MÊME rapport
    consolidé. Purement organisationnel : ne change rien à l'exécution ni au lancement d'un run,
    c'est la troisième couche au-dessus (`Projet → Plan → Campagnes → Cas → Résultats`)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, project_id: int, name: str, description: str = "", refs: str = "",
               created_by: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO test_plan (project_id, name, description, refs, created_by, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, name, description, refs, created_by, now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, plan_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM test_plan WHERE id=?", (plan_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM test_plan WHERE project_id=? ORDER BY id DESC", (project_id,)))

    def runs_of_plan(self, plan_id: int) -> list[dict]:
        """Chaque run garde son PROPRE statut/mode/compteurs — jamais fusionnés en un seul
        chiffre (une campagne manuelle et une automatique ne se lisent pas de la même façon).
        Délègue à `RunRepo.for_plan` : mêmes colonnes calculées que la liste d'un projet."""
        return RunRepo(self.conn).for_plan(plan_id)

    def assign_run(self, plan_id: int, run_id: int) -> None:
        self.conn.execute("UPDATE test_run SET plan_id=? WHERE id=?", (plan_id, run_id))
        self.conn.commit()

    def unassign_run(self, run_id: int) -> None:
        self.conn.execute("UPDATE test_run SET plan_id=NULL WHERE id=?", (run_id,))
        self.conn.commit()

    def update(self, plan_id: int, *, name: str | None = None, description: str | None = None,
               refs: str | None = None) -> None:
        """N'écrit que les champs FOURNIS (`None` = inchangé) — jamais `project_id`, un plan ne
        change pas de projet."""
        champs, valeurs = [], []
        if name is not None:
            champs.append("name=?"); valeurs.append(name)
        if description is not None:
            champs.append("description=?"); valeurs.append(description)
        if refs is not None:
            champs.append("refs=?"); valeurs.append(refs)
        if not champs:
            return
        valeurs.append(plan_id)
        self.conn.execute(f"UPDATE test_plan SET {', '.join(champs)} WHERE id=?", valeurs)
        self.conn.commit()

    def delete(self, plan_id: int) -> None:
        """Supprime le PLAN, jamais les campagnes qu'il contenait — purement organisationnel,
        les runs redeviennent simplement hors de tout plan (référence souple, `plan_id` vers
        NULL), exactement comme un retrait manuel un par un."""
        self.conn.execute("UPDATE test_run SET plan_id=NULL WHERE plan_id=?", (plan_id,))
        self.conn.execute("DELETE FROM test_plan WHERE id=?", (plan_id,))
        self.conn.commit()


class ScheduledRunRepo:
    """Planifications récurrentes (migration 43) — lance automatiquement une campagne sur une
    horloge, en réutilisant TEL QUEL le moteur d'exécution existant (`campaign_service`).

    ⚠️ Aucune colonne/paramètre `mode` : une planification est TOUJOURS automatique — voir
    `scheduler_service.tick()`, qui force `MODE_AUTOMATIQUE` à la création du `test_run` qu'elle
    engendre. Le lire depuis une entrée utilisateur serait la seule façon de se tromper ici."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, project_id: int, name: str, selection_mode: str = "frozen",
               frequency: str, hour: int, minute: int, weekday: int | None = None,
               case_ids: list[int] | None = None, created_by: str = "") -> int:
        if frequency not in ("daily", "weekly"):
            raise ValueError(f"fréquence inconnue : {frequency!r} — attendu 'daily' ou 'weekly'")
        if frequency == "weekly" and weekday is None:
            raise ValueError("une planification hebdomadaire doit préciser le jour (weekday)")
        cur = self.conn.execute(
            "INSERT INTO scheduled_run (project_id, name, selection_mode, frequency, hour,"
            " minute, weekday, is_active, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,1,?,?)",
            (project_id, name, selection_mode, frequency, hour, minute, weekday,
             created_by, now_iso()))
        scheduled_id = int(cur.lastrowid)
        if selection_mode == "frozen":
            for cid in dict.fromkeys(case_ids or []):
                self.conn.execute(
                    "INSERT OR IGNORE INTO scheduled_run_case (scheduled_run_id, case_id)"
                    " VALUES (?,?)", (scheduled_id, cid))
        self.conn.commit()
        return scheduled_id

    def get(self, scheduled_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM scheduled_run WHERE id=?", (scheduled_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM scheduled_run WHERE project_id=? ORDER BY id DESC", (project_id,)))

    def list_active(self) -> list[dict]:
        """TOUTES les planifications actives, tous projets confondus — `scheduler_service.tick()`
        balaie l'ensemble à chaque passage plutôt qu'un projet à la fois."""
        return _rows(self.conn.execute(
            "SELECT * FROM scheduled_run WHERE is_active=1 ORDER BY id"))

    def case_ids(self, scheduled_id: int) -> list[int]:
        """Même logique que `RunRepo.case_ids` : `all` reste VIVANT (recalculé à chaque
        déclenchement), `frozen` est matérialisé dans `scheduled_run_case`."""
        row = self.get(scheduled_id)
        if row is None:
            return []
        if row["selection_mode"] == "all":
            return [r["id"] for r in self.conn.execute(
                "SELECT tc.id FROM test_case tc JOIN module m ON tc.module_id=m.id"
                " JOIN project p ON m.project_id=p.id"
                " WHERE m.project_id=? AND tc.deleted_at='' AND m.deleted_at=''"
                " AND p.deleted_at='' ORDER BY tc.id", (row["project_id"],))]
        return [r["case_id"] for r in self.conn.execute(
            "SELECT src.case_id FROM scheduled_run_case src"
            " JOIN test_case tc ON src.case_id=tc.id"
            " LEFT JOIN module m ON tc.module_id=m.id"
            " LEFT JOIN project p ON m.project_id=p.id"
            " WHERE src.scheduled_run_id=? AND tc.deleted_at=''"
            " AND (m.id IS NULL OR m.deleted_at='')"
            " AND (p.id IS NULL OR p.deleted_at='') ORDER BY src.case_id", (scheduled_id,))]

    def set_active(self, scheduled_id: int, active: bool) -> None:
        self.conn.execute("UPDATE scheduled_run SET is_active=? WHERE id=?",
                          (1 if active else 0, scheduled_id))
        self.conn.commit()

    def delete(self, scheduled_id: int) -> None:
        self.conn.execute("DELETE FROM scheduled_run_case WHERE scheduled_run_id=?",
                          (scheduled_id,))
        self.conn.execute("DELETE FROM scheduled_run WHERE id=?", (scheduled_id,))
        self.conn.commit()

    def mark_triggered(self, scheduled_id: int, run_id: int, *, at: str | None = None) -> None:
        self.conn.execute(
            "UPDATE scheduled_run SET last_run_id=?, last_triggered_at=? WHERE id=?",
            (run_id, at or now_iso(), scheduled_id))
        self.conn.commit()


class RepairRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, execution_id: int, attempt_number: int, failure_signature: str,
               cause_category: str, defect_origin: str, confirmation_status: str,
               what_was_tried: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO repair_attempt (execution_id, attempt_number, failure_signature,"
            " cause_category, defect_origin, confirmation_status, what_was_tried, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (execution_id, attempt_number, failure_signature, cause_category, defect_origin,
             confirmation_status, what_was_tried, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_for_execution(self, execution_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM repair_attempt WHERE execution_id=? ORDER BY attempt_number",
            (execution_id,)))

    def historique_pour_cas(self, case_id: int, limit: int = 20) -> list[dict]:
        """Toutes les tentatives d'un CAS — toutes exécutions, toutes sessions confondues.

        ⚠️ **Ce trou est la raison pour laquelle la boucle rachetait les mêmes correctifs.** La
        base portait déjà tout l'historique (signature d'échec, cause, issue), mais on ne savait
        le lire que par exécution : chaque nouvelle session repartait donc aveugle, et
        redécouvrait — en le repayant — ce qu'une session précédente avait déjà établi.

        Rendu du plus RÉCENT au plus ancien : c'est ce qui informe le plus, et le plafond coupe
        donc par la queue.
        """
        return _rows(self.conn.execute(
            "SELECT ra.*, e.version_id, e.execution_status, e.functional_status"
            " FROM repair_attempt ra JOIN execution e ON e.id = ra.execution_id"
            " WHERE e.test_case_id = ?"
            " ORDER BY ra.created_at DESC, ra.id DESC LIMIT ?",
            (case_id, limit)))

class CostRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_entry(self, *, phase: str, model: str, cost_usd: float, source: str,
                  execution_id: int | None = None, test_case_id: int | None = None,
                  at: str | None = None) -> int:
        """Inscrit une dépense LLM. `test_case_id` est le lien qui compte (§9).

        ⚠️ **Passer `test_case_id`, toujours.** `execution_id` ne suffit pas : une génération
        n'a **aucune exécution** (elle la précède), donc son coût — le poste le plus lourd —
        n'avait nulle part où s'accrocher et disparaissait. Si seul `execution_id` est fourni,
        on retrouve le cas par lui : un appelant qui ne connaît que son run reste correct.
        """
        ts = at or now_iso()
        if test_case_id is None and execution_id is not None:
            row = self.conn.execute("SELECT test_case_id FROM execution WHERE id=?",
                                    (execution_id,)).fetchone()
            if row:
                test_case_id = int(row["test_case_id"])
        cur = self.conn.execute(
            "INSERT INTO cost_ledger (period_month, test_case_id, execution_id, phase, model,"
            " cost_usd, source, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (period_of(ts), test_case_id, execution_id, phase, model, cost_usd, source, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def monthly_total_usd(self, month: str | None = None) -> float:
        target = month or period_of()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger WHERE period_month=?",
            (target,)).fetchone()
        return float(row["total"])

    def total_for_case_usd(self, case_id: int) -> float:
        """Coût LLM cumulé d'un cas **sur toute sa vie** — TÉLÉMÉTRIE DE DEBUG, PAS le §9.

        ⚠️ **NE JAMAIS COMPARER CE CHIFFRE AU SEUIL DU §9** (arbitrage du porteur, 2026-07-17).
        Le §9 du brief dit : *« Coût — nouveau cas de test (génération + exécution + rapport) :
        < 1 € »*. Il mesure une **CRÉATION**, une fois. Cette méthode répond à une **autre**
        question : « combien ce cas a-t-il coûté **depuis toujours** », réparations et sessions de
        débogage comprises.

        **Les confondre alarme à tort.** Mesuré : le cas 1 affiche **$1,1552 = 107 % du §9** — et
        ce n'est **pas** un dépassement du brief : il cumule 5 sessions de débogage de l'outil et
        7 versions. Une **création réelle** mesurée le 2026-07-17 (chemin écran) vaut **$0,1207 =
        11 % du §9**. C'est **ça**, le §9, et il est tenu très largement.

        → Pour juger le §9 : **le coût de la création** (phases `analysis` + `generation` du
        premier passage). Pour comprendre où part l'argent d'un cas qu'on débogue : cette
        méthode-ci.

        ✅ **UN usage légitime de ce cumul comme SEUIL** (ajouté le 2026-07-19) : amorcer le
        GARDE-FOU de dépense de la boucle de réparation. Là, borner « génération + toutes les
        réparations » au §9 est une **enveloppe de sécurité** (empêcher un cas d'emballer la
        dépense), PAS le KPI §9. La distinction tient : le KPI juge une création, le garde-fou
        borne un cumul. Ne pas confondre les deux — l'un mesure, l'autre coupe.

        --- Pourquoi elle existe quand même ---

        Le ledger n'était alimenté que par la CLI (`cli.py`) ; tout ce qui passait par l'API —
        donc par l'écran, donc par la boucle de réparation — coûtait de l'argent sans laisser de
        trace (`run_service._persist` écrivait `cost_usd=0.0` en dur).

        On somme par le ledger et non par `execution.cost_usd` : le ledger porte la phase et le
        modèle, donc il explique le total au lieu de l'asséner.

        ⚠️ **On lit `c.test_case_id`, plus `JOIN execution`** (migration 12). L'ancienne jointure
        rendait le total **structurellement aveugle** au coût de génération du chemin API : cette
        dépense n'a aucune exécution où s'accrocher, donc la jointure l'excluait. Le §9 se mesurait
        sur un total amputé de son poste le plus lourd, sans que rien ne le signale.
        """
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger WHERE test_case_id = ?",
            (case_id,)).fetchone()
        return float(row["total"])

    def creation_cost_usd(self, case_id: int) -> float:
        """Coût de la CRÉATION d'un cas — **c'est CELUI-CI qui se compare au §9**.

        Le §9 du brief : *« Coût — nouveau cas de test (génération + exécution + rapport) : < 1 € »*.
        Donc : l'**analyse** de la spec + la **génération**. Les réparations ultérieures et les
        sessions de débogage sont du coût d'**exploitation** — réel, à suivre
        (`total_for_case_usd`), mais **hors** de ce seuil (arbitrage du porteur, 2026-07-17).

        Mesuré le 2026-07-17 sur le chemin écran : **$0,1207 = 11 % du §9**.

        On somme les phases de création, pas « tout sauf les réparations » : si une phase
        s'ajoutait un jour (un `report` payant, par exemple), la nommer serait une décision, pas
        un effet de bord d'une négation.
        """
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger"
            " WHERE test_case_id = ? AND phase IN ('analysis', 'generation')",
            (case_id,)).fetchone()
        return float(row["total"])

    # Phases de RUN (exécution). Aujourd'hui la seule dépense LLM d'un run est la réparation : le
    # run lui-même (Behave/Playwright/odoorpc) et le diagnostic (déterministe) ne coûtent rien.
    # ⚠️ Nommées POSITIVEMENT, comme `creation_cost_usd` : si un jour un run engage un autre appel
    # LLM (un re-diagnostic payant, par ex.), l'ajouter ICI est une DÉCISION, pas l'effet de bord
    # d'un « tout sauf la création ».
    _RUN_PHASES = ("repair",)

    def run_cost_usd(self, case_id: int) -> float:
        """Coût LLM des RUNS d'un cas — **suivi, SANS seuil cible** (arbitrage du porteur,
        2026-07-19 : mesurer d'abord, calibrer plus tard, jamais un seuil sans données).

        Distinct de `creation_cost_usd` (le §9) et de `total_for_case_usd` (tout). Ce qu'un cas a
        coûté à être RE-joué : la somme des réparations. `0` pour un cas jamais réparé — c'est un
        fait, pas un trou. Se lit au ledger (la seule trace réelle), par `test_case_id`.
        """
        marqueurs = ",".join("?" * len(self._RUN_PHASES))
        row = self.conn.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger"
            f" WHERE test_case_id = ? AND phase IN ({marqueurs})",
            (case_id, *self._RUN_PHASES)).fetchone()
        return float(row["total"])

    def run_cost_for_execution_usd(self, execution_id: int) -> float:
        """Coût LLM attribué à UN run précis (l'exécution qui a provoqué la réparation). Permet de
        lire le coût run par run, pas seulement cumulé par cas — utile pour la future calibration."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger WHERE execution_id = ?",
            (execution_id,)).fetchone()
        return float(row["total"])

    def breakdown_for_case(self, case_id: int) -> list[dict]:
        """Détail par phase/modèle — ce qui a coûté, pas seulement combien."""
        return _rows(self.conn.execute(
            "SELECT phase, model, COUNT(*) AS calls, SUM(cost_usd) AS cost_usd"
            " FROM cost_ledger WHERE test_case_id = ?"
            " GROUP BY phase, model ORDER BY cost_usd DESC",
            (case_id,)))


class ResultRepo:
    """Le REGISTRE des résultats — la seule réponse à « quel est le résultat du cas C dans la
    campagne R ? » (2026-08-04).

    ⚠️ **Deux MODES D'EXÉCUTION, une seule table, et la base qui les tient séparés.** Un résultat
    `automatique` porte une exécution et aucun statut saisi ; un résultat `manuelle` porte un
    statut saisi et aucune exécution. Ce n'est pas une convention que ce dépôt s'engage à
    respecter : c'est un `CHECK` de la table, donc un refus d'insertion. C'est là que vit la
    promesse du produit — *on sait toujours comment un statut a été obtenu*.

    Et un trigger y ajoute la règle née du mode au niveau campagne : un résultat ne peut pas être
    d'un autre mode que la campagne qui l'accueille.

    **Rien n'est jamais modifié ni supprimé** : corriger un résultat, c'est en ajouter un nouveau.
    L'historique reste lisible, y compris les erreurs de saisie — comme partout ici (§7).
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def enregistrer_execution(self, execution_id: int, *, created_by: str = "",
                              comment: str = "") -> int | None:
        """Inscrit au registre l'exécution qui vient de se clore. Rend `None` si elle n'a pas sa
        place (hors campagne, ou déjà inscrite).

        ⚠️ **Une exécution SANS `run_id` n'entre pas au registre** — et ce n'est pas un oubli : le
        registre répond à « résultat du cas C **dans la campagne R** ». Sans campagne, la question
        n'existe pas ; la ligne vivrait dans `execution`, comme avant. C'est aussi ce qui garde
        `quality_summary` (qui compte les `execution`) intact.

        `created_by` et `comment` sont **recopiés à l'écriture**, jamais résolus/modifiés à la
        lecture : changer le compte de service plus tard, ou reformuler un commentaire après
        coup, ne doit pas réécrire l'histoire (§7 : rien n'est jamais modifié ni supprimé).
        `comment` (§A, 2026-08-06) : l'explication en français clair du verdict — générée par
        l'appelant AVANT cet appel (`run_service._persist`), jamais ici.
        """
        ex = self.conn.execute(
            "SELECT id, run_id, test_case_id FROM execution WHERE id=?", (execution_id,)).fetchone()
        if ex is None or ex["run_id"] is None:
            return None
        deja = self.conn.execute(
            "SELECT id FROM test_result WHERE execution_id=?", (execution_id,)).fetchone()
        if deja is not None:
            return int(deja["id"])   # `finalize` peut être rejoué : on ne compte pas deux fois
        cur = self.conn.execute(
            "INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
            " comment, created_by, attachments_path, created_at)"
            " VALUES (?,?,?, ?, '', ?, ?, '', ?)",
            (ex["run_id"], ex["test_case_id"], MODE_AUTOMATIQUE, execution_id, comment,
             created_by, now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

    def saisir(self, *, run_id: int, case_id: int, statut: str, comment: str = "",
               created_by: str = "", attachments_path: str = "") -> int:
        """Inscrit un résultat joué À LA MAIN par un humain, et met à jour le raccourci du cas.

        Le statut est vérifié ici **et** par la base : la liste vient de `STATUTS_MANUELS`, et le
        `CHECK` de la table refuse tout ce qui n'y est pas. Deux gardes pour la même règle, parce
        que celle-ci porte la promesse du produit — un message clair côté Python, un refus
        infranchissable côté base.
        """
        from testpilot.verdict.status import STATUTS_MANUELS

        if statut not in STATUTS_MANUELS:
            raise ValueError(
                f"statut non saisissable : {statut!r} — attendu {list(STATUTS_MANUELS)}. "
                "« untested » n'en fait PAS partie : c'est l'absence de résultat, pas un choix.")
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
            " comment, created_by, attachments_path, created_at)"
            " VALUES (?,?,?, NULL, ?,?,?,?,?)",
            (run_id, case_id, MODE_MANUELLE, statut, comment, created_by, attachments_path, ts))
        self.conn.commit()
        CaseRepo(self.conn).update_last_manuel(case_id, statut=statut, saisi_at=ts)
        return int(cur.lastrowid)

    # Les DEUX AXES ne sont pas recopiés dans le registre : ils se lisent par JOINTURE sur
    # l'exécution. Une copie divergerait le jour où une exécution est corrigée — et surtout,
    # un axe recopié sur une ligne MANUELLE serait une mesure inventée. Sur un résultat manuel,
    # la jointure ne rend rien, et c'est exactement ce qu'on veut afficher : rien.
    _SELECT_RESULTAT = (
        "SELECT tr.*, e.execution_status, e.functional_status, e.started_at AS execution_started_at"
        " FROM test_result tr LEFT JOIN execution e ON e.id = tr.execution_id")

    def dernier(self, run_id: int, case_id: int) -> dict | None:
        """Le résultat qui FAIT FOI pour ce cas dans cette campagne : le dernier inscrit.

        Trié par `id`, jamais par `created_at` : deux résultats saisis dans la même seconde
        auraient la même date, et l'ordre deviendrait celui que la base voudrait bien rendre.
        """
        row = self.conn.execute(
            f"{self._SELECT_RESULTAT} WHERE tr.run_id=? AND tr.case_id=?"
            " ORDER BY tr.id DESC LIMIT 1", (run_id, case_id)).fetchone()
        return dict(row) if row else None

    def historique(self, run_id: int, case_id: int) -> list[dict]:
        """Tous les résultats de ce cas dans cette campagne, du plus ancien au plus récent.

        Corriger un résultat, c'est en ajouter un autre : l'ancien reste, et c'est cette liste qui
        le montre. Sans elle, « corriger » redeviendrait « effacer ».
        """
        return _rows(self.conn.execute(
            f"{self._SELECT_RESULTAT} WHERE tr.run_id=? AND tr.case_id=? ORDER BY tr.id",
            (run_id, case_id)))

    def get(self, result_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM test_result WHERE id=?", (result_id,)).fetchone()
        return dict(row) if row else None

    # ── Les PIÈCES JOINTES d'un résultat (2026-08-05) ────────────────────────
    # ⚠️ **`stored_name` (le nom sur le disque) est distinct de `filename` (celui de
    # l'utilisateur)** : c'est le serveur qui génère le premier, et c'est LUI seul qui touche un
    # chemin. Le nom venu du client n'est qu'une étiquette d'affichage — il ne désigne jamais un
    # fichier. Sans cette séparation, un `filename` du genre `../../.env` deviendrait un chemin.
    #
    # `attachments_path` est STOCKÉ sur le résultat, jamais déduit de son identifiant : le
    # répertoire de données est configurable, et une base restaurée ailleurs doit continuer de
    # dire où ses fichiers sont partis.

    def ajouter_piece_jointe(self, result_id: int, *, filename: str, stored_name: str,
                             dossier: str, content_type: str = "", size_bytes: int = 0) -> int:
        """Inscrit une pièce jointe et mémorise le dossier qui l'accueille.

        ⚠️ Écrire `attachments_path` n'entame PAS la règle « rien n'est modifié » de ce registre :
        cette colonne dit *où sont rangés les fichiers*, pas ce que le résultat affirme. Le
        statut, le commentaire et l'auteur, eux, restent intouchables.
        """
        cur = self.conn.execute(
            "INSERT INTO result_attachment (result_id, filename, stored_name, content_type,"
            " size_bytes, created_at) VALUES (?,?,?,?,?,?)",
            (result_id, filename, stored_name, content_type, size_bytes, now_iso()))
        self.conn.execute("UPDATE test_result SET attachments_path=? WHERE id=?",
                          (dossier, result_id))
        self.conn.commit()
        return int(cur.lastrowid)

    def pieces_jointes(self, result_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM result_attachment WHERE result_id=? ORDER BY id", (result_id,)))

    def pieces_jointes_de(self, result_ids: list[int]) -> dict[int, list[dict]]:
        """Les pièces jointes de PLUSIEURS résultats en **une** requête.

        L'historique d'un cas en affiche N : une requête par ligne rendrait le coût de l'écran
        proportionnel au nombre de corrections, pour une colonne le plus souvent vide.
        """
        if not result_ids:
            return {}
        marqueurs = ",".join("?" * len(result_ids))
        par_resultat: dict[int, list[dict]] = {}
        for row in _rows(self.conn.execute(
                f"SELECT * FROM result_attachment WHERE result_id IN ({marqueurs}) ORDER BY id",
                tuple(result_ids))):
            par_resultat.setdefault(int(row["result_id"]), []).append(row)
        return par_resultat

    def piece_jointe(self, result_id: int, attachment_id: int) -> dict | None:
        """UNE pièce jointe, **à condition qu'elle appartienne à ce résultat**.

        ⚠️ Le `result_id` dans la clause n'est pas décoratif : sans lui, l'identifiant numérique
        d'une pièce jointe suffirait à lire celle d'un AUTRE résultat en passant par n'importe
        quelle URL. Le dossier est rendu avec elle — le nom sur disque ne se recolle qu'à un
        chemin lu en base, jamais à une chaîne venue du client.
        """
        row = self.conn.execute(
            "SELECT a.*, r.attachments_path FROM result_attachment a"
            " JOIN test_result r ON r.id = a.result_id"
            " WHERE a.id=? AND a.result_id=?", (attachment_id, result_id)).fetchone()
        return dict(row) if row else None

    def supprimer_piece_jointe(self, result_id: int, attachment_id: int) -> None:
        """Retire uniquement la pièce demandée, jamais le résultat ni son historique."""
        cur = self.conn.execute(
            "DELETE FROM result_attachment WHERE id=? AND result_id=?",
            (attachment_id, result_id))
        if cur.rowcount == 0:
            raise ValueError("pièce jointe introuvable")
        self.conn.commit()

    def derniers_du_run(self, run_id: int) -> dict[int, dict]:
        """Le dernier résultat de CHAQUE cas de la campagne, en **une** requête.

        ⚠️ Une requête, pas une par cas : l'écran d'une campagne de 500 cas ferait sinon 500
        allers-retours pour afficher une colonne. Le `MAX(id)` par cas est calculé en sous-requête,
        puis joint — c'est la forme qui reste juste quand deux résultats partagent leur horodatage.
        """
        return {int(r["case_id"]): dict(r) for r in self.conn.execute(
            f"{self._SELECT_RESULTAT}"
            " JOIN (SELECT case_id, MAX(id) AS dernier FROM test_result WHERE run_id=?"
            "       GROUP BY case_id) d ON d.dernier = tr.id"
            " WHERE tr.run_id=?", (run_id, run_id))}

    def historique_du_cas(self, case_id: int, limite: int = 200) -> list[dict]:
        """Tous les résultats de ce cas, **toutes campagnes confondues**, du plus récent au plus
        ancien — avec le nom de la campagne qui les a produits.

        ⚠️ C'est la question que `dernier`/`historique` ne savaient pas poser : elles répondent
        « dans CETTE campagne ». Ici on demande « et ailleurs ? » — ce qui permet de voir qu'un cas
        passe partout sauf sur une recette, information invisible campagne par campagne.

        Une campagne dont le PROJET est à la corbeille n'y figure pas : elle n'existe plus pour
        l'écran, et son résultat ne doit pas ressusciter dans l'historique d'un cas vivant.
        """
        return _rows(self.conn.execute(
            "SELECT tr.*, e.execution_status, e.functional_status, r.name AS run_name"
            " FROM test_result tr LEFT JOIN execution e ON e.id = tr.execution_id"
            " JOIN test_run r ON r.id = tr.run_id"
            " JOIN project p ON p.id = r.project_id"
            " WHERE tr.case_id=? AND p.deleted_at='' ORDER BY tr.id DESC LIMIT ?",
            (case_id, limite)))

    def activite_du_run(self, run_id: int, limite: int = 500) -> list[dict]:
        """Le fil chronologique d'une campagne : chaque résultat posé, du plus récent au plus
        ancien, avec le titre du cas concerné.

        ⚠️ Un cas à la CORBEILLE n'apparaît pas : il ne fait plus partie d'aucune campagne
        (même invariant que `RunRepo.case_ids`). Sans ce filtre, le fil d'activité serait la
        seule vue de l'application où un cas supprimé continuerait de vivre.
        """
        return _rows(self.conn.execute(
            "SELECT tr.*, e.execution_status, e.functional_status, tc.title AS case_title"
            " FROM test_result tr LEFT JOIN execution e ON e.id = tr.execution_id"
            " JOIN test_case tc ON tc.id = tr.case_id"
            " WHERE tr.run_id=? AND tc.deleted_at='' ORDER BY tr.id DESC LIMIT ?",
            (run_id, limite)))


class SettingRepo:
    """Les RÉGLAGES D'INSTANCE — une table clé/valeur, mais à vocabulaire FERMÉ.

    ⚠️ **`CLES_CONNUES` n'est pas de la bureaucratie.** Une table clé/valeur ouverte devient un
    dépotoir en six mois : plus personne ne sait quelles clés sont lues, lesquelles sont mortes,
    ni laquelle un écran attend. Refuser une clé inconnue à l'écriture est ce qui rend la table
    lisible dans un an — même discipline que `erreurs.CATALOGUE`, pour la même raison.

    **La résolution est en trois temps : base → variable d'environnement → défaut du code.** Et
    l'API expose **d'où vient la valeur** (`resoudre` rend le couple valeur/provenance) : sans
    ça, un exploitant qui a posé sa variable d'environnement et qui voit autre chose à l'écran
    cherche pendant une heure — la base l'emporte, mais rien ne le lui dit.
    """

    # clé → (valeur par défaut lue dans `config`, description affichée, réservé à l'Admin,
    #         SECRET — 2026-08-12, voir plus bas)
    # ⚠️ `admin_only` (2026-08-11) gouverne seulement l'ÉCRITURE (`routes/settings.py` l'applique) —
    # la lecture reste ouverte à tous, SAUF pour un réglage `secret` (ci-dessous), masqué pour tout
    # le monde y compris l'Admin : la lecture n'a jamais besoin de le REVOIR en clair, seul le
    # serveur en a besoin pour se connecter.
    # ⚠️ `service_account_name` a été RETIRÉ d'ici le 2026-08-12, sur demande explicite du
    # porteur : ce n'était pas censé être un réglage modifiable depuis l'écran (le nom qui signe
    # une exécution automatique n'a plus grand-chose à décider depuis la traçabilité de
    # `triggered_by` — migration 32). Il reste réglable au déploiement par la variable
    # d'environnement `TESTPILOT_SERVICE_ACCOUNT` (`config.SERVICE_ACCOUNT_NAME`), lue
    # directement — plus via cette table, plus via l'écran Réglages.
    FUSEAUX_HORAIRES: tuple[tuple[str, str], ...] = (
        ("Europe/Paris", "Paris"),
        ("Africa/Dakar", "Sénégal"),
    )

    CLES_CONNUES: dict[str, tuple[str, str, bool, bool]] = {
        "reference_url_template": (
            "REFERENCE_URL_TEMPLATE",
            "Gabarit d'URL pour transformer une référence (« JIRA-123 ») en lien cliquable — "
            "« {ref} » est remplacé par la référence exacte. Vide = les références restent du "
            "texte brut, partout. Réservé à l'Admin : un gabarit mal réglé change ce que voit "
            "TOUTE l'équipe, sur tous les projets.",
            True,
            False,
        ),
        "instance_name": (
            "INSTANCE_NAME",
            "Nom affiché pour identifier cette installation de TestPilot.",
            True,
            False,
        ),
        "instance_timezone": (
            "INSTANCE_TIMEZONE",
            "Fuseau horaire IANA utilisé pour afficher les dates de l'instance.",
            True,
            False,
        ),
        "date_format": (
            "DATE_FORMAT",
            "Format utilisé pour afficher les dates dans l'interface.",
            True,
            False,
        ),
        "notifications_enabled": (
            "NOTIFICATIONS_ENABLED",
            "Envoyer un email à l'auteur d'une campagne ou d'une automatisation quand elle se "
            "termine. « 1 » = activé, vide/« 0 » = désactivé (défaut — jamais d'envoi surprise).",
            True,
            False,
        ),
        "smtp_host": (
            "SMTP_HOST",
            "Serveur SMTP utilisé pour les notifications par email.",
            True,
            False,
        ),
        "smtp_port": (
            "SMTP_PORT",
            "Port du serveur SMTP (587 = STARTTLS, le plus courant).",
            True,
            False,
        ),
        "smtp_username": (
            "SMTP_USERNAME",
            "Compte utilisé pour s'authentifier auprès du serveur SMTP. Vide = pas "
            "d'authentification (relais interne ouvert).",
            True,
            False,
        ),
        "smtp_password": (
            "SMTP_PASSWORD",
            "Mot de passe du compte SMTP. Jamais relu en clair une fois enregistré — laisser "
            "vide pour le conserver, l'effacer explicitement pour le retirer.",
            True,
            True,
        ),
        "smtp_from": (
            "SMTP_FROM",
            "Adresse d'expéditeur des emails de notification.",
            True,
            False,
        ),
        "smtp_use_tls": (
            "SMTP_USE_TLS",
            "Chiffrer la connexion au serveur SMTP (STARTTLS). « 1 » = activé, vide/« 0 » = "
            "désactivé.",
            True,
            False,
        ),
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _verifier(self, cle: str) -> None:
        if cle not in self.CLES_CONNUES:
            raise ValueError(
                f"réglage inconnu : {cle!r} — ajoutez-le à SettingRepo.CLES_CONNUES")

    # Le masque renvoyé pour un réglage secret DÉJÀ posé — jamais la valeur réelle. Reconnu à
    # l'écriture (`ecrire`) pour refuser de l'enregistrer telle quelle si jamais elle revenait
    # (un écran qui préremplirait son champ avec la valeur affichée écraserait le vrai secret par
    # ce masque littéral — ce n'est PAS censé arriver côté frontend, ce garde est un filet).
    MASQUE_SECRET = "••••••••"

    def resoudre(self, cle: str) -> tuple[str, str]:
        """Rend `(valeur, provenance)` où provenance ∈ {`db`, `env`, `default`} — la valeur
        RÉELLE, en clair, déchiffrée si besoin. Réservé à un usage INTERNE (le serveur ouvrant
        lui-même une connexion) : jamais renvoyée telle quelle par l'API, voir `tous()`.

        La PROVENANCE est rendue avec la valeur, et pas seulement la valeur : c'est elle qui
        permet à l'écran d'expliquer pourquoi la variable d'environnement de l'exploitant n'est
        pas celle qui s'applique.
        """
        self._verifier(cle)
        _, _, _, secret = self.CLES_CONNUES[cle]
        row = self.conn.execute("SELECT value FROM app_setting WHERE key=?", (cle,)).fetchone()
        if row is not None and str(row["value"]).strip():
            valeur = str(row["value"])
            if secret:
                from testpilot.store import secrets as _secrets
                valeur = _secrets.dechiffrer(valeur)
            return valeur, "db"
        attribut, _, _, _ = self.CLES_CONNUES[cle]
        defaut = str(getattr(config, attribut, "") or "")
        # `config` a déjà lu l'environnement (aucun `os.getenv` hors de lui) : on compare donc à
        # la valeur d'usine pour savoir si l'exploitant a posé une variable, ou pas.
        usine = _DEFAUTS_USINE.get(attribut, "")
        return defaut, ("env" if defaut != usine else "default")

    def valeur(self, cle: str) -> str:
        return self.resoudre(cle)[0]

    def ecrire(self, cle: str, valeur: str, *, par: str = "") -> None:
        """Pose (ou efface) un réglage. Une valeur VIDE supprime la ligne plutôt que d'écrire une
        chaîne vide : « pas de réglage » et « réglé à rien » ne sont pas le même fait, et seul le
        premier doit laisser reprendre la main à l'environnement.

        Un réglage `secret` est CHIFFRÉ avant d'être écrit (`store/secrets.py`, même mécanisme
        que le mot de passe de connexion d'un projet) — la base ne porte jamais un secret en
        clair."""
        self._verifier(cle)
        _, _, _, secret = self.CLES_CONNUES[cle]
        valeur = str(valeur or "").strip()
        if cle == "instance_name" and valeur and not 2 <= len(valeur) <= 80:
            raise ValueError("le nom de l'instance doit contenir entre 2 et 80 caractères")
        if cle == "instance_timezone" and valeur:
            if valeur not in {identifiant for identifiant, _ in self.FUSEAUX_HORAIRES}:
                raise ValueError("fuseau horaire IANA inconnu")
        if cle == "date_format" and valeur and valeur not in {"DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"}:
            raise ValueError("format de date inconnu")
        if secret and valeur == self.MASQUE_SECRET:
            return  # le masque affiché n'est jamais une vraie valeur — no-op de sécurité
        if not valeur:
            self.conn.execute("DELETE FROM app_setting WHERE key=?", (cle,))
        else:
            if secret:
                from testpilot.store import secrets as _secrets
                valeur = _secrets.chiffrer(valeur)
            self.conn.execute(
                "INSERT INTO app_setting (key, value, updated_at, updated_by) VALUES (?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                " updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (cle, valeur, now_iso(), par))
        self.conn.commit()

    def tous(self) -> list[dict]:
        """Tous les réglages CONNUS, résolus — y compris ceux qu'aucune ligne ne porte.

        ⚠️ Un réglage `secret` n'est JAMAIS rendu en clair ici — c'est la vue qu'expose l'API
        (`GET /api/settings`). `MASQUE_SECRET` si une valeur est posée, `""` sinon : ni l'un ni
        l'autre ne permet de reconstituer le mot de passe."""
        out = []
        for cle in self.CLES_CONNUES:
            v, src = self.resoudre(cle)
            secret = self.CLES_CONNUES[cle][3]
            valeur_rendue = (self.MASQUE_SECRET if v else "") if secret else v
            out.append({"key": cle, "value": valeur_rendue, "source": src,
                       "description": self.CLES_CONNUES[cle][1],
                       "admin_only": self.CLES_CONNUES[cle][2], "secret": secret})
        return out


# Les valeurs d'USINE, figées ici, servent UNIQUEMENT à distinguer « l'exploitant a posé une
# variable d'environnement » de « personne n'a rien réglé ». Elles doivent rester identiques aux
# défauts de `config.py` — un test les compare, sinon l'écran annoncerait « env » à tout le monde.
_DEFAUTS_USINE = {
    "REFERENCE_URL_TEMPLATE": "",
    "INSTANCE_NAME": "TestPilot",
    "INSTANCE_TIMEZONE": "Europe/Paris",
    "DATE_FORMAT": "DD/MM/YYYY",
    "NOTIFICATIONS_ENABLED": "",
    "SMTP_HOST": "",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_FROM": "",
    "SMTP_USE_TLS": "1",
}


class GenerationJobRepo:
    """Le job de génération (multi-cas ou automatisation d'un cas manuel) — PERSISTÉ, pas
    seulement en mémoire (migration 29, 2026-08-07, suite à un incident réel : un job en mémoire
    disparaît d'un coup si le serveur redémarre pendant une génération, longue — plusieurs
    minutes de dry-run réel — sans que l'écran ne puisse jamais dire à l'utilisateur pourquoi il
    reste bloqué. Vécu le 07/08, pris pour un simple « timeout »).

    ⚠️ **Colonnes explicites pour ce qu'on filtre/affiche souvent** (`status`, `error`,
    `case_ids`, `module_id`, `cost_usd`) ; **le reste en JSON dans `payload`** — un job est un
    état de TRAVAIL EN COURS, pas une donnée métier durable, et cette table ne devrait pas
    s'élargir à chaque nouveau type de tâche de fond (génération multi-cas : Section ciblée,
    spécification, cas en attente de validation ; automatisation : cas visé, slug, métier).
    """

    # Un job "running" sans la moindre mise à jour depuis ce délai est réputé MORT — le serveur
    # qui le faisait avancer a très probablement redémarré pendant qu'il tournait. La génération
    # dit elle-même « quelques minutes » : un multiple large, pour ne jamais couper un job encore
    # réellement vivant sur une spécification à beaucoup de cas.
    SEUIL_BLOQUE_SECONDES = 900

    _COLONNES_DIRECTES = {"status", "error", "case_ids", "cost_usd"}

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def creer(self, job_id: str, *, module_id: int, payload: dict | None = None) -> None:
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO generation_job (id, status, error, case_ids, module_id, payload,"
            " cost_usd, created_at, updated_at) VALUES (?, 'running', '', '[]', ?, ?, 0.0, ?, ?)",
            (job_id, module_id, json.dumps(payload or {}, ensure_ascii=False), ts, ts))
        self.conn.commit()

    def get(self, job_id: str) -> dict | None:
        """Rend le job, à PLAT (colonnes explicites + `payload` fusionnés au même niveau — les
        colonnes explicites l'emportent en cas de collision, ce qui ne devrait jamais arriver).

        ⚠️ **Repli sur PANNE, écrit ici et pas seulement renvoyé une fois** : un job "running"
        resté sans nouvelle trop longtemps est réputé mort. On l'écrit tout de suite (pas
        seulement au lecteur qui tombe dessus le premier), pour que TOUT lecteur futur voie la
        même vérité — le seul choke point de cette règle, comme `ExecutionRepo.finalize` l'est
        pour le registre.
        """
        row = self.conn.execute("SELECT * FROM generation_job WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        payload = json.loads(d.pop("payload") or "{}")
        d["case_ids"] = json.loads(d["case_ids"])
        d = {**payload, **d}
        if d["status"] == "running":
            maj = _depuis_iso(d["updated_at"])
            if maj is not None and (datetime.now(timezone.utc) - maj) > timedelta(
                    seconds=self.SEUIL_BLOQUE_SECONDES):
                self.maj(job_id, status="failed",
                        error="la génération semble interrompue — le serveur a peut-être "
                              "redémarré pendant qu'elle tournait. Relancez-la.")
                return self.get(job_id)
        return d

    def maj(self, job_id: str, **champs) -> None:
        """Met à jour un job — même ergonomie que l'ancien `_JOBS[job_id].update(**champs)`,
        pour ne pas réécrire toute la logique de `generation_service` : les clés connues
        (`status`/`error`/`case_ids`/`cost_usd`) vont dans leur colonne, tout le reste rejoint
        `payload`."""
        row = self.conn.execute("SELECT payload FROM generation_job WHERE id=?",
                                (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"job {job_id} introuvable")
        payload = json.loads(row["payload"] or "{}")
        directes = {k: v for k, v in champs.items() if k in self._COLONNES_DIRECTES}
        payload.update({k: v for k, v in champs.items() if k not in self._COLONNES_DIRECTES})

        sets = ["updated_at=?", "payload=?"]
        valeurs: list = [now_iso(), json.dumps(payload, ensure_ascii=False)]
        for col in ("status", "error", "cost_usd"):
            if col in directes:
                sets.append(f"{col}=?")
                valeurs.append(directes[col])
        if "case_ids" in directes:
            sets.append("case_ids=?")
            valeurs.append(json.dumps(directes["case_ids"]))
        valeurs.append(job_id)
        self.conn.execute(f"UPDATE generation_job SET {', '.join(sets)} WHERE id=?", valeurs)
        self.conn.commit()


class BackgroundJobRepo:
    """Journal durable des tâches acceptées avant leur exécution hors requête HTTP."""

    def __init__(self, conn):
        self.conn = conn

    def creer(self, job_id: str, *, kind: str, queue_label: str, payload: dict) -> None:
        contenu = secrets_mod.chiffrer(json.dumps(payload, ensure_ascii=False))
        self.conn.execute(
            "INSERT INTO background_job (id, kind, queue_label, payload, status, created_at)"
            " VALUES (?,?,?,?, 'queued', ?)",
            (job_id, kind, queue_label, contenu, now_iso()),
        )
        self.conn.commit()

    def get(self, job_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM background_job WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        resultat = dict(row)
        resultat["payload"] = self._payload(resultat["payload"])
        return resultat

    def claim(self, job_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE background_job SET status='running', started_at=?, error=''"
            " WHERE id=? AND status='queued'",
            (now_iso(), job_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def terminer(self, job_id: str, *, erreur: str = "") -> None:
        self.conn.execute(
            "UPDATE background_job SET status=?, error=?, finished_at=? WHERE id=?",
            ("failed" if erreur else "completed", erreur[:1000], now_iso(), job_id),
        )
        self.conn.commit()

    def queued_ids(self) -> list[str]:
        return [r["id"] for r in self.conn.execute(
            "SELECT id FROM background_job WHERE status='queued' ORDER BY created_at, id")]

    def interrompus(self) -> list[dict]:
        rows = _rows(self.conn.execute(
            "SELECT * FROM background_job WHERE status='running' ORDER BY created_at, id"))
        if rows:
            self.conn.execute(
                "UPDATE background_job SET status='failed', error=?, finished_at=?"
                " WHERE status='running'",
                ("traitement interrompu par un arrêt du serveur; relance manuelle nécessaire",
                 now_iso()),
            )
            self.conn.commit()
        for row in rows:
            row["payload"] = self._payload(row.get("payload"))
        return rows

    def purger_termines(self, avant_iso: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM background_job WHERE status IN ('completed','failed')"
            " AND finished_at<>'' AND finished_at<?",
            (avant_iso,),
        )
        self.conn.commit()
        return cur.rowcount

    @staticmethod
    def _payload(valeur: str | None) -> dict:
        contenu = secrets_mod.dechiffrer(valeur)
        try:
            resultat = json.loads(contenu or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("payload de tâche durable illisible") from exc
        if not isinstance(resultat, dict):
            raise RuntimeError("payload de tâche durable invalide")
        return resultat


def _depuis_iso(valeur: str) -> datetime | None:
    """Parse un horodatage écrit par `now_iso()` — tolérant : une valeur illisible ne doit
    jamais faire planter la détection de blocage, seulement la désactiver pour cette ligne."""
    try:
        return datetime.fromisoformat(valeur)
    except (TypeError, ValueError):
        return None


class UserRepo:
    """Comptes utilisateurs (migration 30, 2026-08-07) — remplace le mot de passe unique partagé
    du lot 2. `password_hash` est déjà haché à l'appel (`api/access.py::hacher_mot_de_passe`) :
    ce repo ne hache ni ne vérifie rien, il n'écrit et ne lit que ce qu'on lui donne, comme
    `store/secrets.py` ne fait que chiffrer/déchiffrer sans connaître la politique d'accès.

    Jamais de suppression définitive d'un compte — seulement `is_active` : désactiver un compte
    ne doit jamais effacer l'auteur des cas/résultats qu'il a signés (`created_by`/`deleted_by`
    restent du texte libre, indépendant de cette table)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, username: str, password_hash: str, role: str, email: str = "",
               must_change_password: bool = False) -> int:
        username = (username or "").strip()
        if not username:
            raise ValueError("le nom d'utilisateur est obligatoire")
        if self.conn.execute("SELECT 1 FROM user WHERE username=?", (username,)).fetchone():
            raise DuplicateName(f"le nom d'utilisateur « {username} » est déjà pris")
        cur = self.conn.execute(
            "INSERT INTO user (username, password_hash, role, email, is_active, created_at)"
            " VALUES (?,?,?,?,1,?)", (username, password_hash, role, (email or "").strip(),
                                      now_iso()))
        self.conn.commit()
        user_id = int(cur.lastrowid)
        if must_change_password:
            self.set_password_hash(user_id, password_hash, temporary=True)
        ProjectMemberRepo(self.conn).sync_user(user_id)
        return user_id

    def get(self, user_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_by_username(self, username: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM user WHERE username=?",
                                (username,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        return _rows(self.conn.execute("SELECT * FROM user ORDER BY username"))

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM user").fetchone()["n"])

    def set_role(self, user_id: int, role: str) -> None:
        self.conn.execute(
            "UPDATE user SET role=?, session_version=session_version+1 WHERE id=?",
            (role, user_id))
        self.conn.commit()
        ProjectMemberRepo(self.conn).sync_user(user_id)

    def set_active(self, user_id: int, is_active: bool) -> None:
        """⚠️ Prend effet IMMÉDIATEMENT (`api/access.py::utilisateur_actuel` relit ce champ à
        CHAQUE requête, jamais depuis le jeton) — désactiver quelqu'un doit couper l'accès tout
        de suite, pas attendre l'expiration naturelle de sa session."""
        self.conn.execute("UPDATE user SET is_active=?, session_version=session_version+1 WHERE id=?",
                          (1 if is_active else 0, user_id))
        self.conn.commit()
        ProjectMemberRepo(self.conn).sync_user(user_id)

    def set_password_hash(self, user_id: int, password_hash: str, *, temporary: bool = False) -> int:
        """Réinitialisation par un Admin (2026-08-11) — pour un compte qui a oublié le sien."""
        import time
        from testpilot import config
        expiry = int(time.time()) + config.TEMPORARY_PASSWORD_HOURS * 3600 if temporary else 0
        self.conn.execute(
            "UPDATE user SET password_hash=?, session_version=session_version+1, "
            "must_change_password=?, password_expires_at=? WHERE id=?",
            (password_hash, int(temporary), expiry, user_id))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT session_version FROM user WHERE id=?", (user_id,)).fetchone()
        return int(row["session_version"]) if row else 0

    def revoke_sessions(self, user_id: int) -> int:
        """Invalide tous les jetons déjà émis pour ce compte et rend la nouvelle version."""
        self.conn.execute(
            "UPDATE user SET session_version=session_version+1 WHERE id=?", (user_id,))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT session_version FROM user WHERE id=?", (user_id,)).fetchone()
        return int(row["session_version"]) if row else 0

    def change_own_password(self, user: dict, password_hash: str) -> int | None:
        """Compare-and-swap : un reset ou une révocation concurrente ne peut être écrasé."""
        cur = self.conn.execute(
            "UPDATE user SET password_hash=?, session_version=session_version+1, "
            "must_change_password=0, password_expires_at=0 "
            "WHERE id=? AND session_version=? AND password_hash=? AND is_active=1",
            (password_hash, user["id"], user["session_version"], user["password_hash"]))
        self.conn.commit()
        return int(user["session_version"]) + 1 if cur.rowcount == 1 else None

    def set_email(self, user_id: int, email: str) -> None:
        """Nécessaire pour prévenir ce compte par email (2026-08-12, `notification_service`) —
        vide = pas d'email connu, `notification_service.notifier` reste alors silencieux."""
        self.conn.execute("UPDATE user SET email=? WHERE id=?", ((email or "").strip(), user_id))
        self.conn.commit()

    def admins_actifs_restants(self, exclude_user_id: int | None = None) -> int:
        """Combien de comptes Admin ACTIFS resteraient hors `exclude_user_id` — sert à interdire
        de désactiver/rétrograder le DERNIER, ce qui couperait toute gestion des comptes/accès
        (même risque d'auto-blocage que `access.require_project_access` évite déjà par projet)."""
        q = "SELECT COUNT(*) AS n FROM user WHERE role='admin' AND is_active=1"
        params: list = []
        if exclude_user_id is not None:
            q += " AND id != ?"
            params.append(exclude_user_id)
        return int(self.conn.execute(q, params).fetchone()["n"])
        self.conn.commit()


class LoginFailureRepo:
    """Compteur anti-brute-force partagé par tous les processus via la base principale."""

    def __init__(self, conn):
        self.conn = conn

    def count_recent(self, attempt_key: str, now: float, window_seconds: int) -> int:
        cutoff = now - window_seconds
        self.conn.execute("DELETE FROM login_failure WHERE occurred_at<=?", (cutoff,))
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM login_failure WHERE attempt_key=? AND occurred_at>?",
            (attempt_key, cutoff)).fetchone()
        self.conn.commit()
        return int(row["n"])

    def record(self, attempt_key: str, now: float, window_seconds: int) -> int:
        self.conn.execute(
            "INSERT INTO login_failure (attempt_key, occurred_at) VALUES (?,?)",
            (attempt_key, now))
        self.conn.commit()
        return self.count_recent(attempt_key, now, window_seconds)

    def clear(self, attempt_key: str) -> None:
        self.conn.execute("DELETE FROM login_failure WHERE attempt_key=?", (attempt_key,))
        self.conn.commit()


class UserGroupRepo:
    """Groupes d'utilisateurs administrables (migration 36)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_all(self) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT g.*, COUNT(gm.user_id) AS member_count"
            " FROM user_group g LEFT JOIN user_group_member gm ON gm.group_id=g.id"
            " GROUP BY g.id ORDER BY g.name"))

    def get(self, group_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT g.*, COUNT(gm.user_id) AS member_count"
            " FROM user_group g LEFT JOIN user_group_member gm ON gm.group_id=g.id"
            " WHERE g.id=? GROUP BY g.id", (group_id,)).fetchone()
        return dict(row) if row else None

    def members(self, group_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT u.id, u.username, u.email, u.role, u.is_active"
            " FROM user_group_member gm JOIN user u ON u.id=gm.user_id"
            " WHERE gm.group_id=? ORDER BY u.username", (group_id,)))

    def create(self, name: str, user_ids: list[int]) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("le nom du groupe est obligatoire")
        try:
            cur = self.conn.execute(
                "INSERT INTO user_group (name, created_at) VALUES (?,?)", (name, now_iso()))
        except INTEGRITY_ERRORS as exc:
            raise DuplicateName(f"le groupe « {name} » existe déjà") from exc
        group_id = int(cur.lastrowid)
        self.replace_members(group_id, user_ids, commit=False)
        self.conn.commit()
        return group_id

    def update(self, group_id: int, name: str, user_ids: list[int]) -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("le nom du groupe est obligatoire")
        try:
            self.conn.execute("UPDATE user_group SET name=? WHERE id=?", (name, group_id))
        except INTEGRITY_ERRORS as exc:
            raise DuplicateName(f"le groupe « {name} » existe déjà") from exc
        self.replace_members(group_id, user_ids, commit=False)
        self.conn.commit()

    def replace_members(self, group_id: int, user_ids: list[int], *, commit: bool = True) -> None:
        self.conn.execute("DELETE FROM user_group_member WHERE group_id=?", (group_id,))
        self.conn.executemany(
            "INSERT INTO user_group_member (group_id,user_id) VALUES (?,?)",
            [(group_id, user_id) for user_id in dict.fromkeys(user_ids)])
        if commit:
            self.conn.commit()

    def delete(self, group_id: int) -> None:
        self.conn.execute("DELETE FROM user_group WHERE id=?", (group_id,))
        self.conn.commit()


class ProjectGroupAccessRepo:
    """Surcharges de rôle attribuées à des groupes dans un projet (migration 37)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_for_project(self, project_id: int) -> list[dict]:
        # ⚠️ `pga.role`/`g.name` DANS le GROUP BY (2026-09-11) : SQLite tolère de sélectionner une
        # colonne hors du GROUP BY quand elle est de fait invariante par groupe (ici, `role` et
        # `name` ne varient jamais pour un `group_id` donné) — PostgreSQL, lui, l'interdit
        # strictement (`GroupingError`). Trouvé en conditions réelles : ce SGBD ne tourne QU'en
        # PostgreSQL sur les environnements déployés, jamais dans la suite de tests par défaut
        # (SQLite), donc rien ne l'avait attrapé avant un vrai déploiement.
        return _rows(self.conn.execute(
            "SELECT pga.project_id, pga.group_id, pga.role, g.name AS group_name,"
            " COUNT(gm.user_id) AS member_count"
            " FROM project_group_access pga JOIN user_group g ON g.id=pga.group_id"
            " LEFT JOIN user_group_member gm ON gm.group_id=g.id"
            " WHERE pga.project_id=? GROUP BY pga.project_id,pga.group_id,pga.role,g.name"
            " ORDER BY g.name", (project_id,)))

    def roles_for_user(self, project_id: int, user_id: int) -> list[str]:
        return [row["role"] for row in self.conn.execute(
            "SELECT pga.role FROM project_group_access pga"
            " JOIN user_group_member gm ON gm.group_id=pga.group_id"
            " WHERE pga.project_id=? AND gm.user_id=?", (project_id, user_id)).fetchall()]

    def get(self, project_id: int, group_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT role FROM project_group_access WHERE project_id=? AND group_id=?",
            (project_id, group_id)).fetchone()
        return row["role"] if row else None

    def set(self, project_id: int, group_id: int, role: str) -> None:
        self.conn.execute(
            "INSERT INTO project_group_access (project_id,group_id,role) VALUES (?,?,?)"
            " ON CONFLICT(project_id,group_id) DO UPDATE SET role=excluded.role",
            (project_id, group_id, role))
        self.conn.commit()

    def remove(self, project_id: int, group_id: int) -> None:
        self.conn.execute(
            "DELETE FROM project_group_access WHERE project_id=? AND group_id=?",
            (project_id, group_id))
        self.conn.commit()


class ProjectAccessRepo:
    """Surcharge du rôle global PAR PROJET (migration 31, 2026-08-10) — deux niveaux, tous deux
    optionnels : `default_access` d'un projet (une valeur sur `project`, pas dans cette table),
    et une exception PAR COMPTE dans `project_access`. La résolution complète (exception > défaut
    > rôle global) vit dans `api/access.py::role_effectif_projet` — ce repo ne fait que lire et
    écrire, comme `UserRepo` ne hache ni ne vérifie aucun mot de passe."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def default_access(self, project_id: int) -> str:
        """Chaîne vide = pas de surcharge (rôle global) — jamais `None`, pour que l'appelant
        n'ait qu'un seul cas à tester."""
        row = self.conn.execute("SELECT default_access FROM project WHERE id=?",
                                (project_id,)).fetchone()
        return (row["default_access"] if row else "") or ""

    def set_default_access(self, project_id: int, default_access: str) -> None:
        self.conn.execute("UPDATE project SET default_access=? WHERE id=?",
                          (default_access, project_id))
        self.conn.commit()
        ProjectMemberRepo(self.conn).sync_project(project_id)

    def overrides_for_project(self, project_id: int) -> list[dict]:
        """Les exceptions par compte de CE projet, avec le nom d'utilisateur déjà joint — l'écran
        Admin n'a besoin de rien résoudre lui-même."""
        return _rows(self.conn.execute(
            "SELECT pa.project_id, pa.user_id, pa.role, u.username"
            " FROM project_access pa JOIN user u ON u.id = pa.user_id"
            " WHERE pa.project_id=? ORDER BY u.username", (project_id,)))

    def override_for_user(self, project_id: int, user_id: int) -> str | None:
        """`None` = aucune exception pour ce compte sur ce projet (repli sur `default_access`
        puis le rôle global) — distinct d'une chaîne vide, qui n'existe pas ici : une ligne de
        `project_access` porte TOUJOURS un rôle explicite."""
        row = self.conn.execute(
            "SELECT role FROM project_access WHERE project_id=? AND user_id=?",
            (project_id, user_id)).fetchone()
        return row["role"] if row else None

    def set_override(self, project_id: int, user_id: int, role: str) -> None:
        self.conn.execute(
            "INSERT INTO project_access (project_id, user_id, role) VALUES (?,?,?)"
            " ON CONFLICT (project_id, user_id) DO UPDATE SET role=excluded.role",
            (project_id, user_id, role))
        self.conn.commit()
        ProjectMemberRepo(self.conn).sync_one(project_id, user_id)

    def remove_override(self, project_id: int, user_id: int) -> None:
        self.conn.execute(
            "DELETE FROM project_access WHERE project_id=? AND user_id=?",
            (project_id, user_id))
        self.conn.commit()
        ProjectMemberRepo(self.conn).sync_one(project_id, user_id)


class ProjectMemberRepo:
    """Appartenances explicites à un projet (migration 34).

    Ce premier slice cohabite avec `ProjectAccessRepo` jusqu'à la validation de parité complète ;
    il ne décide pas encore de l'autorisation HTTP.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, project_id: int, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM project_member WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT pm.*, u.username, u.email FROM project_member pm"
            " JOIN user u ON u.id=pm.user_id WHERE pm.project_id=?"
            " ORDER BY u.username", (project_id,),
        ))

    def set(self, project_id: int, user_id: int, role: str,
            status: str = "active") -> None:
        self.conn.execute(
            "INSERT INTO project_member (project_id,user_id,role,status,created_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(project_id,user_id) DO UPDATE SET"
            " role=excluded.role,status=excluded.status",
            (project_id, user_id, role, status, now_iso()),
        )
        self.conn.commit()

    def remove(self, project_id: int, user_id: int) -> None:
        self.conn.execute(
            "UPDATE project_member SET status='removed' WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        )
        self.conn.commit()

    def effective_role(self, project_id: int, user_id: int) -> str:
        member = self.get(project_id, user_id)
        if member is None or member["status"] != "active":
            return "no_access"
        return member["role"]

    def active_admin_count(self, project_id: int, exclude_user_id: int | None = None) -> int:
        query = (
            "SELECT COUNT(*) AS n FROM project_member pm"
            " JOIN user u ON u.id=pm.user_id"
            " WHERE pm.project_id=? AND pm.role='admin'"
            " AND pm.status='active' AND u.is_active=1"
        )
        params: list = [project_id]
        if exclude_user_id is not None:
            query += " AND pm.user_id<>?"
            params.append(exclude_user_id)
        return int(self.conn.execute(query, params).fetchone()["n"])

    def sync_one(self, project_id: int, user_id: int) -> None:
        """Recalcule une appartenance depuis le modèle historique."""
        row = self.conn.execute(
            "SELECT u.is_active,"
            " COALESCE(pa.role, NULLIF(p.default_access,''), u.role) AS effective_role"
            " FROM project p CROSS JOIN user u"
            " LEFT JOIN project_access pa"
            "   ON pa.project_id=p.id AND pa.user_id=u.id"
            " WHERE p.id=? AND u.id=? AND p.deleted_at=''",
            (project_id, user_id),
        ).fetchone()
        if row is None or row["effective_role"] == "no_access":
            if self.get(project_id, user_id) is not None:
                self.conn.execute(
                    "UPDATE project_member SET status='removed'"
                    " WHERE project_id=? AND user_id=?", (project_id, user_id),
                )
                self.conn.commit()
            return
        self.set(
            project_id, user_id, row["effective_role"],
            "active" if row["is_active"] else "suspended",
        )

    def sync_project(self, project_id: int) -> None:
        for row in self.conn.execute("SELECT id FROM user").fetchall():
            self.sync_one(project_id, row["id"])

    def sync_user(self, user_id: int) -> None:
        for row in self.conn.execute(
            "SELECT id FROM project WHERE deleted_at=''"
        ).fetchall():
            self.sync_one(row["id"], user_id)


class AccessAuditRepo:
    """Trace append-only des décisions prises lors de la gestion des accès projet."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, *, actor_user_id: int | None, project_id: int, action: str,
               target_user_id: int | None, result: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO access_audit"
            " (occurred_at,actor_user_id,project_id,action,target_user_id,result,detail)"
            " VALUES (?,?,?,?,?,?,?)",
            (now_iso(), actor_user_id, project_id, action, target_user_id, result, detail),
        )
        self.conn.commit()

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM access_audit WHERE project_id=? ORDER BY id", (project_id,)))
