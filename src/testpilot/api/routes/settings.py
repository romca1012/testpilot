"""Réglages d'INSTANCE — aujourd'hui : le compte de service et le gabarit de référence
(2026-08-04, étendu le 2026-08-11).

Un réglage d'instance n'appartient à aucun projet : il vaut pour toute l'installation. D'où une
route à part, et non un champ de plus sur le projet — le nom qui signe les exécutions
automatiques ne change pas selon le projet qu'on regarde.

⚠️ **Chaque réglage est rendu avec sa PROVENANCE** (`db` / `env` / `default`). Sans elle, un
exploitant qui a posé `TESTPILOT_SERVICE_ACCOUNT` et qui voit autre chose à l'écran n'a aucun
moyen de comprendre : la base l'emporte sur l'environnement, et c'est l'API qui doit le dire.

⚠️ **Certains réglages sont réservés à l'Admin en ÉCRITURE** (`SettingRepo.CLES_CONNUES[...][2]`)
— pas tous : le compte de service reste ouvert à Testeur+, comme le reste de l'écriture générale.
La LECTURE (`GET`) reste ouverte à tout le monde, à une exception près : un réglage **secret**
(`SettingRepo.CLES_CONNUES[...][3]`, ex. `smtp_password`, 2026-08-12) ne renvoie jamais sa vraie
valeur — même à l'Admin qui vient de la poser — seul le serveur la déchiffre pour s'en servir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from testpilot import config
from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import notification_service
from testpilot.api.routes import auth
from testpilot.store.repositories import SettingRepo

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[schemas.SettingOut])
def list_settings(conn=Depends(get_conn)):
    """Tous les réglages CONNUS, résolus — y compris ceux qu'aucune ligne de base ne porte."""
    return [schemas.SettingOut(**r) for r in SettingRepo(conn).tous()]


@router.get("/options/timezones", response_model=list[schemas.TimezoneOption])
def list_timezones():
    """Catalogue unique des fuseaux proposés par l'instance.

    Le frontend reçoit les identifiants IANA réels depuis le serveur : il ne maintient pas une
    deuxième liste susceptible de diverger de la validation backend.
    """
    return [schemas.TimezoneOption(value=value, label=label)
            for value, label in SettingRepo.FUSEAUX_HORAIRES]


@router.get("/security-status", response_model=schemas.SecurityStatusOut,
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def security_status():
    """État effectif, sans jamais renvoyer la valeur d'un secret."""
    secret_session_externe = bool((config.SESSION_SECRET or "").strip())
    secret_donnees_externe = bool((config.SECRET_KEY or "").strip())
    return schemas.SecurityStatusOut(
        password_min_length=access.MOT_DE_PASSE_LONGUEUR_MIN,
        password_hash="PBKDF2-HMAC-SHA256 (200 000 itérations)",
        session_idle_minutes=config.SESSION_IDLE_MINUTES,
        session_max_hours=config.SESSION_MAX_HOURS,
        cookie_http_only=True,
        cookie_same_site="Lax",
        cookie_secure=config.COOKIE_SECURE,
        session_secret_external=secret_session_externe,
        data_secret_external=secret_donnees_externe,
        login_max_failures=auth.LOGIN_MAX_ECHECS,
        login_window_minutes=auth.LOGIN_FENETRE_SECONDES // 60,
        production_ready=(config.COOKIE_SECURE and secret_session_externe
                          and secret_donnees_externe),
    )


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
    entree = reglages.CLES_CONNUES.get(key)
    if entree is not None and entree[2]:  # [2] = admin_only
        utilisateur = getattr(request.state, "user", None)
        if utilisateur is None or not access.role_suffisant(utilisateur["role"], access.ROLE_ADMIN):
            raise HTTPException(status_code=403, detail="droits insuffisants")
    try:
        reglages.ecrire(key, body.value, par=access.utilisateur_de(request))
    except ValueError as exc:
        raise erreurs.ErreurMetier("requete_invalide", str(exc)) from exc
    valeur, source = reglages.resoudre(key)
    secret = reglages.CLES_CONNUES[key][3]
    # ⚠️ Un réglage secret ne renvoie JAMAIS sa vraie valeur, pas même juste après l'avoir posée
    # soi-même — `resoudre()` la déchiffre pour un usage SERVEUR (ouvrir la connexion SMTP), pas
    # pour repartir dans une réponse HTTP.
    valeur_rendue = (SettingRepo.MASQUE_SECRET if valeur else "") if secret else valeur
    return schemas.SettingOut(key=key, value=valeur_rendue, source=source,
                              description=reglages.CLES_CONNUES[key][1],
                              admin_only=reglages.CLES_CONNUES[key][2], secret=secret)


@router.post("/smtp/test", response_model=schemas.SmtpTestOut,
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def tester_smtp(body: schemas.SmtpTestIn, conn=Depends(get_conn)):
    """Envoie un email de test avec la configuration SMTP ACTUELLEMENT enregistrée — sans exiger
    `notifications_enabled` au préalable (2026-08-12) : un Admin qui règle sa configuration doit
    pouvoir la vérifier avant de l'activer pour de vrai."""
    succes, erreur = notification_service.tester(conn, destinataire=body.destinataire)
    return schemas.SmtpTestOut(succes=succes, erreur=erreur)
