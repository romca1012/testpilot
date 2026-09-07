"""Comptes utilisateurs, rôles, et session (2026-08-07 — remplace le lot 2 du 2026-07-24).

**Ce que c'était avant, et pourquoi ça change.** Le lot 2 posait un mot de passe UNIQUE partagé
par toute l'équipe, plus un nom libre saisi à l'arrivée — explicitement PAS un système de comptes
(« chacun écrit ce qu'il veut »). C'était un choix assumé pour ne pas retarder le déploiement.
Le porteur demande maintenant le vrai système : des comptes individuels, avec un rôle qui borne ce
que chacun peut faire.

**Les 4 rôles**, en hiérarchie CROISSANTE de droits — chacun hérite de tout ce que le précédent
peut faire :

- `lecture_seule` — consulter, jamais écrire.
- `testeur` — usage courant : créer/éditer des cas, lancer des exécutions, saisir des résultats.
- `dev` — + éditer directement le Gherkin/Python généré (l'onglet Script d'un cas).
- `admin` — + gérer les comptes (créer, changer un rôle, activer/désactiver).

**La connexion est désormais OBLIGATOIRE partout** (`verrou_actif()` ne dépend plus d'une
variable d'environnement optionnelle) — il n'existe plus de mode « poste de développement sans
verrou ».

**Un jeton de session porte `user_id` + `username`, signés** — mais PAS le rôle : le rôle et
l'état actif (`is_active`) sont vérifiés EN BASE à chaque requête (voir `utilisateur_actuel`), pas
dans le jeton. C'est délibéré : un jeton dure `SESSION_DAYS` (30 par défaut) — y figer le rôle
ferait qu'une désactivation ou une rétrogradation par un Admin resterait sans effet jusqu'à
l'expiration naturelle de la session, exactement le risque qu'on cherche à couvrir en ajoutant des
rôles.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from testpilot import config
from testpilot.api.deps import get_conn

logger = logging.getLogger(__name__)

COOKIE = "testpilot_session"
_HEADER_UTILISATEUR = "X-TestPilot-User"
_NOM_FICHIER_CLE_SESSION = ".session_secret"

# Chemins toujours ouverts : l'écran de connexion doit pouvoir se charger et se poster.
# ⚠️ `/api/auth/logout` EN FAIT PARTIE (bug réel, trouvé en vérification live 2026-08-07) : une
# route `POST`, donc une « écriture » aux yeux d'`ecriture_bloquee` — un compte Lecture seule ne
# pouvait tout simplement PAS se déconnecter (403 « droits insuffisants » sur son propre bouton
# « Se déconnecter »). Se déconnecter n'est jamais un geste à restreindre par rôle.
_LIBRES = (
    "/api/health", "/api/health/live", "/api/health/ready",
    "/api/auth/login", "/api/auth/session", "/api/auth/logout",
)

# Hiérarchie croissante — l'index dans ce tuple EST le niveau de droits.
ROLE_LECTURE_SEULE = "lecture_seule"
ROLE_TESTEUR = "testeur"
ROLE_DEV = "dev"
ROLE_ADMIN = "admin"
ROLES = (ROLE_LECTURE_SEULE, ROLE_TESTEUR, ROLE_DEV, ROLE_ADMIN)

# ⚠️ PAS dans `ROLES` — ce n'est pas un rôle qu'un COMPTE porte (`user.role` ne le connaît pas),
# seulement une valeur que la surcharge PAR PROJET peut prendre (migration 31, 2026-08-10). Un
# rôle inconnu de `ROLES` vaut déjà -1 pour `niveau()` (repli existant) : `no_access` en hérite
# sans rien ajouter à la hiérarchie des comptes.
ACCES_PROJET_REFUSE = "no_access"

# Méthodes HTTP considérées comme une ÉCRITURE — bloquées pour `lecture_seule` (middleware).
METHODES_ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Écritures qu'AUCUN rôle ne doit voir bloquer, même `lecture_seule` (2026-09-03) — DISTINCT de
# `_LIBRES` ci-dessus : ces chemins restent authentifiés (la route a besoin de savoir QUI agit),
# seule la garde de rôle d'`ecriture_bloquee` s'efface pour eux. Même raisonnement que le carve-out
# de `/api/auth/logout` dans `_LIBRES` : sécuriser SON PROPRE compte n'est jamais un geste à
# restreindre par rôle — un Lecture seule doit pouvoir changer un mot de passe qu'il sait compromis
# aussi bien qu'un Admin.
_ECRITURES_TOUJOURS_AUTORISEES = ("/api/auth/password",)

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_ITERATIONS_HISTORIQUE = 200_000
_PBKDF2_PREFIXE = "pbkdf2_sha256"

# Plancher posé le 2026-08-11 : jusque-là, un mot de passe d'un seul caractère était accepté
# (seule garde : non vide). Pas de politique plus riche (majuscule/chiffre/symbole) — un plancher
# de longueur simple couvre l'essentiel pour une équipe interne, sans friction disproportionnée.
MOT_DE_PASSE_LONGUEUR_MIN = config.PASSWORD_MIN_LENGTH


def verifier_politique_mot_de_passe(value: str, username: str = "") -> None:
    from testpilot.api.erreurs import ErreurMetier
    if not MOT_DE_PASSE_LONGUEUR_MIN <= len(value) <= 128:
        raise ErreurMetier("requete_invalide",
                          f"le mot de passe doit compter entre {MOT_DE_PASSE_LONGUEUR_MIN} et 128 caractères")
    faible = value.casefold().strip()
    interdits = {"password", "password123", "password123456789", "123456789012345",
                 "azerty123456789", "motdepasse", "motdepasse123456", "qwerty123456789",
                 "testpilot123456789", "changeme123456789", "correct horse battery staple"}
    if faible in interdits or len(set(faible)) < 3 or (username and faible == username.casefold()):
        raise ErreurMetier("requete_invalide", "ce mot de passe est trop prévisible ; choisissez une phrase personnelle")


def niveau(role: str) -> int:
    """Position d'un rôle dans la hiérarchie — plus haut = plus de droits. Rôle inconnu : le plus
    bas niveau possible, jamais une exception (un rôle corrompu ne doit jamais élever des droits)."""
    try:
        return ROLES.index(role)
    except ValueError:
        return -1


def role_suffisant(role: str, minimum: str) -> bool:
    return niveau(role) >= niveau(minimum)


# ── Mots de passe — PBKDF2-HMAC-SHA256, stdlib seule (zéro dépendance nouvelle) ────────────────

def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """`algorithme$itérations$sel$hachage`. Le sel est PAR MOT DE PASSE — deux comptes identiques
    ne doivent jamais produire le même hachage (sinon leur égalité se lirait dans la base)."""
    sel = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", (mot_de_passe or "").encode("utf-8"), sel,
                           _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_PREFIXE}${_PBKDF2_ITERATIONS}${sel.hex()}${h.hex()}"


def verifier_mot_de_passe(propose: str, hache: str) -> bool:
    """Recalcule avec le MÊME sel que le hachage stocké, compare à temps constant."""
    try:
        morceaux = (hache or "").split("$")
        if len(morceaux) == 4 and morceaux[0] == _PBKDF2_PREFIXE:
            _algo, iterations_txt, sel_hex, attendu_hex = morceaux
            iterations = int(iterations_txt)
        elif len(morceaux) == 2:
            # Compatibilité avec les comptes créés avant la migration du facteur de travail.
            sel_hex, attendu_hex = morceaux
            iterations = _PBKDF2_ITERATIONS_HISTORIQUE
        else:
            return False
        sel = bytes.fromhex(sel_hex)
        attendu = bytes.fromhex(attendu_hex)
        if iterations < 1 or iterations > 10_000_000:
            return False
    except (ValueError, AttributeError):
        return False
    calcule = hashlib.pbkdf2_hmac("sha256", (propose or "").encode("utf-8"), sel,
                                  iterations)
    return hmac.compare_digest(calcule, attendu)


def hachage_a_mettre_a_niveau(hache: str) -> bool:
    """Vrai pour l'ancien format ou un facteur inférieur au facteur courant."""
    morceaux = (hache or "").split("$")
    if len(morceaux) != 4 or morceaux[0] != _PBKDF2_PREFIXE:
        return True
    try:
        return int(morceaux[1]) < _PBKDF2_ITERATIONS
    except ValueError:
        return True


