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

    devises_vues: list[str] = []
    for symbole in sorted(_DEVISES, key=len, reverse=True):
        devises_vues += [_DEVISES[symbole]] * reste.count(symbole)
        reste = reste.replace(symbole, " ")
    if len(devises_vues) > 1:  # deux montants collés (« 12 € 15 € », prix barré...) ne sont pas UN nombre
        raise LectureImpossible(f"« {brut} » contient plusieurs devises ou montants : un seul nombre est attendu")
    devise = devises_vues[0] if devises_vues else None
    if reste.count("%") > 1:
        raise LectureImpossible(f"« {brut} » contient plusieurs pourcentages : un seul nombre est attendu")
    pourcentage = "%" in reste
    reste = reste.replace("%", " ")

    for c in _MOINS:
        reste = reste.replace(c, "-")
    reste = reste.strip(_ESPACES)
    if reste.startswith("-"):
        negatif, reste = True, reste[1:]
    elif reste.startswith("+"):
        reste = reste[1:]
    reste = _sans_groupes_de_milliers(reste, brut)

    if not re.fullmatch(r"[\d.,]+", reste) or not re.search(r"\d", reste):
        raise LectureImpossible(f"« {brut} » n'est pas un nombre")

    valeur = _decimal(reste, separateur_decimal, brut)
    return NombreLu(-valeur if negatif else valeur, devise, pourcentage, brut)


def _sans_groupes_de_milliers(reste: str, brut: str) -> str:
    """Espaces et apostrophes ne sont admis QUE comme séparateurs de milliers (`1 234 567`, `1'234`), dans la partie entière.

    Revue du 2026-10-07 : « 10 12 » ou « 1 2 3 » (pagination), « 12 5 € » (quantité puis prix) étaient fusionnés en un seul
    nombre (1012, 123, 125) — un `Alors` aurait alors pu réussir sans que la valeur soit prouvée."""
    marques = _ESPACES + "'’"
    if not any(c in reste for c in marques):
        return reste
    coupure = min((i for i in (reste.find("."), reste.find(",")) if i >= 0), default=len(reste))
    entier, queue = reste[:coupure], reste[coupure:]
    admis = (re.fullmatch(r"\d{1,3}(?:[" + re.escape(_ESPACES) + r"]\d{3})+", entier)
             or re.fullmatch(r"\d{1,3}(?:['’]\d{3})+", entier))
    if not admis or any(c in queue for c in marques):
        raise LectureImpossible(f"« {brut} » : espaces ou apostrophes en dehors de groupes de milliers (plusieurs nombres ?)")
    for c in marques:
        entier = entier.replace(c, "")
    return entier + queue


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


def comparer(lu: Decimal | NombreLu, attendu, *, tolerance=None, source: str = "",
             devise_attendue: str | None = None, pourcentage_attendu: bool | None = None) -> Comparaison:
    """`lu` égal à `attendu` à `tolerance` près. Sans tolérance : égalité EXACTE (le message dit « exacte »).

    - Une tolérance non nulle EXIGE sa source (« arrondi de la devise », « demandé par la spec »…) : un écart accepté doit
      toujours pouvoir être justifié (D19). Elle doit être FINIE et strictement inférieure à la valeur attendue (à 1 si
      l'attendu est plus petit) : une tolérance infinie ou énorme accepterait n'importe quelle valeur.
    - `source` est du texte de traçabilité, PAS une preuve : au câblage, la tolérance et sa source viennent de la spec ou de
      la devise (signal structurel), jamais d'un texte écrit par l'agent (décision 0015).
    - Unités : si `devise_attendue` / `pourcentage_attendu` sont donnés et que `lu` est un `NombreLu` qui les contredit, la
      comparaison ÉCHOUE (5 $ n'est pas 5 €, 5 % n'est pas 5). Non donnés : unité non vérifiée, et le message le dit.
    Un `float` est converti par sa représentation texte, jamais par sa valeur binaire."""
    valeur_lue = lu.valeur if isinstance(lu, NombreLu) else lu
    cible = _en_decimal(attendu)
    marge = Decimal(0) if tolerance is None else _en_decimal(tolerance)
    if not (cible.is_finite() and valeur_lue.is_finite() and marge.is_finite()):
        raise ValueError("valeur, attendu et tolérance doivent être des nombres finis")
    if marge < 0:
        raise ValueError("la tolérance ne peut pas être négative")
    if marge > 0 and not source.strip():
        raise ValueError("une tolérance non nulle doit déclarer sa source")
    if marge > 0 and marge >= max(abs(cible), Decimal(1)):
        raise ValueError(f"tolérance {marge} excessive pour l'attendu {cible} : elle accepterait presque toute valeur")
    ecart = abs(valeur_lue - cible)
    qualif = "exacte, aucune tolérance" if marge == 0 else f"± {marge} — {source.strip()}"
    unites_ok, remarques = True, []
    if isinstance(lu, NombreLu):
        if devise_attendue is not None:
            if lu.devise != devise_attendue:
                unites_ok = False
                remarques.append(f"devise lue {lu.devise or 'aucune'}, attendue {devise_attendue}")
        elif lu.devise:
            remarques.append(f"devise lue {lu.devise} non vérifiée")
        if pourcentage_attendu is not None:
            if lu.pourcentage != pourcentage_attendu:
                unites_ok = False
                remarques.append("pourcentage lu" if lu.pourcentage else "pourcentage attendu mais non lu")
        elif lu.pourcentage:
            remarques.append("pourcentage lu non vérifié")
    suite = f" ; {' ; '.join(remarques)}" if remarques else ""
    return Comparaison(ecart <= marge and unites_ok, f"attendu {cible} ({qualif}), lu {valeur_lue}{suite}")


def _en_decimal(valeur) -> Decimal:
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))
