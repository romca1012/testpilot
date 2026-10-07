"""Lot Q2-a — statistiques PURES du banc d'évaluation d'agents.

Pourquoi ce module existe : « 11 cas sur 15 sont bons » n'est pas « 73 % », et un agent qui réussit
75 % du temps à chaque essai ne réussit qu'environ 42 % du temps trois fois de suite. Ce module
calcule les chiffres du banc (pass@1, pass@k, pass^k, faux verts, faux rouges) en gardant trois
règles du dépôt :

- **pur** : aucune I/O, aucun réseau, aucun LLM — il reçoit des données, il rend des nombres ;
- **« non mesuré » n'est jamais 0** : un dénominateur nul rend `None` (jamais 0 %, jamais un
  intervalle inventé) ;
- **un résultat non concluant ne s'efface pas** : un `technical_error`, un `blocked` ou un
  `indetermine` n'est NI un faux vert NI un faux rouge, mais il est TOUJOURS compté et rapporté à
  part. Le laisser sortir du dénominateur sans le dire améliorerait le taux de faux verts en
  silence — exactement l'illusion que le banc doit empêcher.

Sources : `docs/SOURCES-DE-REFERENCE-AGENTS.md` §1 (« Demystifying evals for AI agents » : pass@k =
au moins un succès sur k essais, pass^k = tous les essais réussissent ; jeux équilibrés ;
évaluateurs déterministes d'abord). La formule de Wilson reprend la sémantique de
`intervalle_wilson` de la branche `feat-banc-web-phase1` (`scripts/banc_web.py`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

# Verdicts connus d'une exécution. Une valeur inconnue (faute de frappe, nouvelle valeur d'enum non
# propagée) lève une erreur plutôt que de tomber silencieusement hors de tout compteur.
VERDICTS = ("conforme", "non_conforme", "indetermine", "blocked", "technical_error")
# Verdicts qui tranchent : le test a réellement dit « oui » ou « non » à l'application.
VERDICTS_CONCLUANTS = ("conforme", "non_conforme")
# Verdicts qui ne tranchent pas : ni faux vert ni faux rouge, mais comptés à part.
VERDICTS_NON_CONCLUANTS = ("indetermine", "blocked", "technical_error")

VARIANTE_SAINE = "saine"


# ── Intervalle de confiance ──────────────────────────────────────────────────────────────────


def intervalle_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalle de Wilson (95 % par défaut) d'une proportion k/n, en proportions entre 0 et 1.

    Pourquoi Wilson et non l'approximation normale : sur 8 ou 15 cas, la normale sort de [0, 1] et
    rend un intervalle de largeur nulle à 0/n ou n/n, ce qui ferait croire à une certitude. `None`
    si n == 0 : aucun intervalle n'est inventé quand rien n'a été mesuré.
    """
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"proportion impossible : {k}/{n}")
    if n == 0:
        return None
    p = k / n
    denominateur = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominateur
    demi = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominateur
    return max(0.0, centre - demi), min(1.0, centre + demi)


def _taux(k: int, n: int) -> float | None:
    """Proportion k/n, ou `None` si rien n'a été mesuré (jamais 0 : « non mesuré » ≠ 0)."""
    return None if n == 0 else k / n


# ── pass@1, pass@k, pass^k ───────────────────────────────────────────────────────────────────


def _verifier_k(k: int) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError(f"k doit être un entier >= 1 (reçu : {k!r})")


def _agreger_essais(essais: Mapping[str, Sequence[bool]], k: int, reussi) -> dict:
    """Part des cas mesurés (au moins k essais) pour lesquels `reussi(k premiers essais)` est vrai.

    Un cas qui a moins de k essais n'a pas été mesuré à cette profondeur : il sort du dénominateur
    MAIS il est compté dans `non_mesures`, jamais compté comme un échec (cela ferait croire à un
    agent plus mauvais) ni comme un succès (cela le ferait croire meilleur).
    """
    _verifier_k(k)
    mesures = {cas: tentatives[:k] for cas, tentatives in essais.items() if len(tentatives) >= k}
    succes = sum(1 for tentatives in mesures.values() if reussi(tentatives))
    n = len(mesures)
    return {
        "k": succes,
        "n": n,
        "non_mesures": len(essais) - n,
        "taux": _taux(succes, n),
        "ic95": intervalle_wilson(succes, n),
    }


def pass_at_k(essais: Mapping[str, Sequence[bool]], k: int) -> dict:
    """pass@k : part des cas où AU MOINS UN des k premiers essais réussit (capacité atteignable).

    `essais` : `cas -> liste ordonnée de bool` (un bool par essai, dans l'ordre où ils ont été joués).
    Rend `{"k": cas réussis, "n": cas mesurés, "non_mesures", "taux", "ic95"}`.
    """
    return _agreger_essais(essais, k, lambda tentatives: any(tentatives))