# ── Session — jeton signé, indépendant de tout mot de passe de compte ──────────────────────────

def verrou_actif() -> bool:
    """Toujours vrai désormais — la connexion est obligatoire (2026-08-07). Fonction conservée
    (plutôt que ses appelants purgés un par un) : `SessionOut.lock_enabled` et le middleware la
    lisent encore, et le jour où un mode sans verrou redevient nécessaire, un seul endroit change."""
    return True


def _cle() -> bytes:
    """Clé de signature des sessions — `TESTPILOT_SESSION_SECRET` si fournie, sinon un fichier à
    part créé au besoin (même patron que `store/secrets.py::_lire_ou_creer_cle`, appliqué à un
    secret DISTINCT : `TESTPILOT_SECRET_KEY` chiffre les mots de passe de connexion des projets,
    un usage différent — les confondre ferait qu'un incident sur l'un compromette l'autre).

    JAMAIS dérivée d'un mot de passe de compte (avant le 2026-08-07, elle dérivait du mot de passe
    UNIQUE partagé — changer SON mot de passe ne doit invalider QUE SA session, pas celle de toute
    l'équipe)."""
    depuis_env = (config.SESSION_SECRET or "").strip()
    if depuis_env:
        return hashlib.sha256(depuis_env.encode("utf-8")).digest()

    chemin = Path(config.DATA_DIR) / _NOM_FICHIER_CLE_SESSION
    if chemin.is_file():
        return chemin.read_bytes()

    chemin.parent.mkdir(parents=True, exist_ok=True)
    cle = os.urandom(32)
    chemin.write_bytes(cle)
    try:
        chemin.chmod(0o600)  # sans effet réel sous Windows — d'où le rappel ci-dessous
    except OSError:  # pragma: no cover - systèmes sans permissions POSIX
        pass
    logger.warning(
        "[accès] clé de signature des sessions CRÉÉE dans %s. Sur un serveur partagé, préférez "
        "la variable d'environnement TESTPILOT_SESSION_SECRET : une clé rangée à côté de la base "
        "ne protège que les copies de la base, pas un accès à la machine.", chemin)
    return cle


