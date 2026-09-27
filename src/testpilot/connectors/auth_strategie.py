"""La STRATÉGIE de connexion du compte principal d'un projet web générique (lot 07b-2, C2).

Pourquoi. Un projet `web` sans stratégie déclarée refaisait le formulaire de connexion à CHAQUE
scénario (`connexion_web_utilisateur`, lot 07a) — correct, mais lent, et incapable de couvrir un
second facteur (TOTP) ou une session déjà ouverte ailleurs (SSO d'entreprise). Le harnais Behave
(`behave_runtime/environment.py`) se connecte maintenant **une fois par run**, dans `before_all`,
selon l'une de quatre stratégies, et réutilise la session obtenue (`storage_state` Playwright)
pour chaque scénario — jusqu'à ce qu'une page la trouve invalide, auquel cas une seule
reconnexion est tentée avant `blocked` (jamais un défaut attribué à l'application).

Ne s'applique qu'au compte PRINCIPAL du projet. Les comptes secondaires (`project_account`, lot
07b-1) restent en formulaire simple, y compris quand le principal est en TOTP ou SSO — décision du
porteur, 2026-09-27.

Module PUR : aucune I/O, aucun réseau, aucun LLM (même discipline que `contexte_navigateur.py`).
"""

from __future__ import annotations

import json
import re

FORMULAIRE = "formulaire"
TOTP = "totp"
SESSION_INJECTEE = "session_injectee"
AUCUNE = "aucune"
VALEURS = (FORMULAIRE, TOTP, SESSION_INJECTEE, AUCUNE)

# Aucune valeur d'enum brute à l'écran (CONTINUITE §4.7) : libellé français, serveur ET frontend
# (le frontend porte sa propre copie, comme `LIBELLE_ROLE` — même convention que `verdict/status.py::LIBELLES_CONFIANCE`).
LIBELLES = {
    FORMULAIRE: "Formulaire de connexion",
    TOTP: "Code à usage unique (TOTP)",
    SESSION_INJECTEE: "Session déjà ouverte (jeton fourni)",
    AUCUNE: "Aucune connexion",
}

# Noms des variables d'environnement du sous-processus — DUPLIQUÉS dans `behave_runtime/environment.py` (le harnais ne dépend
# pas du paquet applicatif), même motif que `contexte_navigateur.py`.
ENV_STRATEGIE = "TESTPILOT_AUTH_STRATEGIE"
ENV_TOTP_SECRET = "TESTPILOT_TOTP_SECRET"
ENV_INJECTED_SESSION = "TESTPILOT_INJECTED_SESSION"

_TOTP_SECRET_RE = re.compile(r"^[A-Za-z2-7]+=*$")  # base32 (insensible à la casse, comme pyotp/RFC 4226)


def erreurs(auth_strategie: str, totp_secret: str, injected_session: str) -> list[str]:
    """Messages MÉTIER (jamais un nom de colonne) si la combinaison est incohérente ; vide si correcte.

    Ne valide QUE la forme (un secret TOTP mal formé, un JSON de session illisible) — jamais l'exactitude d'un secret auprès de
    l'application réelle : ça, seule une tentative de connexion réelle peut le dire (`blocked`, pas un 422 à la saisie).
    """
    if auth_strategie not in VALEURS:
        return [f"stratégie de connexion « {auth_strategie} » inconnue (attendu : {', '.join(VALEURS)})"]
    problemes = []
    if auth_strategie == TOTP and totp_secret and not _TOTP_SECRET_RE.match(totp_secret.strip().replace(" ", "")):
        problemes.append("le secret TOTP n'est pas un secret base32 valide (lettres A-Z et chiffres 2-7 seulement)")
    if auth_strategie == SESSION_INJECTEE and injected_session:
        try:
            valeur = json.loads(injected_session)
        except (ValueError, TypeError):
            problemes.append("la session fournie n'est pas un JSON valide (export `storage_state` de Playwright attendu)")
        else:
            if not isinstance(valeur, dict) or not ({"cookies", "origins"} & valeur.keys()):
                problemes.append("la session fournie ne ressemble pas à un `storage_state` Playwright "
                                 "(clés « cookies » / « origins » attendues)")
    return problemes
