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
# Revue du 2026-10-23 : seule la phrase COMPLÈTE du step de la bibliothèque appelle un calcul — jamais « le résultat calculé »
# glissé dans une action, un commentaire ou un step propre à l'agent (la valeur attendue y serait saisie : une tautologie).
_APPEL = re.compile(r'(le nombre affiché pour "[^"\r\n]+" vaut )le résultat calculé "([^"\r\n]+)"')
_MENTION = re.compile(r"le résultat calculé")


class CalculNonJouable(ValueError):
    """Le calcul appelé ne peut pas donner de valeur pour cette itération — le message dit pourquoi, en clair."""


def noms_appeles(feature: str | None) -> list[str]:
    """Les calculs que le test appelle, dans l'ordre de première apparition, sans doublon."""
    vus: dict[str, None] = {}
    for trouve in _APPEL.finditer(feature or ""):
        vus.setdefault(trouve.group(2).strip(), None)
    return list(vus)


def _scenarios(conteneur, fond: list) -> list[tuple[list, object]]:
    """(steps du Contexte qui s'applique, scénario TEL QU'ÉCRIT) — un plan compte une fois (jamais ses scénarios générés),
    une Règle apporte son propre Contexte. Revue du 2026-10-23 (2e passe) : `walk_scenarios` rendait le plan ET ses
    exemples, comptés plusieurs fois."""
    fond = fond + list(conteneur.background.steps if getattr(conteneur, "background", None) else [])
    blocs = [(fond, s) for s in getattr(conteneur, "scenarios", []) or []]
    for regle in getattr(conteneur, "rules", []) or []:
        blocs += _scenarios(regle, fond)
    return blocs


def _mentionne(step) -> bool:
    return bool(_MENTION.search(step.name) or _MENTION.search(step.text or "") or (
        step.table and any(_MENTION.search(c) for r in step.table.rows for c in r.cells)))


def _references_saisies(steps) -> set[str]:
    from testpilot.parametres import resolution

    posees: set[str] = set()
    for step in steps:
        if step.step_type in ("given", "when"):
            for texte in [step.name, step.text or ""] + ([c for r in step.table.rows for c in r.cells] if step.table else []):
                posees.update(resolution.references(texte))
    return posees


def analyser_les_appels(feature: str) -> tuple[str, list[tuple[str, frozenset[str]]]]:
    """(refus, appels) — lu par l'analyseur de Behave, un signal STRUCTUREL, jamais le seul texte. Chaque appel est un step
    `then` dont la phrase ENTIÈRE est celle de la bibliothèque ; « le résultat calculé » n'apparaît nulle part ailleurs
    (action, tableau, Contexte, commentaire). Chaque appel est rendu avec les variables que SON scénario saisit (Contexte
    compris) : une entrée de calcul doit être saisie par le scénario même qui vérifie le résultat — un autre scénario qui la
    cite ne prouve rien (revue du 2026-10-23, 2e passe, bloquant)."""
    from behave.parser import ParserError, parse_feature

    try:
        modele = parse_feature(feature, language="fr")
    except ParserError:
        return "le test n'est pas lisible", []
    if modele is None:
        return "", []
    hors_verification = "seule une vérification « Alors le nombre affiché pour … vaut le résultat calculé … » peut appeler un calcul"
    mentions, appels, fonds_vus = 0, [], set()
    for fond, scenario in _scenarios(modele, []):
        for step in fond:
            if id(step) not in fonds_vus and _mentionne(step):
                return f"« {step.keyword} {step.name[:80]} » (Contexte) : {hors_verification}", []
            fonds_vus.add(id(step))
        # Seules comptent les saisies faites AVANT la vérification (3e passe de la revue) : une valeur saisie après n'a pas
        # pu produire ce que la vérification lit.
        avant = list(fond)
        for step in scenario.steps:
            if not _mentionne(step):
                avant.append(step)
                continue
            trouve = _APPEL.fullmatch(step.name.strip())
            if step.step_type != "then" or not trouve or step.text or step.table:
                return f"« {step.keyword} {step.name[:80]} » : {hors_verification}", []
            mentions += 1
            appels.append((trouve.group(2).strip(), frozenset(_references_saisies(avant))))
            avant.append(step)
    if len(_MENTION.findall(feature)) != mentions:   # une mention hors des steps lus (un commentaire) : jamais réécrite
        return "« le résultat calculé » apparaît ailleurs que dans une vérification (commentaire, texte joint)", []
    return "", appels


def variables(noms: list[str]) -> dict[str, str]:
    """Nom du calcul → variable réservée qui portera sa valeur (`tp_calcul_1`, `tp_calcul_2`…)."""
    return {nom: f"{PREFIXE}{rang}" for rang, nom in enumerate(noms, start=1)}


def reecrire(feature: str, par_nom: Mapping[str, str]) -> str:
    """Chaque appel `le résultat calculé "<nom>"` devient `"{{tp_calcul_k}}"` — la forme du step de nombres existant."""
    return _APPEL.sub(lambda m: m.group(1) + '"{{' + par_nom[m.group(2).strip()] + '}}"', feature)


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
