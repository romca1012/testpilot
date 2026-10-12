"""Outils de décor partagés par les tests de campagnes.

Depuis le 2026-10-12, une exécution AUTOMATIQUE ne contient que les cas dotés d'un test technique. Un test qui veut un cas
jouable par la machine lui en donne un ici, comme le ferait « Automatiser avec l'IA » — sans LLM, sans navigateur.
"""

from __future__ import annotations

from testpilot import config
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo

GHERKIN_MINIMAL = "# language: fr\nFonctionnalité: décor de test\n  Scénario: nominal\n    Soit un décor\n"


def doter_d_un_test_technique(case_id: int, *, conn=None) -> int:
    """Donne au cas une version COURANTE qui porte un test technique. Rend l'identifiant de cette version.

    `conn` : la connexion du test quand il travaille directement sur le dépôt ; sans elle, la base de l'API du test
    (`config.DB_PATH`, déjà redirigée par sa fixture)."""
    propre = conn is None
    conn = conn or get_initialized_db(config.DB_PATH)
    try:
        version_id = VersionRepo(conn).create(test_case_id=case_id, spec_content="", spec_hash="decor-de-test",
                                              feature_content=GHERKIN_MINIMAL, steps_content="# steps du décor\n")
        CaseRepo(conn).set_current_version(case_id, version_id)
        conn.commit()
        return version_id
    finally:
        if propre:
            conn.close()


def creer_cas_avec_test_technique(conn, **champs) -> int:
    """`CaseRepo.create(**champs)` suivi d'un test technique : le cas « généré » des décors de campagne. Un cas créé sans
    version n'a rien que la machine puisse jouer, et n'entre donc dans aucune exécution automatique."""
    case_id = CaseRepo(conn).create(**champs)
    doter_d_un_test_technique(case_id, conn=conn)
    return case_id
