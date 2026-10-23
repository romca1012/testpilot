"""Étape 7 (A108, A110) : la valeur attendue d'un test, CALCULÉE au moment de le jouer — module PUR.

Le test technique désigne un calcul par son NOM, jamais par sa valeur : `Alors le nombre affiché pour "Total" vaut le résultat
calculé "Total commande"` (l'agent n'écrit jamais le chiffre attendu, même garantie que les comptes et les données de test).
Au moment de jouer, le serveur :
1. relève les calculs appelés par le test ;
2. pour CHAQUE itération, calcule la fiche RETENUE de ce nom avec les valeurs de l'itération (un élément d'entrée prend la
   valeur de la variable du même nom : `quantite` ← `{{quantite}}`) ;
3. réécrit l'appel en une variable réservée (`"{{tp_calcul_1}}"`), qui reçoit la valeur calculée, unité comprise — le test se
   joue alors avec la comparaison de nombres existante (« le nombre affiché pour … vaut … », A24 : l'unité est vérifiée).

Un calcul qui ne peut pas se faire (fiche absente ou non retenue, entrée sans valeur, division par zéro) : le test n'est PAS
joué (« bloqué », la raison dite) — jamais une valeur de repli, jamais un verdict sur un calcul qui n'a pas eu lieu.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from testpilot.parametres import calcul

PREFIXE = "tp_calcul_"      # réservé : jamais un nom de variable du projet
_APPEL = re.compile(r'le résultat calculé "([^"\r\n]+)"')


class CalculNonJouable(ValueError):
    """Le calcul appelé ne peut pas donner de valeur pour cette itération — le message dit pourquoi, en clair."""


def noms_appeles(feature: str | None) -> list[str]:
    """Les calculs que le test appelle, dans l'ordre de première apparition, sans doublon."""
    vus: dict[str, None] = {}
    for trouve in _APPEL.finditer(feature or ""):
        vus.setdefault(trouve.group(1).strip(), None)
    return list(vus)


def variables(noms: list[str]) -> dict[str, str]:
    """Nom du calcul → variable réservée qui portera sa valeur (`tp_calcul_1`, `tp_calcul_2`…)."""
    return {nom: f"{PREFIXE}{rang}" for rang, nom in enumerate(noms, start=1)}


def reecrire(feature: str, par_nom: Mapping[str, str]) -> str:
    """Chaque appel `le résultat calculé "<nom>"` devient `"{{tp_calcul_k}}"` — la forme du step de nombres existant."""
    return _APPEL.sub(lambda m: '"{{' + par_nom[m.group(1).strip()] + '}}"', feature)


def valeurs(fiches: Mapping[str, dict], par_nom: Mapping[str, str], valeurs_de_l_iteration: Mapping[str, str]
            ) -> dict[str, tuple[str, str, list[str]]]:
    """Variable réservée → (valeur écrite avec son unité, origine montrée au rapport, détail du calcul). Lève
    `CalculNonJouable` au premier calcul impossible."""
    sortie = {}
    for nom, variable in par_nom.items():
        fiche = fiches.get(nom)
        if fiche is None:
            raise CalculNonJouable(f"le calcul « {nom} » n'est pas retenu pour ce cas — choisissez-le dans la fiche du cas "
                                   "ou régénérez le test")
        entrees = {e: valeurs_de_l_iteration[e] for e in calcul.entrees_attendues(fiche) if e in valeurs_de_l_iteration}
        try:
            resultat = calcul.calculer(fiche, entrees)
        except calcul.CalculImpossible as exc:
            raise CalculNonJouable(f"calcul « {nom} » : {exc}") from exc
        texte = format(resultat.resultat, "f").replace(".", ",")
        if resultat.unite:
            texte = f"{texte} {resultat.unite}"
        sortie[variable] = (texte, f"calcul « {nom} »", resultat.detail)
    return sortie
