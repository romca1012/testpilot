"""Le catalogue des défauts injectables de l'application web du banc (lot Q2-b).

Pourquoi un module à part. Les défauts sont la VÉRITÉ du banc : `specs/banc_local/attendus.yaml` en dépend et un
test de cohérence vérifie que chaque code cité existe ici. Chaque défaut est INDÉPENDANT des autres et n'altère que
son propre comportement (un test le prouve) : sans cela, un cas échouant ne dirait plus quel défaut il détecte.

Module PUR : aucune I/O, aucun réseau (l'état actif est un simple ensemble protégé par un verrou).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Defaut:
    """Un défaut : son code stable, ce qu'il change, et comment on le VOIT (pour les tests d'observabilité)."""

    code: str
    description: str
    observable: str


# L'ordre est celui de la documentation ; les codes sont ceux de `attendus.yaml`, de `apps.yaml` et de TP_DEFAUTS.
CATALOGUE: dict[str, Defaut] = {
    d.code: d
    for d in (
        Defaut(
            "total_faux",
            "Le total TTC du panier et de la commande est majoré de 1 % (la ligne de TVA, elle, reste juste).",
            "la page panier / confirmation et `commandes[].total_ttc` de /__etat",
        ),
        Defaut(
            "validation_absente",
            "Le formulaire de création de client accepte un nom VIDE ; la limite de 40 caractères reste appliquée.",
            "un client sans nom apparaît dans la liste et dans `enregistrements` de /__etat",
        ),
        Defaut(
            "message_erreur_absent",
            "Le formulaire de création de client refuse (nom vide ou trop long) mais n'affiche aucun message d'erreur.",
            "le formulaire est réaffiché sans aucun élément d'erreur",
        ),
        Defaut(
            "etat_non_enregistre",
            "La confirmation d'une commande ou d'un client s'affiche comme d'habitude, mais rien n'est conservé.",
            "`commandes` / `enregistrements` de /__etat restent vides, la liste des clients aussi",
        ),
        Defaut(
            "filtre_ignore",
            "La recherche de produits ne filtre pas : tous les produits restent listés.",
            "la liste de produits pour un texte de recherche quelconque",
        ),
        Defaut(
            "login_accepte_tout",
            "Un identifiant connu est accepté avec N'IMPORTE QUEL mot de passe.",
            "la connexion avec un mot de passe erroné mène à la liste des produits",
        ),
    )
}

CODES: tuple[str, ...] = tuple(CATALOGUE)


class DefautInconnu(ValueError):
    """Un code de défaut qui n'existe pas au catalogue (faute de frappe : on refuse plutôt que d'ignorer)."""


def analyser(valeur: str | list[str] | tuple[str, ...] | None) -> frozenset[str]:
    """Une liste « a,b,c » (variable TP_DEFAUTS) ou une liste de codes → l'ensemble des codes, validés.

    Un code inconnu lève `DefautInconnu` : ignorer silencieusement une faute de frappe ferait croire qu'un défaut est
    actif alors que l'application est saine (un faux « défaut non détecté » dans la mesure).
    """
    if valeur is None:
        return frozenset()
    morceaux = valeur.split(",") if isinstance(valeur, str) else list(valeur)
    codes = {m.strip() for m in morceaux if str(m).strip()}
    inconnus = sorted(codes - set(CODES))
    if inconnus:
        raise DefautInconnu(f"défaut(s) inconnu(s) : {', '.join(inconnus)} (connus : {', '.join(CODES)})")
    return frozenset(codes)


class DefautsActifs:
    """L'ensemble des défauts actifs, modifiable à chaud (`POST /__defauts`) depuis plusieurs threads."""

    def __init__(self, codes: frozenset[str] = frozenset()) -> None:
        self._verrou = threading.Lock()
        self._codes = frozenset(codes)

    def remplacer(self, codes: frozenset[str]) -> None:
        with self._verrou:
            self._codes = frozenset(codes)

    def actif(self, code: str) -> bool:
        # Un code absent du catalogue est une faute du CODE de l'application, pas des données : on le dit tout de suite.
        if code not in CATALOGUE:
            raise DefautInconnu(code)
        with self._verrou:
            return code in self._codes

    def liste(self) -> list[str]:
        with self._verrou:
            return [c for c in CODES if c in self._codes]
