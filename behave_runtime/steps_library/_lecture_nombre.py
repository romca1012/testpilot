"""Lecture normalisée d'un nombre AFFICHÉ et comparaison à tolérance DÉCLARÉE (lot Q4, D21 — outils 1 et 2).

Pourquoi. Un montant affiché s'écrit « 1 234,50 € », « 1,234.50 », « 1.234,50 » ou « (12,50) » selon la langue et
l'application. Le comparer comme du texte (« la page contient "129,51" ») ne prouve ni que c'est le bon champ ni que la
valeur est la bonne. Ce module lit le texte en un NOMBRE, ou REFUSE de le lire : une lecture ambiguë (« 1,234 » : mille
deux cent trente-quatre ou un virgule deux cent trente-quatre ?) n'est jamais devinée — deviner donnerait un faux
`conforme` ou un faux `non_conforme` selon le hasard.

Module PUR (aucune I/O, aucun navigateur, aucun LLM) : importable depuis le sous-processus Behave comme depuis les tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_ESPACES = "     "  # insécable, fine insécable, fine, tabulaire, espace
_MOINS = "−–‒"  # signe moins typographique, tirets
_DEVISES = {  # symbole ou code lu -> code ISO (ou usuel) ; le plus long est cherché d'abord
    "€": "EUR", "EUR": "EUR", "$": "USD", "USD": "USD", "£": "GBP", "GBP": "GBP", "CHF": "CHF",
    "F CFA": "XOF", "FCFA": "XOF", "CFA": "XOF", "XOF": "XOF", "XAF": "XAF",
}


class LectureImpossible(ValueError):
    """Le texte n'est pas un nombre, ou plusieurs lectures sont possibles. Le message dit POURQUOI (jamais deviné)."""


@dataclass(frozen=True)
class NombreLu:
    valeur: Decimal
    devise: str | None = None
    pourcentage: bool = False
    texte_source: str = ""


def _groupes_de_trois(texte: str, sep: str) -> bool:
    return re.fullmatch(r"\d{1,3}(?:" + re.escape(sep) + r"\d{3})+", texte) is not None


def lire_nombre(texte: str, *, separateur_decimal: str | None = None) -> NombreLu:
    """Texte affiché -> `NombreLu`. `separateur_decimal` ('.' ou ',') lève l'ambiguïté quand l'appelant la connaît (langue)."""
    if separateur_decimal not in (None, ".", ","):
        raise ValueError("separateur_decimal doit être '.', ',' ou None")
    brut = str(texte)
    reste = brut.strip()
    if not reste:
        raise LectureImpossible("texte vide")

    negatif = False
    if reste.startswith("(") and reste.endswith(")"):  # convention comptable : (12,50) = -12,50
        negatif, reste = True, reste[1:-1].strip()

    devise = None
    for symbole in sorted(_DEVISES, key=len, reverse=True):
        if symbole in reste:
            devise = devise or _DEVISES[symbole]
            reste = reste.replace(symbole, " ")
    pourcentage = "%" in reste
    reste = reste.replace("%", " ")

    for c in _MOINS:
        reste = reste.replace(c, "-")
    reste = reste.strip(_ESPACES)
    if reste.startswith("-"):
        negatif, reste = True, reste[1:]
    elif reste.startswith("+"):
        reste = reste[1:]
    for c in _ESPACES + "'’":  # séparateurs de milliers sans ambiguïté
        reste = reste.replace(c, "")

    if not re.fullmatch(r"[\d.,]+", reste) or not re.search(r"\d", reste):
        raise LectureImpossible(f"« {brut} » n'est pas un nombre")

    valeur = _decimal(reste, separateur_decimal, brut)
    return NombreLu(-valeur if negatif else valeur, devise, pourcentage, brut)


def _decimal(reste: str, impose: str | None, brut: str) -> Decimal:
    points, virgules = reste.count("."), reste.count(",")
    if points and virgules:  # le DERNIER séparateur est le décimal, l'autre ne peut être que des milliers
        decimal = "." if reste.rfind(".") > reste.rfind(",") else ","
        milliers = "," if decimal == "." else "."
        entier, _, fraction = reste.rpartition(decimal)
        if milliers in fraction or not _groupes_de_trois(entier, milliers):
            raise LectureImpossible(f"« {brut} » : séparateurs de milliers incohérents")
        return _construire(entier.replace(milliers, ""), fraction, brut)

    present = "." if points else "," if virgules else None
    if present is None:
        return _construire(reste, "", brut)
    if reste.count(present) > 1:  # « 1.234.567 » : forcément des milliers
        if impose == present:
            raise LectureImpossible(f"« {brut} » : plusieurs séparateurs décimaux '{present}'")
        if not _groupes_de_trois(reste, present):
            raise LectureImpossible(f"« {brut} » : groupes de milliers incohérents")
        return _construire(reste.replace(present, ""), "", brut)

    entier, _, fraction = reste.partition(present)
    if impose is not None:
        if impose == present:
            return _construire(entier, fraction, brut)
        return _construire(entier + fraction, "", brut)  # l'autre est le décimal : celui-ci sépare des milliers
    if len(fraction) == 3 and 1 <= len(entier) <= 3 and entier != "0":
        raise LectureImpossible(
            f"« {brut} » est ambigu : {entier}{fraction} (milliers) ou {entier}.{fraction} (décimales) ? "
            "Préciser le séparateur décimal.")
    return _construire(entier, fraction, brut)


def _construire(entier: str, fraction: str, brut: str) -> Decimal:
    try:
        return Decimal(f"{entier or '0'}.{fraction}" if fraction else (entier or "0"))
    except InvalidOperation as erreur:
        raise LectureImpossible(f"« {brut} » n'est pas un nombre") from erreur


# ── Comparaison à tolérance DÉCLARÉE ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Comparaison:
    ok: bool
    message: str


def comparer(lu: Decimal | NombreLu, attendu, *, tolerance=None, source: str = "") -> Comparaison:
    """`lu` égal à `attendu` à `tolerance` près. Sans tolérance : égalité EXACTE (le message dit « exacte »).

    Une tolérance non nulle EXIGE sa source (« arrondi de la devise », « demandé par la spec »…) : un écart accepté doit
    toujours pouvoir être justifié (D19). Un `float` est converti par sa représentation texte, jamais par sa valeur binaire."""
    valeur_lue = lu.valeur if isinstance(lu, NombreLu) else lu
    cible = _en_decimal(attendu)
    marge = Decimal(0) if tolerance is None else _en_decimal(tolerance)
    if marge < 0:
        raise ValueError("la tolérance ne peut pas être négative")
    if marge > 0 and not source.strip():
        raise ValueError("une tolérance non nulle doit déclarer sa source")
    ecart = abs(valeur_lue - cible)
    qualif = "exacte, aucune tolérance" if marge == 0 else f"± {marge} — {source.strip()}"
    return Comparaison(ecart <= marge, f"attendu {cible} ({qualif}), lu {valeur_lue}")


def _en_decimal(valeur) -> Decimal:
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))