def pass_hat_k(essais: Mapping[str, Sequence[bool]], k: int) -> dict:
    """pass^k : part des cas où TOUS les k premiers essais réussissent (fiabilité exigée).

    C'est la mesure qui compte pour un produit : l'utilisateur lance le cas à chaque fois, il ne
    choisit pas le meilleur de k essais. Même forme de résultat que `pass_at_k`.
    """
    return _agreger_essais(essais, k, lambda tentatives: all(tentatives))


def pass_at_1(essais: Mapping[str, Sequence[bool]]) -> dict:
    """pass@1 : part des cas dont le PREMIER essai réussit (les essais suivants ne comptent pas)."""
    return pass_at_k(essais, 1)


# ── Faux verts et faux rouges ────────────────────────────────────────────────────────────────


def _valider(enregistrement: Mapping[str, str]) -> None:
    for champ in ("attendu", "obtenu"):
        valeur = enregistrement.get(champ)
        if valeur not in VERDICTS:
            raise ValueError(
                f"{champ} inconnu {valeur!r} (cas {enregistrement.get('cas')!r}) ; "
                f"valeurs admises : {', '.join(VERDICTS)}"
            )
    if not enregistrement.get("variante"):
        raise ValueError(f"variante absente (cas {enregistrement.get('cas')!r})")


def _indicateur(
    enregistrements: Iterable[Mapping[str, str]],
    *,
    variante_saine: bool,
    attendu: str,
    obtenu_erreur: str,
) -> dict:
    """Taux de verdicts « erreur » parmi les enregistrements visés, non concluants rapportés à part.

    Population visée : variante saine ou défectueuse selon `variante_saine`, ET `attendu` donné.
    - `n` = visés dont le verdict est concluant (conforme / non_conforme) ;
    - `k` = parmi eux, ceux dont le verdict est `obtenu_erreur` ;
    - `non_concluants` = visés dont le verdict ne tranche pas (indetermine, blocked, technical_error).
    """
    k = n = non_concluants = 0
    for enregistrement in enregistrements:
        _valider(enregistrement)
        if (enregistrement["variante"] == VARIANTE_SAINE) != variante_saine:
            continue
        if enregistrement["attendu"] != attendu:
            continue
        obtenu = enregistrement["obtenu"]
        if obtenu in VERDICTS_NON_CONCLUANTS:
            non_concluants += 1
            continue
        n += 1
        if obtenu == obtenu_erreur:
            k += 1
    return {
        "k": k,
        "n": n,
        "non_concluants": non_concluants,
        "taux": _taux(k, n),
        "ic95": intervalle_wilson(k, n),
    }


def faux_verts(enregistrements: Iterable[Mapping[str, str]]) -> dict:
    """Faux verts : variante DÉFECTUEUSE, attendu `non_conforme`, obtenu `conforme`.

    C'est le pire défaut du produit (un vert qui n'a rien prouvé, CLAUDE.md §4). Un résultat non
    concluant n'est pas un faux vert — l'application défectueuse n'a pas été déclarée saine — mais
    il est rapporté dans `non_concluants` : un taux de faux verts à 0 % obtenu avec la moitié des
    cas en `technical_error` ne prouve rien, et le lecteur doit pouvoir le voir.
    """
    return _indicateur(
        enregistrements, variante_saine=False, attendu="non_conforme", obtenu_erreur="conforme"
    )


def faux_rouges(enregistrements: Iterable[Mapping[str, str]]) -> dict:
    """Faux rouges : variante SAINE, attendu `conforme`, obtenu `non_conforme`.

    Contrepartie des faux verts : sans elle, un évaluateur qui refuse tout aurait « 0 % de faux
    verts ». C'est le jeu équilibré (variantes saines ET défectueuses) qui rend la mesure honnête.
    """
    return _indicateur(
        enregistrements, variante_saine=True, attendu="conforme", obtenu_erreur="non_conforme"
    )


# ── Présentation ─────────────────────────────────────────────────────────────────────────────


def _pourcent(proportion: float) -> str:
    """0.375 → « 37,5 » (virgule décimale française, une décimale)."""
    return f"{proportion * 100:.1f}".replace(".", ",")


def formater_taux(k: int, n: int, non_concluants: int = 0) -> str:
    """« 3/8 (37,5 %, IC95 % 13,7–69,4 %) » ; « non mesuré » si n == 0 (jamais « 0 % »).

    `non_concluants` (facultatif) ajoute « ; 2 non concluants » : un taux présenté sans le nombre de
    résultats qui n'ont pas tranché serait plus flatteur que la réalité.
    """
    mot = "non concluant" + ("s" if non_concluants > 1 else "")
    if n == 0:
        return f"non mesuré ({non_concluants} {mot})" if non_concluants else "non mesuré"
    bas, haut = intervalle_wilson(k, n)  # type: ignore[misc]  # n > 0 ici
    texte = f"{k}/{n} ({_pourcent(k / n)} %, IC95 % {_pourcent(bas)}–{_pourcent(haut)} %)"
    return f"{texte} ; {non_concluants} {mot}" if non_concluants else texte
