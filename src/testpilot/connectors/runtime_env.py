"""Traduction de la connexion d'un PROJET en variables d'environnement pour le runtime.

Le harnais Behave (``behave_runtime/environment.py``) lit sa connexion dans l'environnement
(``ODOO_URL``/``ODOO_DB``/…). Le projet portant désormais le connecteur et ses paramètres
(décision 0005), ce module fait le pont : projet → variables d'environnement du sous-processus.

Règles :
- le mapping dépend du ``connector_type`` (architecture multi-connecteurs, §8) ;
- une valeur vide n'est PAS propagée : le runtime retombe alors sur la config globale ;
- ``ODOO_ENV`` n'est jamais produit ici — le garde-fou anti-production reste intact.

⚠️ **Le repli sur la config globale est un PIÈGE quand il est silencieux** (levé le 2026-07-24).
Un projet sans connexion saisie faisait tourner ses tests contre ``ODOO_URL`` par défaut —
``localhost:10017`` / ``admin``. L'interface affichait un projet, le navigateur en testait un
autre, **et rien à l'écran ne pouvait le trahir** : une campagne entière pouvait être verte
contre la mauvaise application. C'est le seul défaut connu qui rend les résultats faux **sans
laisser de trace** ; tous les autres se voient.

D'où la séparation :

- :func:`project_env` reste le **traducteur pur** (projet → variables), sans jugement. La CLI
  l'utilise ainsi : là, la connexion vient délibérément du ``.env`` de la machine.
- :func:`verifier_connexion` est la **garde**, appelée par l'API avant tout geste qui touche
  l'application d'un projet (lancer un cas, lancer une campagne, explorer, générer). Elle
  **refuse** au lieu de retomber en silence.
"""

from __future__ import annotations

import json
import logging

from testpilot.connectors import auth_strategie as _auth
from testpilot.connectors import oracle_config as _oracle
from testpilot.connectors.contexte_navigateur import depuis_projet

logger = logging.getLogger(__name__)

# Lot 07b-1 (D8) : les comptes SECONDAIRES du projet, `[{"label", "username", "password"}]` en JSON, pour le sous-processus Behave SEUL
# (le step « je me connecte en tant que "<libellé>" » s'y résout). Le compte principal reste `ODOO_USER` / `WEB_USER`.
ENV_COMPTES = "TESTPILOT_COMPTES"

# Sous-lot D (« Enregistrement assisté du chemin de connexion ») : la séquence confirmée qui
# franchit un écran intercalé avant le formulaire de connexion, `[{"role", "name"}]` en JSON —
# SEUL le connecteur `web` la consomme (voir `_web_helpers.rejouer_sequence_connexion`).
ENV_LOGIN_RECORDING = "TESTPILOT_LOGIN_RECORDING"

# Extension (2026-09-30) : le descripteur du formulaire de connexion lui-même (3 clics guidés),
# `{"champ_identifiant", "champ_mdp", "bouton_soumission"}` en JSON — SEUL le connecteur `web` la
# consomme (voir `_web_helpers.remplir_et_soumettre_formulaire_connexion`).
ENV_LOGIN_FORM = "TESTPILOT_LOGIN_FORM"

# connector_type → {variable d'environnement: colonne du projet} — colonnes REQUISES : sans
# elles, `verifier_connexion` refuse de lancer quoi que ce soit contre cette connexion.
_MAPPINGS: dict[str, dict[str, str]] = {
    "odoo": {
        "ODOO_URL": "base_url",
        "ODOO_DB": "database",
        "ODOO_USER": "username",
        "ODOO_PASSWORD": "password",
    },
    # Connecteur web générique (2026-09-08, multi-connecteurs) : SEULE l'URL est requise — à la
    # différence d'Odoo, l'application ciblée peut très bien n'exiger aucune connexion (voir
    # `connectors/generic_web.py::_tenter_connexion_generique`, qui explore sans authentification
    # quand identifiant/mot de passe manquent).
    "web": {
        "WEB_URL": "base_url",
    },
}

# Colonnes FACULTATIVES par connecteur : transmises au runtime SI renseignées (`project_env`),
# mais jamais exigées par `verifier_connexion` — contrairement à `_MAPPINGS` ci-dessus.
_MAPPINGS_OPTIONNEL: dict[str, dict[str, str]] = {
    "web": {
        "WEB_USER": "username",
        "WEB_PASSWORD": "password",
    },
}

# Libellés MÉTIER des colonnes manquantes — le message va à un QA, pas à un développeur (§8 du
# brief : jamais un nom de colonne brut en premier plan).
_LIBELLES = {
    "base_url": "l'adresse de l'application",
    "database": "la base de données",
    "username": "l'utilisateur",
    "password": "le mot de passe",
}


