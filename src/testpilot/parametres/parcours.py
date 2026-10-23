"""Le parcours d'un cas, enregistré par une personne dans le navigateur en direct (étape 7b, décision A109 du porteur, 2026-10-23)
— module PUR : aucune I/O, aucun navigateur, aucun LLM.

Pourquoi. L'IA qui écrit un test devine le chemin : quel bouton, quel champ, dans quel ordre — et se trompe parfois. Une
personne qui JOUE le cas une fois le connaît. Ici, ce qu'elle a fait devient :
- pour un cas automatisé, les ACTIONS du test, traduites SANS IA en étapes de la bibliothèque (le chemin est juste du premier
  coup) ; l'IA n'écrit plus que la vérification (« Alors »), sur l'élément désigné, avec le résultat attendu du CAS VALIDÉ —
  jamais ce que l'écran montrait pendant l'enregistrement (A39 : un bug présent ce jour-là deviendrait l'attendu) ;
- pour un cas manuel, son MODE OPÉRATOIRE, lisible étape par étape.

Ce qui est retenu d'une action : le rôle et le nom de l'élément (comme l'enregistrement de la connexion), la valeur saisie ou
choisie (jamais celle d'un champ mot de passe), la page atteinte. Ni vidéo, ni image.
"""

from __future__ import annotations

import re

from testpilot.parametres.calcul_au_lancement import _scenarios

ACTIONS = ("clic", "saisie", "choix", "verifier")
# Le libellé français de chaque rôle (CONTINUITE §4.7) — tous ceux que la capture peut rendre (`accname._ROLES_INTERACTIFS`,
# plus `element` : un élément désigné techniquement). Le même tableau côté écran : `EnregistrerParcours.vue`.
LIBELLES_DES_ROLES = {
    "button": "bouton", "link": "lien", "tab": "onglet", "textbox": "champ", "searchbox": "champ de recherche",
    "spinbutton": "champ numérique", "combobox": "liste", "listbox": "liste", "option": "option",
    "checkbox": "case à cocher", "radio": "bouton radio", "switch": "interrupteur", "slider": "curseur",
    "menuitem": "menu", "menuitemcheckbox": "menu", "menuitemradio": "menu", "summary": "bloc dépliant",
    "element": "élément",
}
ACTIONS_MAX = 200          # au-delà, ce n'est plus UN cas : un parcours à découper
_INTERDITS = re.compile(r'["|\r\n]')   # casseraient l'écriture d'une étape (`"…"`, colonne d'un tableau, une ligne)


class ParcoursInvalide(ValueError):
    """Le parcours reçu n'a pas la forme attendue — le message dit quoi."""


def _texte(valeur, limite: int = 200) -> str:
    return str(valeur or "").strip()[:limite]


def normaliser(actions) -> list[dict]:
    """Les actions telles qu'elles sont gardées : seulement les champs connus, bornés. `ParcoursInvalide` sinon."""
    if not isinstance(actions, list) or not actions:
        raise ParcoursInvalide("le parcours ne contient aucune action")
    if len(actions) > ACTIONS_MAX:
        raise ParcoursInvalide(f"{len(actions)} actions : {ACTIONS_MAX} au plus")
    sortie = []
    for i, brute in enumerate(actions, start=1):
        if not isinstance(brute, dict) or brute.get("action") not in ACTIONS:
            raise ParcoursInvalide(f"action {i} : « {(brute or {}).get('action') if isinstance(brute, dict) else brute} » "
                                   f"inconnue ({', '.join(ACTIONS)})")
        action = {"action": brute["action"], "role": _texte(brute.get("role"), 40), "nom": _texte(brute.get("nom")),
                  "page": _texte(brute.get("page"), 300)}
        if brute["action"] in ("saisie", "choix"):
            if brute.get("secret"):
                # Jamais un mot de passe : ni sa valeur, ni l'action (revue du 2026-10-23 — l'agent ne pourrait que
                # l'inventer ; la connexion est faite par TestPilot, hors du parcours).
                continue
            action["champ"] = _texte(brute.get("champ")) or action["nom"]
            action["secret"] = False
            action["valeur"] = _texte(brute.get("valeur"), 500)
            action["relation"] = bool(brute.get("relation"))
        if not (action["nom"] or action.get("champ")):
            raise ParcoursInvalide(f"action {i} : l'élément n'a pas de nom")
        sortie.append(action)
    if not sortie:
        raise ParcoursInvalide("le parcours ne contient aucune action")
    return sortie


def _ecrivable(*textes: str) -> bool:
    return all(t and not _INTERDITS.search(t) for t in textes)


