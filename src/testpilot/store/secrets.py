"""Chiffrement au repos des secrets de connexion (2026-07-24, lot 2 du déploiement).

**Le problème.** Le mot de passe de connexion d'un projet était stocké **en clair** dans SQLite.
Tolérable sur un poste de développement ; **inacceptable sur un serveur interne partagé** — le
fichier de base part dans les sauvegardes, se copie, s'ouvre avec n'importe quel outil SQLite, et
un `SELECT * FROM project` rendait les identifiants de l'application testée.

**Ce que ça protège, et ce que ça ne protège pas.** Honnêteté d'abord, puisque c'est la promesse
du produit :

- ✅ protégé : la **base au repos** — copie du fichier, sauvegarde, export, envoi par erreur ;
- ❌ non protégé : quelqu'un qui a **à la fois** la base **et** la clé (l'outil doit pouvoir
  déchiffrer pour se connecter — c'est du chiffrement réversible, pas une empreinte).

D'où la règle : la clé vit **ailleurs** que la base. Par variable d'environnement de préférence
(`TESTPILOT_SECRET_KEY`), sinon dans un fichier à part, en lecture pour le seul propriétaire.

**Format.** Une valeur chiffrée porte le préfixe ``enc:v1:``. Une valeur sans préfixe est lue
telle quelle : les bases existantes continuent de fonctionner pendant la migration, et une valeur
écrite à la main reste utilisable. Le préfixe rend le format **reconnaissable** — sans lui, on ne
saurait pas distinguer un secret chiffré d'un mot de passe qui ressemble à du base64.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFIXE = "enc:v1:"
_NOM_FICHIER_CLE = ".secret_key"


class ClefIndisponible(RuntimeError):
    """Aucune clé utilisable : on refuse de chiffrer plutôt que d'écrire un faux secret."""


def _fernet():
    """L'outil de chiffrement, ou une erreur claire si la bibliothèque manque."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dépendance déclarée dans pyproject
        raise ClefIndisponible(
            "la bibliothèque `cryptography` est absente — installez les dépendances "
            "(`pip install -e .`) : sans elle, un secret ne peut pas être chiffré") from exc
    return Fernet


def chemin_de_la_cle() -> Path:
    """Où vit la clé quand elle n'est pas fournie par l'environnement."""
    from testpilot import config

    return Path(config.DATA_DIR) / _NOM_FICHIER_CLE


def _lire_ou_creer_cle() -> bytes:
    """La clé : variable d'environnement en priorité, sinon un fichier à part, créé au besoin.

    ⚠️ **Le fichier est un compromis assumé.** Une clé posée à côté de la base protège les
    sauvegardes et les copies, pas un accès complet au serveur. La variable d'environnement est
    meilleure (la clé ne touche jamais le disque de l'application) — le déploiement la recommande,
    et ce module le rappelle dans les journaux plutôt que de laisser croire à une protection
    plus forte qu'elle n'est.
    """
    from testpilot import config

    depuis_env = (config.SECRET_KEY or "").strip()
    if depuis_env:
        return depuis_env.encode("utf-8")

    chemin = chemin_de_la_cle()
    if chemin.is_file():
        return chemin.read_bytes().strip()

    Fernet = _fernet()
    cle = Fernet.generate_key()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(cle)
    try:
        chemin.chmod(0o600)  # sans effet réel sous Windows — d'où le rappel ci-dessous
    except OSError:  # pragma: no cover - systèmes sans permissions POSIX
        pass
    logger.warning(
        "[secrets] clé de chiffrement CRÉÉE dans %s. Sur un serveur partagé, préférez la variable "
        "d'environnement TESTPILOT_SECRET_KEY : une clé rangée à côté de la base ne protège que "
        "les copies de la base, pas un accès à la machine.", chemin)
    return cle


def est_chiffre(valeur: str | None) -> bool:
    return bool(valeur) and str(valeur).startswith(_PREFIXE)


def chiffrer(valeur: str | None) -> str:
    """Chiffre une valeur. Une chaîne vide reste vide (l'absence de secret n'est pas un secret)."""
    texte = valeur or ""
    if not texte or est_chiffre(texte):
        return texte
    Fernet = _fernet()
    jeton = Fernet(_lire_ou_creer_cle()).encrypt(texte.encode("utf-8")).decode("ascii")
    return f"{_PREFIXE}{jeton}"


def dechiffrer(valeur: str | None) -> str:
    """Rend la valeur en clair. Une valeur non préfixée est rendue telle quelle (base pré-migration).

    ⚠️ **Un déchiffrement qui échoue ne rend JAMAIS le jeton chiffré comme s'il était le mot de
    passe.** Ce serait le motif « affiché ≠ réel » appliqué à l'authentification : la connexion
    échouerait avec un « mot de passe invalide » incompréhensible, alors que la vraie cause est
    une clé perdue ou changée. On rend une chaîne vide, et la garde de connexion (`verifier_
    connexion`) dira « mot de passe manquant » — ce qui envoie corriger au bon endroit.
    """
    texte = valeur or ""
    if not est_chiffre(texte):
        return texte
    Fernet = _fernet()
    from cryptography.fernet import InvalidToken

    try:
        return Fernet(_lire_ou_creer_cle()).decrypt(
            texte[len(_PREFIXE):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.error(
            "[secrets] un secret ne peut pas être déchiffré — la clé a changé ou a été perdue. "
            "Ressaisissez le mot de passe du projet dans l'écran Projets. (La valeur chiffrée "
            "n'est PAS utilisée telle quelle : elle ne serait pas le mot de passe.)")
        return ""