class ConnexionIncomplete(Exception):
    """La connexion du projet ne permet pas de savoir contre QUOI on testerait.

    Porte la liste des éléments manquants pour que l'écran dise quoi corriger, et non un
    « impossible de lancer » sans suite.
    """

    def __init__(self, project: dict | None, manquants: list[str]):
        self.manquants = manquants
        self.project_name = (project or {}).get("name") or "ce projet"
        super().__init__(self.message())

    def message(self) -> str:
        details = ", ".join(self.manquants)
        return (f"La connexion du projet « {self.project_name} » est incomplète : {details}. "
                f"Renseignez-la dans l'écran Projets avant de lancer un test — sans elle, "
                f"l'outil ne sait pas contre quelle application il travaille.")


def verifier_connexion(project: dict | None, comptes: list[dict] | None = None,
                       sequence_connexion: list[dict] | None = None,
                       login_form: dict | None = None) -> dict[str, str]:
    """Rend les variables d'environnement du projet, ou **lève** si elles ne suffisent pas.

    Jamais de repli silencieux : mieux vaut un refus explicite qu'un résultat obtenu contre une
    application que personne n'a choisie.
    """
    if not project:
        raise ConnexionIncomplete(project, ["aucun projet rattaché"])

    connector = (project.get("connector_type") or "").lower()
    mapping = _MAPPINGS.get(connector)
    if mapping is None:
        raise ConnexionIncomplete(
            project, [f"le type de connecteur « {connector or 'non renseigné'} » n'est pas géré"])

    manquants = [_LIBELLES.get(colonne, colonne)
                 for colonne in mapping.values() if not project.get(colonne)]
    if manquants:
        raise ConnexionIncomplete(project, manquants)

    _verifier_oracle_joignable(project)
    return project_env(project, comptes, sequence_connexion, login_form)


def _config_oracle(project: dict) -> dict | None:
    """La configuration DÉCODÉE de l'oracle du projet, ou `None` (aucun oracle / type non géré ici :
    seul `http` est traité, D7 — l'oracle SQL en lecture seule est un sous-lot séparé)."""
    if (project.get("oracle_type") or "").lower() != _oracle.TYPE_HTTP or not project.get("oracle_base_url"):
        return None
    try:
        auth = json.loads(project.get("oracle_auth") or "{}") or {}
    except (ValueError, TypeError):
        auth = {}
    try:
        queries = json.loads(project.get("oracle_queries") or "[]") or []
    except (ValueError, TypeError):
        queries = []
    return {"base_url": project["oracle_base_url"], "auth": auth, "queries": queries}


def _verifier_oracle_joignable(project: dict | None) -> None:
    """Refuse (`ConnexionIncomplete`) si l'oracle du projet est configuré mais INJOIGNABLE (D7) —
    mieux vaut un refus explicite maintenant qu'un cas qui tournerait sans jamais pouvoir prouver
    `ground_truth = backend_verified` (verdict/status.py)."""
    config = _config_oracle(project or {})
    if config is None:
        return
    from testpilot.connectors.oracle_http import OracleHttp, OracleIndisponible

    try:
        OracleHttp(config["base_url"], config["auth"]).verifier_joignable()
    except OracleIndisponible as exc:
        raise ConnexionIncomplete(project, [f"l'oracle backend est injoignable ({exc})"]) from exc


def cible_de(project: dict | None) -> dict[str, str]:
    """Ce contre quoi on va tourner, pour l'INSCRIRE dans l'historique — **jamais le mot de
    passe**. Un rapport qui ne dit pas quelle application il a jugée ne prouve rien."""
    p = project or {}
    return {
        "target_url": str(p.get("base_url") or ""),
        "target_database": str(p.get("database") or ""),
        "target_username": str(p.get("username") or ""),
    }


