"""Notifications par email (2026-08-12) — prévenir l'auteur d'une campagne ou d'une automatisation
quand elle se termine, au lieu de le laisser revenir vérifier lui-même.

Portée délibérément étroite (recherche du porteur sur les réglages TestRail manquants, priorité
1 des trois retenues) : **seule la personne qui a déclenché** l'action est prévenue — pas toute
l'équipe du projet. Rien dans le produit aujourd'hui ne modélise un abonnement/« watchers », et
diffuser à tout le monde le run exploratoire d'une seule personne serait du bruit, pas un service.
Ça retombe naturellement sur `triggered_by` (migration 32) : on sait déjà QUI a déclenché, il ne
manquait que comment le joindre — `user.email` (migration 33).

Best-effort de bout en bout : un email qui échoue (SMTP indisponible, mauvais mot de passe) ne
doit JAMAIS faire échouer la campagne ou l'automatisation qui vient de se terminer — même
philosophie que `_expliquer`/`_joindre_captures` dans `run_service.py`, un geste secondaire ne
casse jamais l'appelant principal.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from testpilot.store.repositories import SettingRepo, UserRepo

logger = logging.getLogger(__name__)


def _smtp_config(conn) -> dict | None:
    """Résout les champs `smtp_*`, indépendamment de `notifications_enabled` — `None` si l'hôte
    ou l'expéditeur manquent (jamais de tentative sur une configuration à moitié remplie)."""
    reglages = SettingRepo(conn)
    host = reglages.valeur("smtp_host").strip()
    expediteur = reglages.valeur("smtp_from").strip()
    if not host or not expediteur:
        return None
    return {
        "host": host,
        "port": int(reglages.valeur("smtp_port") or "587"),
        "username": reglages.valeur("smtp_username").strip(),
        "password": reglages.valeur("smtp_password"),
        "from": expediteur,
        "use_tls": reglages.valeur("smtp_use_tls") in ("1", "true", "vrai"),
    }


def _smtp_pret(conn) -> dict | None:
    """Configuration SMTP prête à l'usage RÉEL (notifications) : `None` si désactivées, en plus
    des mêmes gardes que `_smtp_config`."""
    reglages = SettingRepo(conn)
    if reglages.valeur("notifications_enabled") not in ("1", "true", "vrai"):
        return None
    return _smtp_config(conn)


def envoyer(conn, *, destinataire: str, sujet: str, corps: str,
           config_forcee: dict | None = None) -> tuple[bool, str]:
    """Envoie un email best-effort. Rend `(succès, erreur)` — jamais d'exception qui remonte.

    `config_forcee` : passe outre `notifications_enabled` (utilisé par la route de test — un
    Admin qui teste sa configuration ne devrait pas avoir à l'activer d'abord).
    """
    destinataire = (destinataire or "").strip()
    if not destinataire:
        return False, "aucune adresse de destination"

    smtp = config_forcee if config_forcee is not None else _smtp_pret(conn)
    if smtp is None:
        return False, "notifications désactivées ou configuration SMTP incomplète"

    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = smtp["from"]
    message["To"] = destinataire
    message.set_content(corps)

    try:
        with smtplib.SMTP(smtp["host"], smtp["port"], timeout=10) as serveur:
            if smtp["use_tls"]:
                serveur.starttls()
            if smtp["username"]:
                serveur.login(smtp["username"], smtp["password"])
            serveur.send_message(message)
        return True, ""
    except Exception as exc:  # best-effort ABSOLU — jamais casser l'appelant pour un email
        logger.warning("[notification] envoi à %s en échec : %s", destinataire, exc, exc_info=True)
        return False, str(exc)


def notifier(conn, *, triggered_by: str, sujet: str, corps: str) -> None:
    """Prévient QUI a déclenché l'action, s'il a un email connu — silencieux sinon (beaucoup de
    comptes n'en auront pas au début, ce n'est pas une erreur)."""
    triggered_by = (triggered_by or "").strip()
    if not triggered_by:
        return
    compte = UserRepo(conn).get_by_username(triggered_by)
    email = (compte or {}).get("email") or ""
    if not email:
        logger.info("[notification] « %s » n'a pas d'email renseigné — rien envoyé", triggered_by)
        return
    envoyer(conn, destinataire=email, sujet=sujet, corps=corps)


def notifier_fin_de_campagne(conn, run_id: int, *, triggered_by: str) -> None:
    """Fin d'une campagne (`campaign_service.run_campaign`) — un compte-rendu court : combien de
    cas, combien ont réussi."""
    from testpilot.store.repositories import RunRepo

    run = RunRepo(conn).get(run_id)
    if run is None:
        return
    cases = RunRepo(conn).cases_with_results(run_id)
    reussis = sum(1 for c in cases if (c.get("result") or {}).get("execution_status") == "success")
    sujet = f"TestPilot — campagne « {run['name']} » terminée"
    corps = (
        f"La campagne « {run['name']} » que vous avez lancée est terminée.\n\n"
        f"{reussis} / {len(cases)} cas réussis (exécution technique).\n\n"
        f"Consultez le détail dans TestPilot, onglet Exécutions et résultats de test."
    )
    notifier(conn, triggered_by=triggered_by, sujet=sujet, corps=corps)


def tester(conn, *, destinataire: str) -> tuple[bool, str]:
    """Envoie un email de test — passe outre `notifications_enabled` : un Admin qui teste sa
    configuration ne devrait pas avoir à l'activer d'abord. Utilisé par
    `POST /api/settings/smtp/test`."""
    smtp = _smtp_config(conn)
    if smtp is None:
        return False, "configuration SMTP incomplète (hôte ou adresse d'expéditeur manquant)"
    return envoyer(
        conn, destinataire=destinataire, sujet="TestPilot — email de test",
        corps="Ceci est un email de test envoyé depuis les réglages de notification de TestPilot.\n\n"
              "Si vous le recevez, la configuration SMTP fonctionne.",
        config_forcee=smtp)


def notifier_fin_d_automatisation(conn, *, case_id: int, titre_cas: str, succes: bool,
                                  triggered_by: str) -> None:
    """Fin d'une automatisation de cas manuel (`generation_service.run_automation`)."""
    etat = "réussie" if succes else "en échec"
    sujet = f"TestPilot — automatisation de « {titre_cas} » {etat}"
    corps = (
        f"L'automatisation du cas #{case_id} « {titre_cas} » que vous avez demandée est {etat}.\n\n"
        f"Consultez le cas dans TestPilot pour le détail."
    )
    notifier(conn, triggered_by=triggered_by, sujet=sujet, corps=corps)