def _signer(charge: str) -> str:
    return hmac.new(_cle(), charge.encode("utf-8"), hashlib.sha256).hexdigest()


def creer_jeton(user_id: int, username: str, session_version: int = 1) -> str:
    """Jeton : `expiration.user_id.session_version.username.signature`. `username` y figure pour que
    `utilisateur_de` reste `request`-seul (aucune lecture base) — c'est le rôle, lui, qui se
    vérifie en base à chaque requête (voir le module docstring)."""
    expire = int(time.time()) + config.SESSION_DAYS * 86400
    nom_propre = (username or "").replace(".", " ").strip()[:60]
    charge = f"{expire}.{user_id}.{int(session_version)}.{nom_propre}"
    return f"{charge}.{_signer(charge)}"


def lire_jeton(jeton: str | None) -> tuple[int, int, str] | None:
    """`(user_id, session_version, username)` d'un jeton valide, ou `None`. Jamais d'exception : une
    entrée douteuse est une session absente, pas une panne."""
    if not jeton:
        return None
    try:
        expire_txt, uid_txt, version_txt, nom, signature = jeton.split(".", 4)
        charge = f"{expire_txt}.{uid_txt}.{version_txt}.{nom}"
        if not hmac.compare_digest(signature, _signer(charge)):
            return None
        if int(expire_txt) < time.time():
            return None
        return int(uid_txt), int(version_txt), nom
    except (ValueError, AttributeError):
        return None


def utilisateur_de(request: Request) -> str:
    """Le nom du testeur connecté : la session d'abord, puis l'en-tête (client sans cookie),
    sinon vide. Signature INCHANGÉE depuis le lot 2 (2026-07-24) — des dizaines d'appelants
    l'utilisent pour signer `created_by`/`deleted_by`/`author` ; seule la garantie derrière change
    (un compte vérifié, plus une déclaration libre)."""
    jeton = lire_jeton(request.cookies.get(COOKIE))
    if jeton:
        return jeton[2]
    return (request.headers.get(_HEADER_UTILISATEUR) or "").strip()[:60]


