"""Verrou d'accès de l'instance + identité du testeur (lot 2 du déploiement, 2026-07-24).

**Ce que c'est.** Un **mot de passe unique d'instance**, partagé par l'équipe, plus un **nom
libre** saisi à l'arrivée. Rien de plus.

**Ce que ce n'est PAS** — et il faut le dire, parce que la confusion serait dangereuse :

- ce n'est **pas un système de comptes** (hors V1, §8 du brief) : pas d'inscription, pas de mot de
  passe par personne, pas de rôles, pas de permissions ;
- le nom saisi n'est **pas une authentification** : il n'est pas vérifié, chacun écrit ce qu'il
  veut. Il répond à « qui a créé ce cas ? » sur un serveur partagé, **pas** à « qui a le droit
  de… ». On l'affiche donc comme une signature déclarée, jamais comme une identité prouvée.

**Pourquoi malgré tout.** L'outil pilote un navigateur contre l'application testée et lit ses
rapports. Joignable sur un réseau sans le moindre verrou, il offre les deux à qui atteint le port.
Un secret partagé est faible ; c'est **infiniment** plus que rien, et ça se livre aujourd'hui,
tandis que les comptes sont un chantier qui ne doit pas retarder le déploiement.

**Sans mot de passe configuré, aucun verrou** : c'est le mode poste de développement, celui qui
existait avant. Le démarrage le dit dans les journaux plutôt que de laisser croire à une
protection absente de la configuration.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from fastapi import Request

from testpilot import config

logger = logging.getLogger(__name__)

COOKIE = "testpilot_session"
_HEADER_UTILISATEUR = "X-TestPilot-User"

# Chemins toujours ouverts : l'écran de connexion doit pouvoir se charger et se poster.
_LIBRES = ("/api/health", "/api/auth/login", "/api/auth/session")


def verrou_actif() -> bool:
    return bool((config.ACCESS_PASSWORD or "").strip())


def _cle() -> bytes:
    """Clé de signature des sessions — dérivée du mot de passe d'instance.

    Conséquence VOULUE : changer le mot de passe **invalide toutes les sessions ouvertes**. C'est
    le seul geste dont dispose l'équipe quand quelqu'un part ou qu'un secret a fuité ; il doit
    donc mordre immédiatement, sans redémarrage ni purge.
    """
    return hashlib.sha256((config.ACCESS_PASSWORD or "").encode("utf-8")).digest()


def _signer(charge: str) -> str:
    return hmac.new(_cle(), charge.encode("utf-8"), hashlib.sha256).hexdigest()


def creer_jeton(nom: str) -> str:
    """Jeton de session : `expiration.nom.signature`. Signé, donc non falsifiable sans la clé."""
    expire = int(time.time()) + config.SESSION_DAYS * 86400
    nom_propre = (nom or "").replace(".", " ").strip()[:60]
    charge = f"{expire}.{nom_propre}"
    return f"{charge}.{_signer(charge)}"


def lire_jeton(jeton: str | None) -> str | None:
    """Le nom porté par un jeton valide, ou None. Jamais d'exception : une entrée douteuse est
    une session absente, pas une panne."""
    if not jeton:
        return None
    try:
        expire_txt, nom, signature = jeton.split(".", 2)
        charge = f"{expire_txt}.{nom}"
        if not hmac.compare_digest(signature, _signer(charge)):
            return None
        if int(expire_txt) < time.time():
            return None
        return nom
    except (ValueError, AttributeError):
        return None


def mot_de_passe_valide(propose: str) -> bool:
    """Comparaison à temps constant — une comparaison naïve laisse mesurer le secret."""
    return hmac.compare_digest((propose or "").encode("utf-8"),
                               (config.ACCESS_PASSWORD or "").encode("utf-8"))


def utilisateur_de(request: Request) -> str:
    """Le nom du testeur : la session d'abord, puis l'en-tête (client sans cookie), sinon vide.

    Vide se lit « on ne sait pas » et **doit rester vide** : inventer « admin » ou « ui » ferait
    signer un cas par quelqu'un qui n'existe pas — le motif « affiché ≠ réel » appliqué à
    l'auteur d'un test.
    """
    nom = lire_jeton(request.cookies.get(COOKIE))
    if nom:
        return nom
    return (request.headers.get(_HEADER_UTILISATEUR) or "").strip()[:60]


def chemin_libre(chemin: str) -> bool:
    """Le verrou protège l'API ET le frontend : une page servie sans session ne montre rien
    d'utile, mais laisser passer les fichiers statiques évite un écran blanc au lieu du
    formulaire de connexion."""
    if chemin in _LIBRES:
        return True
    return not chemin.startswith("/api/")


def journaliser_l_etat_au_demarrage() -> None:
    if verrou_actif():
        logger.info("[accès] verrou d'instance ACTIF (mot de passe partagé).")
    else:
        logger.warning(
            "[accès] AUCUN verrou : quiconque atteint ce port peut lancer des tests contre "
            "l'application cible et lire les rapports. Acceptable sur un poste isolé ; sur un "
            "serveur partagé, renseignez TESTPILOT_ACCESS_PASSWORD.")
