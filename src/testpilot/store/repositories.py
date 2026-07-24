"""Repositories — accès au référentiel TestPilot.

Chaque classe encapsule une table (ou un agrégat proche). Entrées/sorties = dict
simples pour garder le socle léger et portable vers PostgreSQL. Les valeurs d'enum
font autorité dans ``verdict/status.py`` ; la base les reflète via des CHECK (schema.sql).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from testpilot import config
from testpilot.store import secrets as secrets_mod

logger = logging.getLogger(__name__)


class DuplicateName(ValueError):
    """Un nom déjà pris à sa portée d'unicité (projet global, module/projet, cas/module).

    Levée par les repos — donc honorée par l'API *et* la CLI. Les routes la traduisent en
    HTTP 409 ; l'index UNIQUE en base reste le filet de dernier recours.
    """


class NotEmpty(ValueError):
    """Un conteneur qu'on refuse de supprimer parce qu'il porte encore des enfants.

    Levée par les repos, traduite en HTTP 409 par les routes. Le refus est DÉLIBÉRÉ et non un
    manque : supprimer une spécification en cascade emporterait des cas qui portent des versions,
    des exécutions et des coûts — c'est-à-dire de l'historique, que le projet ne détruit jamais
    en silence (§2.10 : « on n'efface jamais un run, on annote »). L'utilisateur vide d'abord.
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
        for row in self.conn.execute("SELECT id, name FROM project"):
            if row["id"] != excluding and _key(row["name"]) == _key(name):
                raise DuplicateName(f"un projet nommé « {row['name']} » existe déjà")

    def create(self, *, name: str, description: str = "", connector_type: str = "odoo",
               base_url: str = "", database: str = "", username: str = "",
               password: str = "") -> int:
        self.ensure_name_free(name)
        cur = self.conn.execute(
            "INSERT INTO project (name, description, connector_type, base_url, database,"
            " username, password, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (name, description, connector_type, base_url, database, username,
             secrets_mod.chiffrer(password), now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

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
        row = self.conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
        return self._en_clair(row) if row else None

    def list_all(self) -> list[dict]:
        """Projets + compteurs de modules et de cas (pour l'accueil / le sélecteur)."""
        return [self._en_clair(r) for r in self.conn.execute(
            "SELECT p.*,"
            " (SELECT COUNT(*) FROM module m WHERE m.project_id=p.id) AS module_count,"
            " (SELECT COUNT(*) FROM test_case tc JOIN module m ON tc.module_id=m.id"
            "  WHERE m.project_id=p.id) AS case_count"
            " FROM project p ORDER BY p.id")]

    def find_by_name(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM project WHERE name=?", (name,)).fetchone()
        return self._en_clair(row) if row else None

    def first(self) -> dict | None:
        """Projet par défaut (le plus ancien). Source unique de la règle « projet courant »
        hors interface : rattachement automatique ET connexion du runtime en CLI."""
        row = self.conn.execute("SELECT * FROM project ORDER BY id LIMIT 1").fetchone()
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
    _CONNEXION = ("connector_type", "base_url", "database", "username")

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

    def delete(self, project_id: int) -> None:
        """Supprime un projet ET toute sa descendance (modules, cas, versions, relectures,
        exécutions, résultats, réparations, coûts) — dans l'ordre des FK, en une transaction."""
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
            cur.execute(f"DELETE FROM execution        WHERE test_case_id IN ({case_sub})", (project_id,))
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
        for row in self.conn.execute("SELECT id, name FROM module WHERE project_id=?", (project_id,)):
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
            " WHERE m.id=?", (module_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT m.*,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.module_id=m.id) AS case_count"
            " FROM module m WHERE m.project_id=? ORDER BY m.id", (project_id,)))

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

    def delete(self, module_id: int) -> None:
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
            cases.delete(cid)
        # Les spécifications du module n'ont plus de cas (on vient de tous les retirer).
        self.conn.execute("DELETE FROM case_group WHERE module_id=?", (module_id,))
        self.conn.execute("DELETE FROM module WHERE id=?", (module_id,))
        self.conn.commit()

    def find_by_name(self, project_id: int, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM module WHERE project_id=? AND name=?", (project_id, name)).fetchone()
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
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id) AS n"
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
        for row in self.conn.execute("SELECT id, title FROM case_group WHERE module_id=?",
                                     (module_id,)):
            if row["id"] == excluding or _key(row["title"]) != _key(title):
                continue
            if self.est_residu(row["id"]):
                logger.info("[spécification] résidu #%s « %s » récupéré : ni cas ni document",
                            row["id"], row["title"])
                self.conn.execute("DELETE FROM case_group WHERE id=?", (row["id"],))
                continue
            raise DuplicateName(f"ce module a déjà une spécification « {row['title']} »")

    def create(self, *, module_id: int, title: str, description: str = "",
               spec_content: str = "", spec_hash: str = "", auto_enveloppe: bool = False) -> int:
        """Crée une spécification. `spec_content` est LE DOCUMENT source (2026-07-19) ; `spec_hash`
        son empreinte, que chaque cas généré référencera. Vides à l'auto-enveloppement d'un cas
        (la spec vit encore sur la version jusqu'à l'étape 3).

        ⚠️ `auto_enveloppe=True` **uniquement** depuis `CaseRepo.create`, qui fabrique un conteneur
        1:1 autour d'un cas qui n'en avait pas. Ce drapeau donne à cette enveloppe le droit d'être
        récupérée quand son cas disparaît. Par défaut **False** : tout ce qui vient de l'écran est
        délibéré, donc protégé — en cas de doute, on protège (migration 17).
        """
        self.ensure_title_free(module_id, title)
        ts = now_iso()
        row = self.conn.execute("SELECT MAX(position) AS m FROM case_group WHERE module_id=?",
                                (module_id,)).fetchone()
        position = 0 if row["m"] is None else int(row["m"]) + 1
        cur = self.conn.execute(
            "INSERT INTO case_group (module_id, title, description, spec_content, spec_hash,"
            " position, auto_enveloppe, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (module_id, title, description, spec_content, spec_hash, position,
             int(auto_enveloppe), ts, ts))
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, group_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM case_group WHERE id=?", (group_id,)).fetchone()
        return dict(row) if row else None

    def list_for_module(self, module_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT g.*,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id) AS case_count"
            " FROM case_group g WHERE g.module_id=? ORDER BY g.position, g.id", (module_id,)))

    def list_for_project(self, project_id: int) -> list[dict]:
        """Toutes les spécifications d'un projet (jointes au module), pour l'arbre latéral."""
        return _rows(self.conn.execute(
            "SELECT g.id, g.module_id, g.title, g.position,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.group_id=g.id) AS case_count"
            " FROM case_group g JOIN module m ON g.module_id=m.id"
            " WHERE m.project_id=? ORDER BY g.module_id, g.position, g.id", (project_id,)))

    def case_count(self, group_id: int) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM test_case WHERE group_id=?",
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

    def delete(self, group_id: int) -> None:
        """Supprime une spécification VIDE. Refuse (NotEmpty) tant qu'elle porte des cas.

        Pas de cascade : un cas porte des versions, des exécutions, des résultats et des lignes de
        coût. Les emporter sur la suppression de leur conteneur détruirait de l'historique sans
        que personne l'ait demandé — le contraire de la ligne du projet (§2.10). L'utilisateur
        supprime (ou déplace) ses cas d'abord ; le refus dit combien il en reste.
        """
        n = self.case_count(group_id)
        if n:
            raise NotEmpty(f"cette spécification porte encore {n} cas — supprimez-les d'abord")
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
        rows = self.conn.execute("SELECT id, title FROM test_case WHERE group_id=?", (group_id,))
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
        rows = self.conn.execute("SELECT id, title FROM test_case WHERE feature_slug=?",
                                 (feature_slug,))
        for row in rows:
            if row["id"] != excluding:
                raise DuplicateName(
                    f"le fichier de test « {feature_slug}.feature » est déjà utilisé par le cas "
                    f"« {row['title']} »")

    def create(self, *, title: str, module_id: int | None = None, group_id: int | None = None,
               angle: str = "", feature_slug: str = "", author: str = "", description: str = "",
               origin: str = "ia_generated", priority: str = "medium") -> int:
        """Crée un cas. `group_id` OBLIGATOIRE pour tout cas RANGÉ dans un module : s'il n'est pas
        fourni mais qu'un module l'est, on AUTO-ENVELOPPE le cas dans sa propre spécification 1:1
        (même geste que la migration legacy). L'appelant historique (la génération) continue donc
        de marcher sans changement — l'étape 3 lui fera passer un `group_id` explicite.

        Un cas SANS module (module_id=None) reste sans groupe : il n'a pas de place dans la
        hiérarchie Module→Spécification→Cas, donc aucune spécification à lui donner. C'est un cas
        de bord (hors arbre), pas le chemin de production — qui passe toujours par un module.
        """
        if group_id is None and module_id is not None:
            group_id = CaseGroupRepo(self.conn).create(module_id=module_id, title=title,
                                                       auto_enveloppe=True)
        self.ensure_title_free(group_id, title)
        self.ensure_slug_free(feature_slug)
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_case (title, module_id, group_id, angle, feature_slug, description,"
            " origin, validation_status, priority, position, author, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?, 'never_executed', ?,?,?,?,?)",
            (title, module_id, group_id, angle, feature_slug, description, origin, priority,
             self._next_position(module_id), author, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def create_manual(self, *, module_id: int, title: str, preconditions: str = "",
                      test_steps: str = "", expected_result: str = "", angle: str = "",
                      author: str = "ui") -> int:
        """Crée un cas À LA MAIN — le bouton « Ajouter un cas de test », SANS IA (décision `0022`).

        Le cas naît avec son **document métier** (titre, préconditions, étapes, résultat attendu)
        mais **sans Gherkin** : il n'est donc pas exécutable tant qu'un test technique n'a pas été
        généré (décision `0022` n°6, bouton « Régénérer le test technique » à venir). Ce n'est PAS
        le « cas fantôme » que `0006` refusait — un cas fantôme ne testait rien *et* ne décrivait
        rien ; celui-ci porte une intention métier lisible, assumée par un humain (décision n°7).

        `origin='manual_converted'` : marque un cas d'origine humaine (par opposition à
        `ia_generated`), la seule valeur non-IA que le schéma autorise. Une version est créée
        d'emblée : c'est elle qui porte le métier (le métier vit sur la version, décision n°10).
        """
        cid = self.create(title=title, module_id=module_id, author=author,
                          origin="manual_converted", feature_slug="")
        VersionRepo(self.conn).create(
            test_case_id=cid, spec_content="", spec_hash="",
            feature_content="", steps_content="",   # pas de Gherkin : cas non exécutable en l'état
            change_summary="Création manuelle", created_by=author,
            title=title, preconditions=preconditions, test_steps=test_steps,
            expected_result=expected_result, angle=angle)
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

    def delete(self, case_id: int) -> None:
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

    def _nettoyer_specification_orpheline(self, group_id: int | None) -> None:
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
            self.conn.execute("DELETE FROM case_group WHERE id=?", (group_id,))

    def update_metier(self, case_id: int, *, title: str | None = None,
                      preconditions: str | None = None, test_steps: str | None = None,
                      expected_result: str | None = None, angle: str | None = None,
                      refs: str | None = None, estimate: str | None = None,
                      editor: str = "ui") -> int | None:
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

        Rend l'id de la nouvelle version, ou `None` si aucun champ versionné n'a changé.
        """
        case = self.get(case_id)
        if case is None:
            return None
        versions = VersionRepo(self.conn)
        current = versions.get(case.get("current_version_id")) if case.get("current_version_id") else None

        # Métadonnées : simple mise à jour sur le cas, sans version.
        meta = {k: v for k, v in (("refs", refs), ("estimate", estimate)) if v is not None}
        if meta:
            sets = ", ".join(f"{k}=?" for k in meta)
            self.conn.execute(f"UPDATE test_case SET {sets}, updated_at=? WHERE id=?",
                              (*meta.values(), now_iso(), case_id))
            self.conn.commit()

        # Contenu versionné : valeur fournie, sinon celle de la version courante (repli sur le cas
        # pour titre/angle, car les versions d'avant la migration 14 n'en portaient pas).
        def pick(new, key, fallback):
            if new is not None:
                return new
            return (current or {}).get(key) or fallback

        new_title = pick(title, "title", case.get("title", ""))
        new_pre = pick(preconditions, "preconditions", "")
        new_steps = pick(test_steps, "test_steps", "")
        new_expected = pick(expected_result, "expected_result", "")
        new_angle = pick(angle, "angle", case.get("angle", ""))

        inchange = (current is not None
                    and new_title == (current.get("title") or case.get("title", ""))
                    and new_pre == (current.get("preconditions") or "")
                    and new_steps == (current.get("test_steps") or "")
                    and new_expected == (current.get("expected_result") or "")
                    and new_angle == (current.get("angle") or case.get("angle", "")))
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
            expected_result=new_expected, angle=new_angle,
        )
        # Le CAS porte des COPIES courantes (titre/angle) pour les listes et les filtres.
        # La VERSION fait foi — même règle que le raccourci de résultat.
        self.conn.execute(
            "UPDATE test_case SET title=?, angle=?, current_version_id=?, updated_at=? WHERE id=?",
            (new_title, new_angle, version_id, now_iso(), case_id))
        self.conn.commit()
        return version_id

    def set_priority(self, case_id: int, priority: str) -> None:
        self.conn.execute("UPDATE test_case SET priority=?, updated_at=? WHERE id=?",
                          (priority, now_iso(), case_id))
        self.conn.commit()

    def get(self, case_id: int) -> dict | None:
        row = self.conn.execute(_CASE_SELECT + " WHERE tc.id=?", (case_id,)).fetchone()
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
        clauses, params = [], []
        if project_id is not None:
            clauses.append("m.project_id = ?"); params.append(project_id)
        if module_id is not None:
            clauses.append("tc.module_id = ?"); params.append(module_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order = " ORDER BY tc.module_id, tc.position, tc.id"
        return _rows(self.conn.execute(_CASE_SELECT + where + order, params))

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

    def set_validation_status(self, case_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE test_case SET validation_status=?, updated_at=? WHERE id=?",
            (status, now_iso(), case_id),
        )
        self.conn.commit()

    def update_last_outcome(self, case_id: int, *, execution_status: str,
                            functional_status: str, executed_at: str) -> None:
        self.conn.execute(
            "UPDATE test_case SET last_execution_status=?, last_functional_status=?,"
            " last_executed_at=?, updated_at=? WHERE id=?",
            (execution_status, functional_status, executed_at, now_iso(), case_id),
        )
        self.conn.commit()


class VersionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, spec_content: str, spec_hash: str,
               feature_content: str, steps_content: str, feature_path: str = "",
               steps_path: str = "", change_summary: str = "", created_by: str = "",
               title: str = "", preconditions: str = "", test_steps: str = "",
               expected_result: str = "", angle: str = "") -> int:
        """Crée une version — **le CAS ENTIER**, métier ET technique (décision `0022` n°10).

        Les champs métier (`title`, `preconditions`, `test_steps`, `expected_result`, `angle`)
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
            " title, preconditions, test_steps, expected_result, angle)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (test_case_id, number, spec_content, spec_hash, feature_content, steps_content,
             feature_path, steps_path, change_summary, now_iso(), created_by,
             title, preconditions, test_steps, expected_result, angle),
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

    def list_for_case(self, test_case_id: int) -> list[dict]:
        """Historique des décisions de relecture d'un cas (toutes versions), anté-chronologique."""
        return _rows(self.conn.execute(
            "SELECT * FROM review_decision WHERE test_case_id=? ORDER BY id DESC",
            (test_case_id,)))


class ExecutionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def quality_summary(self, *, project_id: int | None = None) -> dict:
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
        where = "WHERE e.trigger = 'first_run'"
        params: tuple = ()
        if project_id is not None:
            where += (" AND e.test_case_id IN (SELECT tc.id FROM test_case tc"
                      " JOIN module m ON tc.module_id = m.id WHERE m.project_id = ?)")
            params = (project_id,)

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
        # `ran_rate` reste None (et non 0.0) sans donnée : « aucune mesure » n'est pas « 0 % de
        # réussite » — le motif du repli silencieux qu'on refuse partout (§4.6).
        ran_rate = (total["success"] / n) if n else None
        return {
            "total": n,
            "ran": total["success"],
            "technical_error": total["technical_error"],
            "not_executed": total["not_executed"],
            "ran_rate": ran_rate,
            "by_day": sorted(par_jour.values(), key=lambda d: d["jour"]),
        }

    def create(self, *, test_case_id: int, version_id: int, trigger: str = "first_run",
               cible: dict | None = None) -> int:
        """Ouvre une ligne d'exécution.

        `cible` (migration 20) : contre quelle application on va tourner — adresse, base,
        utilisateur, **jamais le mot de passe**. Écrite à l'OUVERTURE et non à la clôture : une
        exécution qui plante avant la fin doit tout de même dire ce qu'elle visait.
        """
        c = cible or {}
        cur = self.conn.execute(
            "INSERT INTO execution (test_case_id, version_id, trigger, target_url,"
            " target_database, target_username, started_at) VALUES (?,?,?,?,?,?,?)",
            (test_case_id, version_id, trigger, str(c.get("target_url") or ""),
             str(c.get("target_database") or ""), str(c.get("target_username") or ""), now_iso()),
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
                 field_fallbacks: str = "", error_message: str = "") -> None:
        """Clôt une exécution avec son verdict.

        `error_message` : raison d'un plantage AVANT tout scénario (migration 11) — sans elle,
        l'écran affiche « erreur technique » sans dire pourquoi.

        ⚠️ `report_json_path`/`report_html_path` ont été **supprimés** (migration 7) : personne ne
        les alimentait ni ne les lisait. Le rapport est **reconstruit à la demande** depuis la
        base (`report_service.build_report_for_execution`) — c'est le seul mécanisme réel.
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

    def get(self, execution_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM execution WHERE id=?", (execution_id,)).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM execution WHERE test_case_id=? ORDER BY id", (test_case_id,)))

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
               selection_mode: str = "frozen", case_ids: list[int] | None = None) -> int:
        """Crée un run en BROUILLON (jamais lancé à la création — `0022` 8.c.1).

        `case_ids` n'est matérialisé que pour `frozen` : en mode `all`, la sélection est vivante,
        la stocker figerait ce qu'on veut justement garder mouvant.
        """
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_run (project_id, name, description, refs, selection_mode, status,"
            " created_at) VALUES (?,?,?,?,?,'draft',?)",
            (project_id, name, description, refs, selection_mode, ts))
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
        # `tested_count` = cas DISTINCTS ayant au moins une exécution dans ce run — la base du
        # « % de complétion » de l'écran Aperçu (note fonctionnelle). Le total dépend du mode
        # (figé = frozen_count ; vivant = calculé par l'appelant), d'où les deux exposés.
        return _rows(self.conn.execute(
            "SELECT r.*,"
            " (SELECT COUNT(*) FROM test_run_case rc WHERE rc.run_id=r.id) AS frozen_count,"
            " (SELECT COUNT(DISTINCT e.test_case_id) FROM execution e WHERE e.run_id=r.id)"
            "     AS tested_count"
            " FROM test_run r WHERE r.project_id=? ORDER BY r.id DESC", (project_id,)))

    def case_ids(self, run_id: int) -> list[int]:
        """Les cas du run : recalculés (mode `all`) ou lus dans la liaison figée (`frozen`)."""
        run = self.get(run_id)
        if run is None:
            return []
        if run["selection_mode"] == "all":
            return [r["id"] for r in self.conn.execute(
                "SELECT tc.id FROM test_case tc JOIN module m ON tc.module_id=m.id"
                " WHERE m.project_id=? ORDER BY tc.id", (run["project_id"],))]
        return [r["case_id"] for r in self.conn.execute(
            "SELECT case_id FROM test_run_case WHERE run_id=? ORDER BY case_id", (run_id,))]

    def cases_with_results(self, run_id: int) -> list[dict]:
        """Chaque cas du run + son résultat DANS CE run (la dernière exécution rattachée).

        C'est le cœur de `0022` n°4 : le résultat vit sur le cas × run. Un cas sans exécution
        dans ce run est « Non testé » — on l'expose quand même (il fait partie de la campagne).
        """
        out = []
        for cid in self.case_ids(run_id):
            case = self.conn.execute(
                "SELECT id, title, last_execution_status, last_functional_status"
                " FROM test_case WHERE id=?", (cid,)).fetchone()
            if case is None:
                continue  # cas supprimé depuis (mode all) — on ne fabrique rien
            ex = self.conn.execute(
                "SELECT id, execution_status, functional_status, scenarios_total,"
                " scenarios_passed, started_at FROM execution"
                " WHERE run_id=? AND test_case_id=? ORDER BY id DESC LIMIT 1", (run_id, cid)).fetchone()
            row = dict(case)
            row["result"] = dict(ex) if ex else None
            out.append(row)
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