def utilisateur_actuel(conn, request: Request) -> dict | None:
    """L'utilisateur AUTHENTIFIÉ pour cette requête, rôle et état actif LUS EN BASE (pas depuis le
    jeton) — c'est ce qui rend une désactivation ou un changement de rôle immédiats, sans attendre
    l'expiration de la session (voir le module docstring). `None` si le jeton est absent, invalide,
    expiré, pointe vers un compte supprimé, ou un compte désactivé."""
    from testpilot.store.repositories import UserRepo

    jeton = lire_jeton(request.cookies.get(COOKIE))
    if jeton is None:
        return None
    user_id, version_jeton, _nom = jeton
    utilisateur = UserRepo(conn).get(user_id)
    if (utilisateur is None or not utilisateur.get("is_active")
            or int(utilisateur.get("session_version", 1)) != version_jeton):
        return None
    if (utilisateur.get("must_change_password") and utilisateur.get("password_expires_at")
            and utilisateur["password_expires_at"] <= time.time()):
        return None
    return utilisateur


def chemin_libre(chemin: str) -> bool:
    """Le verrou protège l'API ET le frontend : une page servie sans session ne montre rien
    d'utile, mais laisser passer les fichiers statiques évite un écran blanc au lieu du
    formulaire de connexion."""
    if chemin in _LIBRES:
        return True
    return not chemin.startswith("/api/")


def ecriture_bloquee(role: str, method: str, chemin: str) -> bool:
    """Le rôle `lecture_seule` ne doit RIEN écrire, nulle part — vérifié UNE FOIS ici plutôt que
    route par route (ça couvre aussi toute route future qui oublierait de se gater elle-même).
    Exception étroite : `_ECRITURES_TOUJOURS_AUTORISEES` (changer son propre mot de passe)."""
    return (not role_suffisant(role, ROLE_TESTEUR)
            and method in METHODES_ECRITURE
            and chemin.startswith("/api/")
            and chemin not in _LIBRES
            and chemin not in _ECRITURES_TOUJOURS_AUTORISEES)


def require_role(minimum: str):
    """Dépendance FastAPI : refuse (403) si `request.state.user` (posé par le middleware) n'a pas
    au moins ce rôle. Réservé aux DEUX planchers AU-DESSUS de `testeur` (gestion des comptes =
    admin, édition d'un script généré = dev) — le plancher `testeur` lui-même est déjà appliqué
    partout par le middleware (`ecriture_bloquee`), pas route par route."""
    def dependance(request: Request) -> dict:
        utilisateur = getattr(request.state, "user", None)
        if utilisateur is None or not role_suffisant(utilisateur["role"], minimum):
            raise HTTPException(status_code=403, detail="droits insuffisants")
        return utilisateur
    return dependance


def _role_effectif_projet_legacy(conn, utilisateur: dict, project_id: int) -> str:
    """Résolution historique conservée pendant la transition et les tests de parité."""
    from testpilot.store.repositories import ProjectAccessRepo, ProjectGroupAccessRepo

    repo = ProjectAccessRepo(conn)
    exception = repo.override_for_user(project_id, utilisateur["id"])
    if exception is not None:
        return exception
    roles_groupes = ProjectGroupAccessRepo(conn).roles_for_user(project_id, utilisateur["id"])
    if roles_groupes:
        # Une attribution « rôle global » est résolue membre par membre. Plusieurs groupes se
        # cumulent : le plus haut niveau gagne ; `no_access` n'accorde simplement aucun droit.
        resolus = [utilisateur["role"] if role == "" else role for role in roles_groupes]
        return max(resolus, key=niveau)
    defaut = repo.default_access(project_id)
    if defaut:
        return defaut
    return utilisateur["role"]


def role_effectif_projet(conn, utilisateur: dict, project_id: int) -> str:
    """Le rôle qui s'applique VRAIMENT à ce compte sur CE projet (migration 34) —
    ordre de résolution, du plus spécifique au plus général :

    `project_member` est désormais l'autorité. Pendant la transition, la décision historique est
    recalculée et toute divergence est journalisée comme une erreur. Un compte authentifié réel
    absent de la table des membres n'a aucun accès.
    """
    from testpilot.store.repositories import ProjectMemberRepo, UserRepo

    # Les tests API historiques injectent un Admin synthétique id=0 sans ligne en base. Ce repli
    # ne peut pas arriver en production : le middleware n'authentifie qu'un `user` réellement lu.
    if UserRepo(conn).get(utilisateur["id"]) is None:
        return _role_effectif_projet_legacy(conn, utilisateur, project_id)

    ancien = _role_effectif_projet_legacy(conn, utilisateur, project_id)
    nouveau = ProjectMemberRepo(conn).effective_role(project_id, utilisateur["id"])
    if nouveau != ancien:
        logger.error(
            "[accès] divergence ProjectMember user=%s projet=%s nouveau=%s legacy=%s",
            utilisateur["id"], project_id, nouveau, ancien,
        )
    # La résolution dynamique devient l'autorité dès l'arrivée des groupes. `project_member`
    # reste la projection utilisée par l'écran historique et son écart demeure journalisé.
    return ancien