def etape_de_test(action: dict) -> str | None:
    """La ligne de test (sans mot-clé) qui rejoue l'action avec la bibliothèque, ou `None` si aucune ne la rejoue telle quelle
    (l'IA l'écrira alors, guidée par ce que le parcours dit). Une vérification n'est jamais une action : `None`."""
    a = action["action"]
    if a == "clic":
        if action["role"] in ("button", "link") and _ecrivable(action["nom"]):
            return f'je clique sur le bouton "{action["nom"]}"'
        if action["role"] == "tab" and _ecrivable(action["nom"]):
            return f'je clique sur l\'onglet "{action["nom"]}"'
        return None
    # Une liste à recherche (autocomplétion, many2one) : remplir le texte ne choisit pas l'enregistrement — l'agent écrit
    # l'étape propre à l'application (revue du 2026-10-23 : forcer l'étape générique aurait fait échouer le test).
    if a == "saisie" and not action.get("secret") and not action.get("relation") and _ecrivable(action["champ"]) \
            and not _INTERDITS.search(action["valeur"]):
        return f'je renseigne le champ "{action["champ"]}" avec la valeur "{action["valeur"]}"'
    if a == "choix" and _ecrivable(action["champ"], action["valeur"]):
        return f'je sélectionne "{action["valeur"]}" dans le champ "{action["champ"]}"'
    return None


def pour_l_agent(actions: list[dict]) -> dict:
    """Ce que l'agent technique reçoit : les actions traduites (à recopier dans l'ordre ; `None` = à écrire lui-même, avec la
    description de l'action) et les éléments où la personne vérifie le résultat. Les valeurs saisies y sont : ce sont les
    DONNÉES du parcours, pas un résultat attendu (le résultat attendu vient du cas)."""
    etapes, a_verifier = [], []
    for action in actions:
        if action["action"] == "verifier":
            a_verifier.append({"role": action["role"], "nom": action["nom"], "page": action["page"]})
            continue
        etapes.append({"etape": etape_de_test(action), "description": lire(action)})
    return {"etapes": etapes, "a_verifier": a_verifier}


def lire(action: dict) -> str:
    """Une action en français, pour le mode opératoire d'un cas manuel et pour l'agent."""
    a, nom = action["action"], action.get("nom") or action.get("champ") or "?"
    role = LIBELLES_DES_ROLES.get(action.get("role", ""), "élément")   # jamais un rôle ARIA brut à l'écran (§4.7)
    if a == "clic":
        return f"Cliquer sur « {nom} » ({role})"
    if a == "choix" or (a == "saisie" and action.get("relation")):
        return f"Choisir « {action['valeur']} » dans « {action.get('nom') or action.get('champ')} »"
    if a == "saisie":
        return f"Saisir « {action['valeur']} » dans « {action.get('nom') or action.get('champ')} »"
    return f"Vérifier le résultat attendu sur « {nom} » ({role})"


def mode_operatoire(actions: list[dict]) -> list[str]:
    return [f"{i}. {lire(a)}" for i, a in enumerate(actions, start=1)]


def _motif(etape: str) -> re.Pattern:
    """Une étape traduite, retrouvée dans le test : mot pour mot, sauf la VALEUR d'une saisie qui peut être devenue une donnée
    de test (`{{quantite}}`) — l'élément et l'ordre, eux, sont ceux de la personne."""
    valeur = re.match(r'^je renseigne le champ "([^"]*)" avec la valeur "[^"]*"$', etape)
    if valeur:
        return re.compile(r'^je renseigne le champ "' + re.escape(valeur.group(1)) + r'" avec la valeur "[^"]*"$')
    choix = re.match(r'^je sélectionne "[^"]*" dans le champ "([^"]*)"$', etape)
    if choix:
        return re.compile(r'^je sélectionne "[^"]*" dans le champ "' + re.escape(choix.group(1)) + r'"$')
    return re.compile("^" + re.escape(etape) + "$")


def fautes_d_ecriture(feature: str, parcours: dict) -> list[str]:
    """Le test écrit suit-il le parcours ? Chaque action traduite doit apparaître, DANS L'ORDRE, parmi les actions (Soit/Quand)
    du scénario — d'autres actions peuvent s'intercaler (l'agent écrit celles que la bibliothèque ne rejoue pas). Lu par
    l'analyseur de Behave (signal structurel). Vide : il le suit."""
    from behave.parser import ParserError, parse_feature

    attendues = [e["etape"] for e in parcours.get("etapes") or [] if e.get("etape")]
    if not attendues:
        return []
    try:
        modele = parse_feature(feature, language="fr")
    except ParserError:
        return ["le test n'est pas lisible"]
    # Chaque scénario TEL QU'ÉCRIT avec le Contexte qui s'applique (Règles comprises) — même lecture que les calculs.
    blocs = _scenarios(modele, []) if modele else []
    if not blocs:
        return ["le test n'a aucun scénario"]
    fautes = []
    for fond, scenario in blocs:
        actions = [s.name.strip() for s in fond + list(scenario.steps) if s.step_type in ("given", "when")]
        rang = 0
        for etape in attendues:
            motif = _motif(etape)
            while rang < len(actions) and not motif.match(actions[rang]):
                rang += 1
            if rang == len(actions):
                fautes.append(f"le scénario « {scenario.name} » ne suit pas le parcours enregistré : « {etape} » manque, ou "
                              "n'est pas à sa place — recopie les actions du parcours dans l'ordre")
                break
            rang += 1
    return fautes
