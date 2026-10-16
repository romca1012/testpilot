"""Itérations : un test, une ligne de données de test par itération (décision A52 du porteur, 2026-10-16) — module PUR.

Le « Data Table » de QTP/UFT : le même test est rejoué une fois par ligne choisie au lancement, chaque ligne portant ses valeurs
— résultat attendu compris (`{{resultat_attendu}}`, déclaré par une personne). Une exécution, un seul passage de Behave : la
copie du test propre à l'exécution devient un « Plan du scénario » dont chaque « Exemples » est une itération, nommée d'après
sa ligne. Chaque itération est un scénario avec son propre résultat ; le verdict de l'exécution est celui de Behave sur
l'ensemble — une itération en échec fait échouer l'exécution, une itération qui n'a rien prouvé n'est jamais conforme.

Deux règles :
- `iterations` : les lignes réduites aux valeurs DES variables du test. Deux lignes qui ne diffèrent que par une variable que
  ce test n'emploie pas ne font qu'une itération ; un test sans variable n'en a qu'une (il se joue comme avant).
- `en_plan_de_scenario` : réécrit le Gherkin à partir des numéros de ligne du parseur de Behave lui-même. Les variables sont
  remplacées par `resolution.remplacer` — EXACTEMENT les écritures qu'accepte l'exécution d'un jeu seul (`{{ age }}`,
  `{{Age}}`…), en `<age>` pour un plan, en valeur pour un scénario joué une fois. Un `Contexte` qui emploie une variable est
  recopié en tête de chaque scénario (Behave ne remplace pas `<nom>` dans un contexte). Un plan déjà écrit garde ses
  exemples, chacun combiné avec chaque itération. Deux filets, relus sur le résultat : plus AUCUNE `{{…}}`, et exactement le
  nombre de scénarios attendu (revue du 2026-10-16 : une variable restée littérale faisait passer un « n'est pas affiché »).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from testpilot.parametres import resolution

PLAN = "Plan du scénario"
EXEMPLES = "Exemples"


class IterationsImpossibles(ValueError):
    """Le test ne peut pas être joué en itérations — le message se montre tel quel (le test sort « bloqué »)."""


def iterations(lignes: Sequence[tuple[str, Mapping[str, str]]]) -> list[tuple[str, dict[str, str]]]:
    """[(nom, valeurs)] sans doublon : deux lignes aux mêmes valeurs (pour les variables du test) ne font qu'une itération,
    nommée d'après toutes ses lignes (« Par défaut / Pro »). L'ordre des lignes est gardé."""
    vues: dict[tuple, list] = {}
    for nom, valeurs in lignes:
        cle = tuple(sorted((n, str(v)) for n, v in valeurs.items()))
        if cle in vues:
            vues[cle][0].append(nom)
        else:
            vues[cle] = [[nom], dict(valeurs)]
    return [(" / ".join(noms), valeurs) for noms, valeurs in vues.values()]


def _poser(texte: str, valeurs: Mapping[str, str], connues: Iterable[str]) -> str:
    """Le remplacement de l'exécution d'un jeu seul (`resolution.remplacer`), pour ces valeurs."""
    return resolution.remplacer(texte, {n: resolution.Valeur(str(v), "") for n, v in valeurs.items()}, connues).texte


def _cellule_recopiee(texte: str) -> str:
    # Une cellule d'un « Exemples » déjà écrit : Behave ne déséchappe que « \| ». Une valeur de données de test, elle, ne
    # contient jamais « | » (`resolution.valider_valeur`) et n'est pas échappée : elle est jouée telle qu'annoncée (A29).
    return texte.replace("|", "\\|")


def _ligne_de_table(cellules: list[str], retrait: str) -> str:
    return retrait + "| " + " | ".join(cellules) + " |"


def _debut_d_entete(lignes: list[str], ligne: int) -> int:
    """La première ligne (1-based) de l'en-tête d'un élément : ses étiquettes et commentaires qui le précèdent."""
    debut = ligne
    while debut > 1 and (lignes[debut - 2].strip().startswith(("@", "#")) or not lignes[debut - 2].strip()):
        debut -= 1
    while debut < ligne and not lignes[debut - 1].strip():
        debut += 1
    return debut


def _instances(modele) -> int:
    return sum(len(list(s.scenarios)) if hasattr(s, "scenarios") else 1 for s in modele.scenarios)


def en_plan_de_scenario(feature: str, iters: Sequence[tuple[str, Mapping[str, str]]],
                        connues: Iterable[str] | None = None) -> str:
    """Le Gherkin `feature` (où `{{nom}}` est encore écrit) joué une fois par itération. `connues` : les variables du projet.
    Lève `IterationsImpossibles`."""
    from behave.parser import ParserError, parse_feature

    if not iters:
        raise IterationsImpossibles("aucune ligne de données de test à jouer")
    noms = list(iters[0][1])
    connues = list(connues) if connues is not None else noms
    try:
        modele = parse_feature(feature, language="fr")
    except ParserError as exc:
        raise IterationsImpossibles(f"le test n'a pas pu être relu pour les itérations ({exc})") from exc
    if modele is None:
        raise IterationsImpossibles("le test est vide")
    if getattr(modele, "rules", None):
        raise IterationsImpossibles("un test organisé en « Règle » ne se joue pas encore en itérations")
    lignes = feature.split("\n")
    marques = _poser(feature, {n: f"<{n}>" for n in noms}, connues).split("\n")   # `{{age}}` → `<age>`, mêmes lignes
    if len(marques) != len(lignes):
        raise IterationsImpossibles("le test n'a pas pu être préparé pour les itérations")
    scenarios = list(modele.scenarios)
    debuts = [_debut_d_entete(lignes, s.line) for s in scenarios] + [len(lignes) + 1]

    # 1. Le contexte, s'il emploie une variable : retiré, et ses étapes recopiées en tête de chaque scénario.
    contexte: tuple[int, int] | None = None     # (première, dernière) ligne de ses étapes
    retirer: tuple[int, int] | None = None
    fond = modele.background
    if fond is not None and fond.steps:
        fin = (debuts[0] if scenarios else len(lignes) + 1) - 1
        if resolution.references("\n".join(lignes[fond.steps[0].line - 1:fin])):
            while fin > fond.steps[0].line and not lignes[fin - 1].strip():
                fin -= 1
            contexte = (fond.steps[0].line, fin)
            retirer = (_debut_d_entete(lignes, fond.line), fin)

    def bloc(source: list[str], scenario, debut: int, fin: int) -> tuple[list[str], int]:
        """Les lignes du scénario dans `source`, contexte recopié avant ses étapes ; et le décalage introduit."""
        lignes_bloc = source[debut - 1:fin]
        if contexte is None or not scenario.steps:
            return lignes_bloc, 0
        recopie = source[contexte[0] - 1:contexte[1]]
        premier = scenario.steps[0].line - debut
        return lignes_bloc[:premier] + recopie + lignes_bloc[premier:], len(recopie)

    sortie: list[str] = []
    attendues = 0
    curseur = 1
    for index, scenario in enumerate(scenarios):
        debut, fin = debuts[index], debuts[index + 1] - 1
        sortie += [l for n, l in enumerate(lignes[curseur - 1:debut - 1], start=curseur)
                   if retirer is None or not retirer[0] <= n <= retirer[1]]
        origine, decalage = bloc(lignes, scenario, debut, fin)
        employes = [n for n in noms if n in resolution.references("\n".join(origine))]
        exemples = list(getattr(scenario, "examples", None) or [])
        lignes_d_exemples = sum(len(e.table.rows) for e in exemples if e.table is not None) if exemples else 1
        if not employes:
            sortie += origine
            attendues += lignes_d_exemples
        else:
            propres = iterations([(nom, {n: v[n] for n in employes}) for nom, v in iters])
            if len(propres) == 1:    # mêmes valeurs dans toutes les lignes pour CE scénario : joué une fois, valeurs posées
                sortie += _poser("\n".join(origine), propres[0][1], connues).split("\n")
                attendues += lignes_d_exemples
            else:
                ordinaire = scenario.__class__.__name__ != "ScenarioOutline"   # dans un plan, `<nom>` est une colonne
                if ordinaire and any(f"<{n}>" in "\n".join(origine) for n in employes):
                    raise IterationsImpossibles("le test écrit déjà « <nom> » pour une de ses variables : il ne se joue pas "
                                                "en itérations")
                marque, _ = bloc(marques, scenario, debut, fin)
                sortie += _plan(marque, scenario, debut, decalage, employes, propres, connues)
                attendues += len(propres) * lignes_d_exemples
        curseur = fin + 1
    reste = lignes[curseur - 1:]
    if retirer is not None and not scenarios:
        reste = [l for n, l in enumerate(reste, start=curseur) if not retirer[0] <= n <= retirer[1]]
    sortie += reste
    texte = "\n".join(sortie)

    if resolution.references(texte):
        raise IterationsImpossibles("une variable du test n'a pas pu être posée pour chaque itération")
    try:
        verifie = parse_feature(texte, language="fr")
    except ParserError as exc:   # filet : la réécriture ne doit jamais produire un Gherkin que Behave refuse
        raise IterationsImpossibles(f"les itérations n'ont pas pu être écrites ({exc})") from exc
    if verifie is None or _instances(verifie) != attendues:
        raise IterationsImpossibles("les itérations n'ont pas pu être écrites")
    return texte


def _plan(marque: list[str], scenario, debut: int, decalage: int, employes: list[str], iters, connues) -> list[str]:
    """Un scénario (déjà marqué `<nom>`) réécrit en plan dont chaque itération est une « Exemples ». `decalage` : les lignes
    du contexte recopiées avant ses étapes."""
    entete = scenario.line - debut
    retrait = marque[entete][:len(marque[entete]) - len(marque[entete].lstrip())] + "  "
    if scenario.__class__.__name__ != "ScenarioOutline":
        corps = list(marque)
        corps[entete] = corps[entete].replace(f"{scenario.keyword}:", f"{PLAN}:", 1)
        while corps and not corps[-1].strip():
            corps.pop()
        for nom_ligne, valeurs in iters:
            corps += ["", f"{retrait}{EXEMPLES}: {nom_ligne}", _ligne_de_table(list(employes), retrait + "  "),
                      _ligne_de_table([valeurs[n] for n in employes], retrait + "  ")]
        return corps + [""]
    # Un plan déjà écrit : chaque « Exemples » combiné avec chaque itération (ses colonnes + les variables). Ses cellules
    # reçoivent elles aussi les valeurs de l'itération (une cellule peut citer `{{age}}`), ses étiquettes sont gardées.
    exemples = list(scenario.examples or [])
    if not exemples:
        raise IterationsImpossibles("un plan de scénario sans « Exemples » ne se joue pas en itérations")
    if any(n in (e.table.headings if e.table else []) for e in exemples for n in employes):
        raise IterationsImpossibles("une colonne des exemples du test porte le nom d'une variable de test")
    lignes_brutes = marque  # mêmes numéros de ligne que le Gherkin d'origine, décalés du contexte recopié
    premier = min(_debut_d_entete_relatif(lignes_brutes, e.line - debut + decalage) for e in exemples)
    corps = list(marque[:premier])
    while corps and not corps[-1].strip():
        corps.pop()
    for e in exemples:
        if e.table is None:
            continue
        etiquettes = " ".join(f"@{t}" for t in (getattr(e, "tags", None) or []))
        for nom_ligne, valeurs in iters:
            corps += [""]
            if etiquettes:
                corps.append(f"{retrait}{etiquettes}")
            corps.append(f"{retrait}{e.keyword}: {(e.name + ' — ') if e.name else ''}{nom_ligne}")
            corps.append(_ligne_de_table([_cellule_recopiee(h) for h in e.table.headings] + list(employes), retrait + "  "))
            for rangee in e.table.rows:
                cellules = [_cellule_recopiee(_poser(c, valeurs, connues)) for c in rangee.cells]
                corps.append(_ligne_de_table(cellules + [valeurs[n] for n in employes], retrait + "  "))
    return corps + [""]


def _debut_d_entete_relatif(lignes: list[str], index: int) -> int:
    """`_debut_d_entete` sur un bloc (index 0-based) : l'en-tête d'un « Exemples » commence à ses étiquettes."""
    debut = index
    while debut > 0 and (lignes[debut - 1].strip().startswith(("@", "#")) or not lignes[debut - 1].strip()):
        debut -= 1
    while debut < index and not lignes[debut].strip():
        debut += 1
    return debut