def require_project_access(project_id: int, request: Request, conn=Depends(get_conn)) -> str:
    """Dépendance FastAPI, pour les routes qui portent `project_id` DIRECTEMENT dans leur chemin.
    Les routes plus profondes (cas/section/exécution/campagne...) ont leur propre dépendance,
    `require_project_access_depuis()` ci-dessous (2026-08-11) — même contrat, chemin différent.

    - **404**, jamais 403, si le rôle effectif est `no_access` : un projet sans accès doit se
      comporter comme s'il n'existait pas — le confirmer par un 403 serait la même fuite que
      distinguer « mot de passe faux » de « compte inconnu » à la connexion.
    - **403** si écriture demandée et le rôle effectif est sous Testeur.

    Rend le rôle effectif : la route s'en sert directement, sans le recalculer.
    """
    utilisateur = getattr(request.state, "user", None)
    if utilisateur is None:
        raise HTTPException(status_code=401, detail="session requise")

    role = role_effectif_projet(conn, utilisateur, project_id)
    if role == ACCES_PROJET_REFUSE:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not role_suffisant(role, ROLE_TESTEUR) and request.method in METHODES_ECRITURE:
        raise HTTPException(status_code=403, detail="droits insuffisants")
    return role


def require_project_role(minimum: str):
    """Exige un niveau précis dans le projet, y compris pour un rôle global moins élevé.

    Cette garde couvre les opérations d'administration du projet (identité, suppression,
    exploration) qui ne doivent pas devenir accessibles à tout Testeur simplement parce qu'il
    possède le droit d'écrire des cas.
    """
    def dependance(project_id: int, request: Request, conn=Depends(get_conn)) -> str:
        role = require_project_access(project_id, request, conn)
        if not role_suffisant(role, minimum):
            raise HTTPException(status_code=403, detail="droits insuffisants")
        return role
    return dependance


# ── Routes profondes (2026-08-11) — fermer le trou documenté ci-dessus depuis la migration 31 ──
#
# Une route comme `GET /api/cases/{case_id}` ne porte pas `project_id` dans son chemin : sans ce
# qui suit, un compte à qui l'accès à un projet est retiré (`no_access`, ou forcé en Lecture
# seule) pouvait continuer de lire/écrire/exécuter — voire PURGER DÉFINITIVEMENT via la corbeille
# — tout ce qui appartient à ce projet, tant qu'il connaissait déjà l'identifiant profond (cas,
# section, exécution, campagne, résultat, pièce jointe, job de génération). `require_role`/
# `ecriture_bloquee` ne voient qu'un rôle GLOBAL, jamais la surcharge par projet.
#
# Même contrat EXACT que `require_project_access` (404 si `no_access`, jamais 403 ; 403 si
# écriture et rôle effectif sous Testeur) — repris tel quel, jamais réinventé.

def require_project_access_depuis(id_param: str, resolveur):
    """Variante de `require_project_access` pour un chemin qui porte un identifiant PROFOND
    (`case_id`, `module_id`, `group_id`...) plutôt que `project_id` directement.

    `resolveur(conn, id_brut) -> int | None` fait remonter cet identifiant jusqu'au projet.
    `id_brut` est la valeur BRUTE (texte) du paramètre de chemin — jamais casté ici : `job_id`
    (generation_job) est une chaîne, les autres des entiers, et c'est au résolveur de savoir
    lequel il attend, pas à cette fonction générique.

    Lue depuis `request.path_params` (pas un paramètre typé comme `require_project_access`) parce
    que le NOM du paramètre change d'une route à l'autre — un paramètre `project_id: int` fixe ne
    peut pas s'adapter à `case_id`, `module_id`, etc. sans une fonction par identifiant.

    Un resolveur qui rend `None` est traité comme un **refus fermé** : soit la ressource n'existe
    pas, soit elle est orpheline et aucune isolation par projet ne peut être prouvée. Dans les deux
    cas, l'API répond 404. Un rôle global, même Admin, ne doit jamais servir de repli lorsqu'une
    ressource métier sensible n'a pas de périmètre d'autorisation vérifiable."""
    def dependance(request: Request, conn=Depends(get_conn)) -> str | None:
        utilisateur = getattr(request.state, "user", None)
        if utilisateur is None:
            raise HTTPException(status_code=401, detail="session requise")

        project_id = resolveur(conn, request.path_params.get(id_param))
        if project_id is None:
            raise HTTPException(status_code=404, detail="ressource introuvable")

        role = role_effectif_projet(conn, utilisateur, project_id)
        if role == ACCES_PROJET_REFUSE:
            raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
        if not role_suffisant(role, ROLE_TESTEUR) and request.method in METHODES_ECRITURE:
            raise HTTPException(status_code=403, detail="droits insuffisants")
        return role
    return dependance


