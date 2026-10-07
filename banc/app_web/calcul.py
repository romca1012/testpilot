"""Catalogue et calcul du panier de l'application web du banc (lot Q2-b).

Pourquoi un vrai calcul. Les valeurs calculées sont ce que le futur banc veut vérifier : un test généré doit
comparer le total affiché à une référence INDÉPENDANTE. Tout est donc en `Decimal` (jamais de flottant : 8,955 n'est pas
représentable) avec une règle d'arrondi unique et écrite dans les specs : demi-centime arrondi VERS LE HAUT.

Règle, dans l'ordre (chaque montant intermédiaire est arrondi au centime, comme sur une facture) :
    ligne        = quantité × prix unitaire
    sous-total   = somme des lignes
    remise       = arrondi(sous-total × remise% / 100)
    total HT     = sous-total − remise
    TVA          = arrondi(total HT × 18 %)
    total TTC    = total HT + TVA

Module PUR : aucune I/O. Le défaut `total_faux` n'est PAS ici : il est appliqué par le serveur, afin que cette
fonction reste la référence saine contre laquelle les tests comparent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable

TAUX_TVA = Decimal("18")
CENTIME = Decimal("0.01")
QUANTITE_MAX = 99
NOM_CLIENT_MAX = 40


@dataclass(frozen=True)
class Produit:
    ident: str
    nom: str
    prix: Decimal


PRODUITS: tuple[Produit, ...] = (
    Produit("P001", "Clavier mécanique", Decimal("49.90")),
    Produit("P002", "Souris sans fil", Decimal("24.50")),
    Produit("P003", "Écran 24 pouces", Decimal("159.00")),
    Produit("P004", "Casque audio", Decimal("79.99")),
    Produit("P005", "Câble HDMI", Decimal("9.95")),
    Produit("P006", "Tapis de souris", Decimal("12.00")),
)
PAR_IDENT: dict[str, Produit] = {p.ident: p for p in PRODUITS}


def arrondir(montant: Decimal) -> Decimal:
    """Au centime, demi-centime vers le haut (0,995 → 1,00 ; 8,955 → 8,96)."""
    return montant.quantize(CENTIME, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Totaux:
    sous_total: Decimal
    remise_pct: Decimal
    remise: Decimal
    total_ht: Decimal
    tva: Decimal
    total_ttc: Decimal


def calculer(lignes: Iterable[tuple[Decimal, int]], remise_pct: Decimal = Decimal("0")) -> Totaux:
    """Les totaux d'un panier de lignes `(prix unitaire, quantité)` — une quantité 0 vaut 0,00, sans exception."""
    sous_total = sum((arrondir(prix * quantite) for prix, quantite in lignes), Decimal("0.00"))
    remise = arrondir(sous_total * remise_pct / Decimal(100))
    total_ht = sous_total - remise
    tva = arrondir(total_ht * TAUX_TVA / Decimal(100))
    return Totaux(arrondir(sous_total), remise_pct, remise, arrondir(total_ht), tva, arrondir(total_ht + tva))


def majorer_un_pour_cent(montant: Decimal) -> Decimal:
    """Le total FAUX du défaut `total_faux` : +1 % arrondi au centime (0,00 reste 0,00)."""
    return arrondir(montant * Decimal("1.01"))


def formater_montant(montant: Decimal) -> str:
    """129,51 € — virgule décimale et espace avant le symbole, comme sur une boutique française."""
    return f"{arrondir(montant):f}".replace(".", ",") + " €"


def formater_pourcentage(pct: Decimal) -> str:
    """10 → « 10 », 12.50 → « 12,5 » (forme normalisée, sans exposant)."""
    return f"{pct.normalize():f}".replace(".", ",")


def analyser_quantite(texte: str, *, minimum: int = 1) -> int:
    """Un entier de `minimum` à 99 ; lève `ValueError` avec un message prêt à afficher sinon."""
    brut = (texte or "").strip()
    if not brut.isdigit() or not brut.isascii():
        raise ValueError(f"La quantité doit être un entier entre {minimum} et {QUANTITE_MAX}.")
    valeur = int(brut)
    if not minimum <= valeur <= QUANTITE_MAX:
        raise ValueError(f"La quantité doit être un entier entre {minimum} et {QUANTITE_MAX}.")
    return valeur


def analyser_remise(texte: str) -> Decimal:
    """Un pourcentage de 0 à 100 (virgule ou point) ; vide = 0 ; lève `ValueError` avec un message prêt à afficher."""
    brut = (texte or "").strip().replace(",", ".")
    if brut == "":
        return Decimal("0")
    message = "La remise doit être comprise entre 0 et 100."
    try:
        valeur = Decimal(brut)
    except InvalidOperation:
        raise ValueError(message) from None
    if not valeur.is_finite() or not Decimal("0") <= valeur <= Decimal("100"):
        raise ValueError(message)
    return valeur
