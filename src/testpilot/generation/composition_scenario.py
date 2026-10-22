"""Composition d'un scénario (étape 5 du plan unique, défaut F24 du registre de fiabilité).

Pourquoi. Mesuré sur la génération 17.0 du banc (2026-09-25) : un `Alors` lit « cet enregistrement » sans qu'aucune étape
ne l'ait mis en contexte — `RuntimeError` à l'exécution, un cas en erreur technique de plus, et une réparation payée pour
un test mal composé dès l'écriture. Le refus arrive maintenant à l'ÉCRITURE : l'IA corrige tout de suite.

Ce que « poser » et « lire » veulent dire ne vient pas d'une liste tenue à la main : `steps_library` le lit dans le CODE
de la bibliothèque (AST, `context.last_record_ids` écrit ou lu, à travers ses helpers). Le contrôle ne lit que la
STRUCTURE du `.feature` (étapes du contexte puis du scénario, plans développés), jamais le sens d'un libellé.

Prudent par construction : une étape qui n'est pas dans la bibliothèque (écrite dans le `_steps.py` du test) peut poser
l'enregistrement — après elle, plus aucun refus dans ce scénario.

Module pur : aucune I/O, aucun LLM.
"""

from __future__ import annotations

import parse as parse_lib


def _parseurs(catalogue) -> list[tuple[object, object]]:
    retenus = []
    for step in catalogue or []:
        try:
            retenus.append((step, parse_lib.compile(step.label)))
        except (ValueError, IndexError):
            continue
    return retenus


def _reconnu(texte: str, parseurs):
    for step, parseur in parseurs:
        try:
            if parseur.parse(texte) is not None:
                return step
        except (ValueError, IndexError):
            continue
    return None


def enregistrement_lu_sans_etre_pose(feature: str, catalogue) -> list[str]:
    """Les étapes qui lisent l'enregistrement courant sans qu'aucune étape précédente du scénario ne l'ait posé."""
    from behave.parser import ParserError, parse_feature

    parseurs = _parseurs(catalogue)
    if not any(getattr(s, "lit_enregistrement", False) for s, _p in parseurs):
        return []
    try:
        modele = parse_feature(feature or "", language="fr")
    except ParserError:
        return []
    if modele is None:
        return []
    fautes = []
    for scenario in modele.walk_scenarios():
        fond = getattr(scenario, "background_steps", None) or []
        pose = False
        for etape in [*fond, *(getattr(scenario, "steps", None) or [])]:
            step = _reconnu(str(etape.name or "").strip(), parseurs)
            if step is None or getattr(step, "pose_enregistrement", False):
                pose = True   # étape inconnue de la bibliothèque : elle peut poser l'enregistrement (prudence)
                continue
            if getattr(step, "lit_enregistrement", False) and not pose:
                fautes.append(f"« {etape.name} » (scénario « {scenario.name} ») lit l'enregistrement courant, mais aucune "
                              "étape précédente ne l'a créé, ouvert ou trouvé")
    return list(dict.fromkeys(fautes))