def require_project_role_depuis(id_param: str, resolveur, minimum: str):
    """Variante profonde de :func:`require_project_role`."""
    acces = require_project_access_depuis(id_param, resolveur)

    def dependance(request: Request, conn=Depends(get_conn)) -> str | None:
        role = acces(request, conn)
        if role is not None and not role_suffisant(role, minimum):
            raise HTTPException(status_code=403, detail="droits insuffisants")
        return role
    return dependance


def project_id_depuis_case(conn, case_id) -> int | None:
    from testpilot.store.repositories import CaseRepo
    try:
        cas = CaseRepo(conn).get(int(case_id))
    except (TypeError, ValueError):
        return None
    return (cas or {}).get("project_id")


def project_id_depuis_module(conn, module_id) -> int | None:
    from testpilot.store.repositories import ModuleRepo
    try:
        module = ModuleRepo(conn).get(int(module_id))
    except (TypeError, ValueError):
        return None
    return (module or {}).get("project_id")


def project_id_depuis_group(conn, group_id) -> int | None:
    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return None
    ligne = conn.execute(
        "SELECT m.project_id AS project_id FROM case_group g"
        " JOIN module m ON g.module_id = m.id WHERE g.id = ?", (group_id,)).fetchone()
    return ligne["project_id"] if ligne else None


def project_id_depuis_execution(conn, execution_id) -> int | None:
    try:
        execution_id = int(execution_id)
    except (TypeError, ValueError):
        return None
    ligne = conn.execute(
        "SELECT m.project_id AS project_id FROM execution e"
        " JOIN test_case tc ON e.test_case_id = tc.id"
        " JOIN module m ON tc.module_id = m.id WHERE e.id = ?", (execution_id,)).fetchone()
    return ligne["project_id"] if ligne else None


def project_id_depuis_run(conn, run_id) -> int | None:
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        return None
    ligne = conn.execute("SELECT project_id FROM test_run WHERE id = ?", (run_id,)).fetchone()
    return ligne["project_id"] if ligne else None


def project_id_depuis_result(conn, result_id) -> int | None:
    try:
        result_id = int(result_id)
    except (TypeError, ValueError):
        return None
    ligne = conn.execute(
        "SELECT r.project_id AS project_id FROM test_result tr"
        " JOIN test_run r ON tr.run_id = r.id WHERE tr.id = ?", (result_id,)).fetchone()
    return ligne["project_id"] if ligne else None


def project_id_depuis_attachment(conn, attachment_id) -> int | None:
    try:
        attachment_id = int(attachment_id)
    except (TypeError, ValueError):
        return None
    ligne = conn.execute(
        "SELECT r.project_id AS project_id FROM result_attachment a"
        " JOIN test_result tr ON a.result_id = tr.id"
        " JOIN test_run r ON tr.run_id = r.id WHERE a.id = ?", (attachment_id,)).fetchone()
    return ligne["project_id"] if ligne else None


def project_id_depuis_job(conn, job_id) -> int | None:
    """`job_id` (generation_job) est une chaîne — jamais castée en entier, contrairement aux
    autres résolveurs."""
    from testpilot.store.repositories import GenerationJobRepo
    if not job_id:
        return None
    job = GenerationJobRepo(conn).get(str(job_id))
    if not job or not job.get("module_id"):
        return None
    return project_id_depuis_module(conn, job["module_id"])


def journaliser_l_etat_au_demarrage() -> None:
    logger.info("[accès] connexion obligatoire (comptes utilisateurs, 4 rôles).")