def project_env(project: dict | None, comptes: list[dict] | None = None,
                sequence_connexion: list[dict] | None = None,
                login_form: dict | None = None) -> dict[str, str]:
    """Variables d'environnement de connexion déduites d'un projet. Vide si non applicable.

    `comptes` : les comptes secondaires (`ProjectAccountRepo.pour_runtime`), secrets déchiffrés — transmis tels quels au sous-processus,
    qui en a besoin pour se connecter. Jamais passés à la génération (elle ne reçoit que les libellés).
    `sequence_connexion` (sous-lot D) : la séquence confirmée qui franchit un écran intercalé avant
    le formulaire de connexion — voir `ENV_LOGIN_RECORDING`.
    `login_form` (extension 2026-09-30) : le descripteur du formulaire de connexion lui-même (3
    clics guidés) — voir `ENV_LOGIN_FORM`."""
    if not project:
        return {}
    connector = (project.get("connector_type") or "").lower()
    mapping = _MAPPINGS.get(connector)
    if mapping is None:
        logger.warning("[runtime] connecteur '%s' sans mapping d'environnement — "
                       "connexion globale utilisée", connector)
        return {}
    toutes_les_colonnes = {**mapping, **_MAPPINGS_OPTIONNEL.get(connector, {})}
    env = {}
    for var, column in toutes_les_colonnes.items():
        value = project.get(column)
        if value:  # vide → on laisse la config globale s'appliquer
            env[var] = str(value)
    # Lot 07c (C3) : le contexte navigateur est TOUJOURS transmis, défauts compris — un navigateur qui retomberait sur la langue
    # et le fuseau de la machine changerait de comportement d'un poste à l'autre. Jamais « vide → config globale » ici.
    env.update(depuis_projet(project).env())
    if comptes:
        env[ENV_COMPTES] = json.dumps(
            [{"label": c["label"], "username": c["username"], "password": c["password"]} for c in comptes],
            ensure_ascii=False)
    # Lot 07b-2 (C2) : la stratégie de connexion du compte PRINCIPAL — SEUL le connecteur `web` la consomme (avant_all du
    # harnais). `formulaire` (défaut) ne change rien au comportement d'avant ce lot une fois traduit.
    if connector == "web":
        env[_auth.ENV_STRATEGIE] = str(project.get("auth_strategie") or _auth.FORMULAIRE)
        if project.get("totp_secret"):
            env[_auth.ENV_TOTP_SECRET] = str(project["totp_secret"])
        if project.get("injected_session"):
            env[_auth.ENV_INJECTED_SESSION] = str(project["injected_session"])
    # Essai (2026-09-30) : contrairement aux 3 variables ci-dessus (des concepts propres à la
    # stratégie du connecteur `web`), le chemin de connexion enregistré est un mécanisme UI
    # générique (franchir un écran, remplir un formulaire) qui ne présuppose rien de spécifique au
    # connecteur — ouvert à `odoo` ICI pour permettre l'essai demandé, consommé UNIQUEMENT par
    # `odoo_login.py::playwright_login` si le projet a effectivement enregistré quelque chose
    # (sinon `None`/`[]`, comportement historique inchangé pour Odoo).
    if connector in ("web", "odoo"):
        if sequence_connexion:
            env[ENV_LOGIN_RECORDING] = json.dumps(sequence_connexion, ensure_ascii=False)
        if login_form:
            env[ENV_LOGIN_FORM] = json.dumps(login_form, ensure_ascii=False)
    # Lot 07e (D7) : l'oracle backend n'est pas propre au connecteur `web` (un projet Odoo peut lui
    # aussi vouloir recouper contre une API tierce) — transmis dès qu'il est configuré, quel que
    # soit le connecteur, contrairement à la stratégie d'auth ci-dessus (propre au navigateur).
    config = _config_oracle(project)
    if config is not None:
        env[_oracle.ENV_ORACLE] = json.dumps(config, ensure_ascii=False)
    return env


def env_du_projet(conn, project: dict | None) -> dict[str, str]:
    """`project_env` AVEC les comptes secondaires, la séquence de connexion (sous-lot D) ET le
    formulaire de connexion (extension 2026-09-30) du projet — le point d'entrée des appelants
    qui lancent un run Behave."""
    from testpilot.store import project_login_recordings
    from testpilot.store.repositories import ProjectAccountRepo

    if not project or not project.get("id"):
        return project_env(project)
    comptes = ProjectAccountRepo(conn).pour_runtime(project["id"])
    sequence = project_login_recordings.lire(conn, project["id"])
    login_form = project_login_recordings.lire_formulaire(conn, project["id"])
    return project_env(project, comptes, sequence, login_form)


def verifier_connexion_du_projet(conn, project: dict | None) -> dict[str, str]:
    """`verifier_connexion` (lève si la connexion est incomplète) AVEC les comptes secondaires du
    projet (D8) — pour un appelant qui a déjà `project` en main, hors du chemin `case_id` de
    `run_service.resolve_connection` (ex. une campagne de mesure ciblée sur un `--project-id`).

    Trouvé le 2026-09-30 (mesure de clôture du lot 09) : sans cette fonction, un appelant qui ne
    peut pas passer par `run_service` était tenté d'appeler `ProjectAccountRepo.pour_runtime`
    lui-même — ce que la règle structurelle D8 interdit (`tests/test_comptes_projet.py`) — et le
    correctif le plus simple sans elle (appeler `verifier_connexion(project)` sans comptes) laisse
    `TESTPILOT_COMPTES` vide en silence : le step « je me connecte en tant que » échoue en
    PRÉREQUIS MANQUANT même quand le compte existe réellement."""
    from testpilot.store import project_login_recordings
    from testpilot.store.repositories import ProjectAccountRepo

    a_un_projet = bool(project and project.get("id"))
    comptes = ProjectAccountRepo(conn).pour_runtime(project["id"]) if a_un_projet else []
    sequence = project_login_recordings.lire(conn, project["id"]) if a_un_projet else None
    login_form = project_login_recordings.lire_formulaire(conn, project["id"]) if a_un_projet else None
    return verifier_connexion(project, comptes, sequence, login_form)
