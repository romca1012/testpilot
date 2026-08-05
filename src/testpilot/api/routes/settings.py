"""Réglages d'INSTANCE — aujourd'hui le seul : le compte de service (2026-08-04).

Un réglage d'instance n'appartient à aucun projet : il vaut pour toute l'installation. D'où une
route à part, et non un champ de plus sur le projet — le nom qui signe les exécutions
automatiques ne change pas selon le projet qu'on regarde.

⚠️ **Chaque réglage est rendu avec sa PROVENANCE** (`db` / `env` / `default`). Sans elle, un
exploitant qui a posé `TESTPILOT_SERVICE_ACCOUNT` et qui voit autre chose à l'écran n'a aucun
moyen de comprendre : la base l'emporte sur l'environnement, et c'est l'API qui doit le dire.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import SettingRepo

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[schemas.SettingOut])
def list_settings(conn=Depends(get_conn)):
    """Tous les réglages CONNUS, résolus — y compris ceux qu'aucune ligne de base ne porte."""
    return [schemas.SettingOut(**r) for r in SettingRepo(conn).tous()]


@router.patch("/{key}", response_model=schemas.SettingOut)
def update_setting(key: str, body: schemas.SettingPatch, request: Request,
                   conn=Depends(get_conn)):
    """Pose (ou efface) un réglage.

    Une valeur **vide efface** le réglage et rend la main à l'environnement, puis au défaut —
    c'est la seule façon de revenir en arrière sans éditer la base à la main.

    Une clé inconnue est refusée : sans cette garde, la table deviendrait un dépotoir où plus
    personne ne saurait ce qui est réellement lu (même discipline que le catalogue d'erreurs).
    """
    reglages = SettingRepo(conn)
    try:
        reglages.ecrire(key, body.value, par=access.utilisateur_de(request))
    except ValueError as exc:
        raise erreurs.ErreurMetier("requete_invalide", str(exc)) from exc
    valeur, source = reglages.resoudre(key)
    return schemas.SettingOut(key=key, value=valeur, source=source,
                              description=reglages.CLES_CONNUES[key][1])
