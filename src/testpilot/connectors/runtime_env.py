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

from testpilot.connectors.contexte_navigateur import depuis_projet

logger = logging.getLogger(__name__)

# Lot 07b-1 (D8) : les comptes SECONDAIRES du projet, `[{"label", "username", "password"}]` en JSON, pour le sous-processus Behave SEUL
# (le step « je me connecte en tant que "<libellé>" » s'y résout). Le compte principal reste `ODOO_USER` / `WEB_USER`.
ENV_COMPTES = "TESTPILOT_COMPTES"

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


def verifier_connexion(project: dict | None, comptes: list[dict] | None = None) -> dict[str, str]:
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

    return project_env(project, comptes)


def cible_de(project: dict | None) -> dict[str, str]:
    """Ce contre quoi on va tourner, pour l'INSCRIRE dans l'historique — **jamais le mot de
    passe**. Un rapport qui ne dit pas quelle application il a jugée ne prouve rien."""
    p = project or {}
    return {
        "target_url": str(p.get("base_url") or ""),
        "target_database": str(p.get("database") or ""),
        "target_username": str(p.get("username") or ""),
    }


def project_env(project: dict | None, comptes: list[dict] | None = None) -> dict[str, str]:
    """Variables d'environnement de connexion déduites d'un projet. Vide si non applicable.

    `comptes` : les comptes secondaires (`ProjectAccountRepo.pour_runtime`), secrets déchiffrés — transmis tels quels au sous-processus,
    qui en a besoin pour se connecter. Jamais passés à la génération (elle ne reçoit que les libellés)."""
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
    return env


def env_du_projet(conn, project: dict | None) -> dict[str, str]:
    """`project_env` AVEC les comptes secondaires du projet — le point d'entrée des appelants qui lancent un run Behave."""
    from testpilot.store.repositories import ProjectAccountRepo

    comptes = ProjectAccountRepo(conn).pour_runtime(project["id"]) if project and project.get("id") else []
    return project_env(project, comptes)
