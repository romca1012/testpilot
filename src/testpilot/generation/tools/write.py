"""Tools d'écriture des fichiers Behave, avec validation avant persistance.

Règles verrouillées (issues des erreurs récurrentes du prototype) :
  - guillemets ASCII uniquement (les typographiques cassent ``ast.parse``) ;
  - un fichier _steps.py ne redéfinit jamais un step de la bibliothèque partagée
    (sinon AmbiguousStep au run) — la liste réservée vient de ToolContext ;
  - un step généré ne réinvente pas son propre transport HTTP (décision 0003) : il passe
    par ``context.odoo`` (RPC) ou ``context.page`` (navigateur), jamais par ``requests``.
"""

from __future__ import annotations

import ast
import json
import os
import re
import unicodedata
from typing import TYPE_CHECKING

from testpilot.generation import enregistrement_lint, gel_verifications, litteraux_observes, steps_library
from testpilot.generation.references import message_refus, verifier_references
from testpilot.generation.tools import essai as essai_tools
from testpilot.generation.placeholders import SECRET_MASQUE

if TYPE_CHECKING:
    from testpilot.generation.tools import ToolContext, ToolOutcome

_CURLY = "‘’“”"

# Bibliothèques d'accès réseau brut interdites dans un step généré. L'e2e a montré le
# problème : l'agent a écrit son propre helper `requests` vers /web/dataset/call_kw — une
# route interne, appelée hors session → 404, et 3 scénarios morts avant toute vérification.
_FORBIDDEN_IMPORTS = {"requests", "urllib", "urllib3", "httpx", "http", "aiohttp"}
# Endpoints internes d'Odoo : jamais appelés en direct par un test (c'est le rôle du RPC).
_FORBIDDEN_ENDPOINTS = ("/web/dataset", "/jsonrpc", "/xmlrpc")


def _outcome(observation: str, ok: bool = True, **kw):
    from testpilot.generation.tools import ToolOutcome
    if not ok:
        _consigner_refus_d_ecriture(observation)
    return ToolOutcome(observation=observation, ok=ok, **kw)


# Lot VH-04 (banc base-4, 2026-10-09) : deux générations sur 30 n'ont pas abouti (l'une à 0,54 $) sans qu'on puisse dire si
# les gardes d'écriture faisaient tourner l'agent en rond — rien ne gardait trace des REFUS. Désignée par le banc (variable
# d'environnement), une ligne par refus : l'outil et le CODE du refus (écrits par nos gardes, jamais par l'agent).
REFUS_ECRITURE_FILE_ENV = "TP_REFUS_ECRITURE_FILE"
_CODE_DE_REFUS = re.compile(r"^\[(\w+)\]\s*([A-Z][A-Z_]{2,})?")


def _consigner_refus_d_ecriture(observation: str) -> None:
    chemin = os.environ.get(REFUS_ECRITURE_FILE_ENV)
    if not chemin:
        return
    trouve = _CODE_DE_REFUS.match(observation or "")
    ligne = {"outil": trouve.group(1) if trouve else "", "code": (trouve.group(2) if trouve else "") or "AUTRE"}
    try:
        with open(chemin, "a", encoding="utf-8") as flux:
            flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except OSError:
        pass  # une mesure manquée ne fait jamais tomber une génération


def _forbidden_transport(tree: ast.AST, content: str) -> str:
    """Décrit le transport interdit trouvé dans un fichier de steps, sinon chaîne vide.

    Les imports sont détectés via l'AST (une regex confondrait un import réel avec une
    mention en commentaire ou en docstring) ; les endpoints internes le sont sur le texte.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORTS or root == "testpilot":
                    return f"import de `{alias.name}`"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            # Lot 07e (D7, revue du 2026-09-28) : le paquet applicatif `testpilot` n'est JAMAIS
            # importé par un step généré (le prompt système n'enseigne que `_base_helpers`,
            # `features.environment`, `behave`) — bannir la RACINE entière, pas seulement un
            # sous-module précis, ferme aussi un contournement PAR ATTRIBUT (importer un paquet
            # PARENT puis nommer un sous-module sensible en pointillé dans le code, jamais dans une
            # clause `import`/`from` — donc invisible à une détection limitée à un sous-module précis).
            if root in _FORBIDDEN_IMPORTS or root == "testpilot":
                return f"import depuis `{node.module}`"

    for endpoint in _FORBIDDEN_ENDPOINTS:
        if endpoint in content:
            return f"appel direct à l'endpoint interne `{endpoint}`"
    return ""


_LECTURES_RPC = {"search", "read", "search_read"}


def _touche_env(noeud: ast.AST, alias: frozenset = frozenset()) -> bool:
    return any((isinstance(n, ast.Attribute) and n.attr in {"env", "odoo"})
               or (isinstance(n, ast.Name) and (n.id in {"env", "odoo"} or n.id in alias))
               for n in ast.walk(noeud))


def _est_lecture_rpc(noeud: ast.AST, alias: frozenset = frozenset()) -> bool:
    return (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr in _LECTURES_RPC and _touche_env(noeud.func.value, alias))


def _forbidden_recount(tree: ast.AST) -> str:
    """Décrit un COMPTAGE écrit par l'agent (§F9, 2026-09-23), sinon chaîne vide.

    Un step généré qui recompte lui-même (`search_count`, ou `len()` d'un `search`/`read`
    RPC) contourne les helpers cloisonnés du lot 01 (`id > max_id`) et réintroduit le faux
    PASSED de F1 — dans le code GÉNÉRÉ, là où aucun test du dépôt ne le voit (mesuré en
    campagne réelle, cas 95, 23/09). Détection par AST : ni un commentaire ni une chaîne ne
    déclenchent, un `len()` sur une variable n'est vu que si elle vient d'une lecture RPC, et
    un alias local d'un modèle (`M = context.odoo.env['m']` puis `M.search_count([])`) est suivi.

    ⚠️ **Limites assumées — c'est un filet, pas une preuve d'absence de comptage** : ne sont PAS
    vus `getattr(m, 'search_count')`, un comptage indirect (`sum(1 for _ in m.search([]))`,
    `read_group`), un alias posé hors de la fonction (niveau module) ou passé en argument. Un
    agent déterminé les contourne ; ce garde ferme la forme littérale que l'agent produit
    réellement (mesuré : cas 95) et redirige vers le catalogue. Faux positif assumé : tout
    `len(search(...))` sur `env`/`odoo`, même légitime, est refusé.
    """
    portees = [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] or [tree]
    for portee in portees:
        affectations = [n for n in ast.walk(portee) if isinstance(n, ast.Assign)]
        alias = frozenset(
            c.id for n in affectations if isinstance(n.value, (ast.Subscript, ast.Attribute))
            and _touche_env(n.value) for c in n.targets if isinstance(c, ast.Name))
        issus_de_lecture = {
            c.id for n in affectations if _est_lecture_rpc(n.value, alias)
            for c in n.targets if isinstance(c, ast.Name)}
        for n in ast.walk(portee):
            if not isinstance(n, ast.Call):
                continue
            if (isinstance(n.func, ast.Attribute) and n.func.attr == "search_count"
                    and _touche_env(n.func.value, alias)):
                return "appel à `search_count` sur `context.odoo.env`"
            if isinstance(n.func, ast.Name) and n.func.id == "len" and n.args:
                arg = n.args[0]
                if _est_lecture_rpc(arg, alias) or (isinstance(arg, ast.Name)
                                                    and arg.id in issus_de_lecture):
                    return "`len()` d'une lecture `search`/`read` sur `context.odoo.env`"
    return ""


# ── Gardes de PLACEMENT des assertions (lot 03, D4 — régime BLOQUANT) ────────────────────────────
#
# Le runtime (D3) prouve qu'un scénario vert a exécuté au moins un constat ; ces gardes disent à
# l'agent, AVANT tout run, où l'écrire. Un refus déterministe coûte moins qu'un run réel raté.
# Dérogation au régime détectif de 0008 (`assertion_lint`, inchangé pour les tautologies) : la faute
# est mesurable au runtime, donc le refus n'est pas une hypothèse.

_CONSTATER = {"constater", "constater_visible", "constater_texte"}


def _nom_appele(noeud: ast.Call) -> str:
    cible = noeud.func
    if isinstance(cible, ast.Name):
        return cible.id
    if isinstance(cible, ast.Attribute):
        return cible.attr
    return ""


def _forbidden_source_kwarg(tree: ast.AST) -> str:
    """Décrit un appel `constater(..., source=...)` LITTÉRAL (lot 07e, D7), sinon chaîne vide.

    ⚠️ **Message précoce, pas la garantie elle-même** (revue du 2026-09-28, 3e passe). La 2e revue a
    montré qu'une garde par AST limitée à cette forme se contourne par un 3e argument POSITIONNEL,
    un déballage `**{...}` ou un alias d'import (`from _base_helpers import constater as c`) — trois
    formes qu'aucune détection AST ne ferme EXHAUSTIVEMENT (un agent peut toujours renommer,
    déballer ou compter les positions). La VRAIE garantie tient désormais à la SIGNATURE de
    `constater(condition, message)` elle-même (`_base_helpers.py`, plus de paramètre `source`
    du tout) : un 3e argument, sous QUELQUE forme que ce soit, lève un `TypeError` au lieu de forger
    un signal. Ce garde-ci ne fait que transformer le cas le plus probable (le mot-clé littéral,
    celui qu'un agent écrirait naturellement après avoir vu `source` dans un message d'erreur ou une
    trace) en un refus déterministe AVANT le run, plutôt qu'en un crash runtime moins lisible.
    """
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and _nom_appele(node) == "constater"
                and any(kw.arg == "source" for kw in node.keywords)):
            return "argument `source=` d'un appel à `constater`"
    return ""


# Q1 (revue du 2026-10-07) : noms du MÉCANISME de preuve, réservés au socle. Un step généré qui s'en servirait
# pourrait se déclarer « non assertif » ou fausser le compteur pour masquer un `Alors` vide. Le refus est un message
# PRÉCOCE ; la garantie est STRUCTURELLE (`environment._est_exempte_non_assertive` n'exempte jamais une fonction du
# fichier généré) — même doctrine que `source=` (lot 07e) : un garde par forme de code ne ferme jamais la classe.
_RESERVES_AU_SOCLE = frozenset({
    "non_assertif", "_tp_non_assertif", "_COMPTEUR_CONSTATS", "nombre_de_constats_reussis",
    "consigner_alors_sans_constat", "_consigner_constat", "_SOURCE_CONSTAT", "_source_du_constat",
    "definir_etat_constat", "TP_GENERATED_STEPS_FILE",
    # Lot VH-02 (revue du 2026-10-08) : la garde des constats qui ne prouvent rien, et le fichier où les constats sont consignés.
    "_condition_toujours_vraie", "ConstatInvalideError", "TP_CONSTATS_FILE",
    # Lot VH-04 (revue, point 9) : garde de session, source `rpc` des constats, soumission observée — un step généré ne
    # désarme pas la garde, ne forge pas une lecture du serveur ni une soumission.
    "armer_garde_de_session", "_GARDE_DE_SESSION", "_appliquer_garde_de_session", "garde_de_session",
    "noter_session_ouverte", "cookies_de_session", "_tp_mot_de_passe_saisi", "_tp_cookies_session", "__tp_mot_de_passe_saisi",
    "noter_lecture_rpc", "_LECTURE_RPC_DU_STEP", "debut_de_step",
    "_tp_refus_navigateur", "_tp_releve_sequence", "_tp_releve_t", "_soumission_observee", "_est_un_envoi",
    "reponses_reseau", "navigations",
    # Lot VH-06 (revues) : l'oracle ne s'interroge que par les steps du catalogue — ni par `context.oracle`
    # (`litteraux_observes`), ni par les fonctions internes de la bibliothèque (`import _base_helpers as H; H._executer_oracle`).
    "_executer_oracle", "_resoudre_oracle", "_liste_de_l_oracle", "_champ_oracle", "construire_oracle",
    # Lot VH-07 : l'état consigné à la fin d'un essai (« exécuter puis écrire ») appartient au harnais.
    "TP_ESSAI_ETAT_FILE", "_consigner_etat_d_essai", "_JS_CONTROLES_D_ESSAI",
})


def _forbidden_reserve_au_socle(tree: ast.AST) -> str:
    """Décrit la première référence à un nom du mécanisme de preuve (`Name`, `Attribute`, import, ou chaîne
    littérale type `setattr(f, "_tp_non_assertif", True)`), sinon chaîne vide."""
    for node in ast.walk(tree):
        nom = ""
        if isinstance(node, ast.Name):
            nom = node.id
        elif isinstance(node, ast.Attribute):
            nom = node.attr
        elif isinstance(node, ast.alias):
            nom = node.name
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            nom = node.value
        if nom in _RESERVES_AU_SOCLE:
            return f"« {nom} » (mécanisme de preuve réservé à la bibliothèque)"
    return ""


def _decorateurs(func) -> set[str]:
    noms = set()
    for deco in func.decorator_list:
        cible = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(cible, ast.Name):
            noms.add(cible.id)
        elif isinstance(cible, ast.Attribute):
            noms.add(cible.attr)
    return noms


def _helpers_qui_constatent() -> frozenset[str]:
    """Délégué à `steps_library` (Q1 : source unique, partagée avec le catalogue). Bibliothèque
    illisible → au moins `constater*`, comme avant."""
    return steps_library.helpers_qui_constatent() or frozenset(_CONSTATER)


def _affirme(noeud: ast.AST) -> str:
    """Ce qui, dans ce nœud, est une ASSERTION écrite à la main ou un constat, sinon `""`."""
    if isinstance(noeud, ast.Assert):
        return "`assert`"
    if isinstance(noeud, ast.Raise) and noeud.exc is not None:
        cible = noeud.exc.func if isinstance(noeud.exc, ast.Call) else noeud.exc
        if isinstance(cible, ast.Name) and cible.id == "AssertionError":
            return "`raise AssertionError`"
    if isinstance(noeud, ast.Call):
        nom = _nom_appele(noeud)
        if nom == "expect":
            return "`expect(...)`"
        if nom in _CONSTATER:
            return f"`{nom}(...)`"
    return ""


def _avale_l_echec(handler: ast.ExceptHandler) -> bool:
    """Un `except` nu, `except Exception` ou `except BaseException` qui ne relève JAMAIS."""
    if handler.type is None:
        large = True
    else:
        # Lot VH-02 (V10) : `except (AssertionError, X):` contournait la garde, qui ne lisait qu'un nom seul.
        cibles = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        noms = {c.id if isinstance(c, ast.Name) else getattr(c, "attr", "") for c in cibles}
        # `TypeError`/`ConstatInvalideError` : avaler le refus d'un constat qui ne prouve rien (revue VH-02).
        large = bool(noms & {"Exception", "BaseException", "AssertionError", "TypeError", "ConstatInvalideError"})
    return large and not any(isinstance(n, ast.Raise) for n in ast.walk(handler))


def _forbidden_assertion_placement(tree: ast.AST) -> str:
    """Décrit la première faute de placement d'assertion (D4), sinon chaîne vide.

    1. une assertion ou un constat dans une fonction `@given`/`@when`/`@step` (sans `@then`) : le type
       du step est un signal de structure — une assertion hors `Alors` est classée « prérequis non
       rempli » (`@given`) ou « test cassé » (`@when`), jamais comme un constat sur l'application ;
    2. une fonction `@then` qui n'appelle ni `constater*` ni un helper de la bibliothèque qui en
       appelle : elle ne peut consigner aucun constat, donc ne prouve rien ;
    3. dans une fonction `@then`, un `except` large dont le corps ne relève pas : il avale l'échec.

    ⚠️ **Filet, pas preuve** : une assertion posée dans un helper NON décoré défini dans le fichier
    et appelé depuis un `@given`/`@when` n'est pas vue ; le runtime (D3) attrape ce qui reste.
    """
    constatent = _helpers_qui_constatent()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorateurs = _decorateurs(func)
        est_then = "then" in decorateurs
        est_contexte = bool(decorateurs & {"given", "when", "step"}) and not est_then
        if est_contexte:
            for n in ast.walk(func):
                trouve = _affirme(n)
                if trouve:
                    return (f"{trouve} dans le step `{func.name}` (`@given`/`@when`) : une assertion "
                            "n'a sa place que dans un `@then`. Dans un Soit/Quand, prépare ou agis ; "
                            "déplace la vérification dans un step « Alors »")
        if est_then:
            appels = {_nom_appele(n) for n in ast.walk(func) if isinstance(n, ast.Call)}
            if not (appels & constatent):
                return (f"le step `@then` `{func.name}` n'appelle ni `constater(...)` ni un helper de "
                        "la bibliothèque qui constate : il ne peut consigner aucun constat, donc ne "
                        "prouve rien. Écris `constater(condition, \"message\")` "
                        "(ou `constater_visible` / `constater_texte`)")
            for n in ast.walk(func):
                if isinstance(n, ast.ExceptHandler) and _avale_l_echec(n):
                    return (f"le step `@then` `{func.name}` contient un `except` large qui ne relève "
                            "pas : il avale l'échec de la vérification. Retire le `try/except`, ou "
                            "relève l'exception (`raise`)")
    return ""


# ── Lot VH-02 (V1, V9) : un constat doit LIRE l'application ; une action ne se fait pas par RPC ; Python limité ──────────────
#
# Audit du 2026-10-08 : `constater(statut == attendu)` où les deux côtés viennent du Gherkin, `constater(True)`,
# `constater(page.url)` ou `constater(a == a)` passaient toutes les gardes et donnaient `conforme`. Et un `Quand je valide la
# commande` codé `context.odoo.env[m].write({"state": "done"})` suivi d'un `Alors l'état technique … est "done"` sortait
# `conforme` sans que l'interface ni la logique métier aient été exercées. Gardes de FORME (un filet, pas une preuve) : le
# runtime garde le dernier mot (`constater` refuse un objet qui ne prouve rien, un constat échoué avalé → `indetermine`).
#
# Revue du 2026-10-08 (2e passe) : la lecture de l'application se suit désormais à travers une valeur que le TEST écrit dans
# `context` (une valeur du Gherkin rangée dans `context.valeur` n'est pas une lecture), le passage de `context` à un helper,
# `getattr(context, "<attribut>")`, une affectation sous un `if`/`for`/`while` qui lit l'application, un `.append`/`.update`
# et une affectation indicée ; `constater(condition=…)` et les arguments déballés sont vus ; les fonctions imbriquées sont
# jugées chacune avec ses propres variables.

# Ce que Behave pose sur `context` à partir du TEXTE du test (tableau, docstring, scénario…) : ce n'est pas l'application.
_CONTEXTE_DU_TEST = frozenset({"table", "text", "scenario", "feature", "config", "tags", "active_outline", "step"})
# Modules qu'un fichier de steps généré peut importer. Tout le reste est refusé : un import est le moyen le plus court de
# sortir du cadre (nouvelle connexion, réseau, système de fichiers, harnais).
_IMPORTS_AUTORISES = frozenset({
    "__future__", "behave", "_base_helpers", "features", "playwright", "re", "json", "datetime", "decimal", "time", "math",
    "unicodedata", "string", "collections", "itertools", "functools", "typing", "uuid", "random", "calendar", "zoneinfo",
    "dateutil", "logging", "copy",
})
_APPELS_INTERDITS = frozenset({"exec", "eval", "compile", "__import__", "open", "globals", "vars", "locals", "breakpoint"})
_ATTRIBUTS_INTERDITS = frozenset({"__dict__", "__globals__", "__builtins__", "__code__", "_runner", "__class__",
                                  "web_password", "odoo_password", "totp_secret", "injected_session"})
# Dans un `@when`/`@then`, un objet Odoo ne sert qu'à LIRE : toute autre méthode (create, write, action_confirm,
# button_confirm, execute_kw…) ferait l'action par RPC au lieu de l'interface.
_LECTURES_RPC_PERMISES = frozenset({"search", "read", "search_read", "browse", "fields_get", "name_get", "name_search",
                                    "read_group", "exists", "mapped", "filtered", "sorted", "with_context", "ref", "get",
                                    "search_count", "default_get", "keys", "values", "items"})
_MUTATIONS = frozenset({"append", "extend", "update", "add", "insert", "setdefault", "appendleft"})


def _cibles(cible: ast.AST) -> list[str]:
    """Noms locaux écrits par une cible d'affectation (`x`, `a, b`, `*r`, et la BASE de `x[...]`)."""
    if isinstance(cible, ast.Name):
        return [cible.id]
    if isinstance(cible, (ast.Tuple, ast.List)):
        return [n for c in cible.elts for n in _cibles(c)]
    if isinstance(cible, ast.Starred):
        return _cibles(cible.value)
    if isinstance(cible, ast.Subscript):
        return _cibles(cible.value)
    return []


def _attributs_contexte_ecrits(cible: ast.AST) -> list[str]:
    if isinstance(cible, ast.Attribute) and isinstance(cible.value, ast.Name) and cible.value.id == "context":
        return [cible.attr]
    if isinstance(cible, (ast.Tuple, ast.List)):
        return [a for c in cible.elts for a in _attributs_contexte_ecrits(c)]
    return []


class _Lecture:
    """Dit si une expression lit l'application, pour UNE fonction, étant donné les variables locales déjà « lues » et les
    attributs de `context` qui portent une valeur venue de l'application."""

    def __init__(self, locaux: set[str], contexte_lu):
        self.locaux = locaux
        self.contexte_lu = contexte_lu  # callable(attr) -> bool

    def depend(self, expr: ast.AST | None) -> bool:
        if expr is None:
            return False
        for n in _noeuds_sans_fonctions(expr):
            if isinstance(n, ast.Name) and n.id in self.locaux:
                return True
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "context":
                if self.contexte_lu(n.attr):
                    return True
            if isinstance(n, ast.Call):
                if any(isinstance(a, ast.Name) and a.id == "context" for a in n.args):
                    return True  # `lire_statut(context)` : un helper qui reçoit `context` lit l'application
                if (isinstance(n.func, ast.Name) and n.func.id == "getattr" and len(n.args) >= 2
                        and isinstance(n.args[0], ast.Name) and n.args[0].id == "context"
                        and isinstance(n.args[1], ast.Constant) and self.contexte_lu(str(n.args[1].value))):
                    return True
        return False


def _noeuds_sans_fonctions(racine: ast.AST):
    """`ast.walk` qui ne descend pas dans les fonctions et lambdas imbriquées (jugées à part, avec leurs propres variables)."""
    pile = [racine]
    while pile:
        n = pile.pop()
        yield n
        for enfant in ast.iter_child_nodes(n):
            if not isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                pile.append(enfant)


def _parcourir(instructions, lecture: _Lecture, sous_lecture: bool, sortie: list) -> None:
    """Rend, pour chaque affectation de la fonction, `(noms_locaux, attributs_context, lue)` ; `lue` tient compte du flot de
    contrôle (sous un `if`/`for`/`while` dont le test lit l'application, une affectation en dépend aussi)."""
    for st in instructions:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(st, ast.Assign):
            lue = sous_lecture or lecture.depend(st.value)
            for t in st.targets:
                sortie.append((_cibles(t), _attributs_contexte_ecrits(t), lue))
        elif isinstance(st, (ast.AugAssign, ast.AnnAssign)):
            lue = sous_lecture or lecture.depend(st.value)
            sortie.append((_cibles(st.target), _attributs_contexte_ecrits(st.target), lue))
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute):
            appel = st.value
            if appel.func.attr in _MUTATIONS:
                lue = sous_lecture or any(lecture.depend(a) for a in appel.args) or any(
                    lecture.depend(k.value) for k in appel.keywords)
                sortie.append((_cibles(appel.func.value), [], lue))
        elif (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Name)
              and st.value.func.id == "setattr" and len(st.value.args) >= 3
              and isinstance(st.value.args[0], ast.Name) and st.value.args[0].id == "context"
              and isinstance(st.value.args[1], ast.Constant)):
            sortie.append(([], [str(st.value.args[1].value)], sous_lecture or lecture.depend(st.value.args[2])))
        elif isinstance(st, (ast.For, ast.AsyncFor)):
            lue = sous_lecture or lecture.depend(st.iter)
            sortie.append((_cibles(st.target), _attributs_contexte_ecrits(st.target), lue))
            _parcourir(st.body, lecture, lue, sortie)
            _parcourir(st.orelse, lecture, sous_lecture, sortie)
        elif isinstance(st, (ast.If, ast.While)):
            lue = sous_lecture or lecture.depend(st.test)
            _parcourir(st.body, lecture, lue, sortie)
            _parcourir(st.orelse, lecture, lue, sortie)
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            for item in st.items:
                if item.optional_vars is not None:
                    sortie.append((_cibles(item.optional_vars), [], sous_lecture or lecture.depend(item.context_expr)))
            _parcourir(st.body, lecture, sous_lecture, sortie)
        elif isinstance(st, ast.Try):
            for bloc in (st.body, st.orelse, st.finalbody, *[h.body for h in st.handlers]):
                _parcourir(bloc, lecture, sous_lecture, sortie)
        # Expressions d'affectation (`:=`) et compréhensions dans n'importe quelle instruction.
        for n in _noeuds_sans_fonctions(st):
            if isinstance(n, ast.NamedExpr):
                sortie.append((_cibles(n.target), [], sous_lecture or lecture.depend(n.value)))
            elif isinstance(n, ast.comprehension):
                sortie.append((_cibles(n.target), [], sous_lecture or lecture.depend(n.iter)))


def _analyse_des_lectures(tree: ast.AST, attributs_harnais: frozenset[str] | None):
    """Point fixe sur tout le fichier : variables locales « lues » par fonction, et attributs de `context` qui portent une
    valeur de l'application. Un attribut écrit par CE fichier n'est lu que si TOUTES ses affectations lisent l'application ;
    un attribut non écrit ici est lu s'il est posé par le harnais (ou, harnais inconnu, s'il n'est pas une donnée du test)."""
    fonctions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    ecrits: dict[str, bool] = {}
    for f in fonctions:
        for n in ast.walk(f):
            for t in (n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)]
                      if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []):
                for a in _attributs_contexte_ecrits(t):
                    ecrits.setdefault(a, True)  # optimiste au départ, le point fixe ne fait que retirer

    def contexte_lu(attr: str) -> bool:
        if attr in _CONTEXTE_DU_TEST:
            return False
        if attr in ecrits:
            return ecrits[attr]
        return attributs_harnais is None or attr in attributs_harnais

    locaux: dict[int, set[str]] = {}
    for _ in range(12):
        avant = (dict(ecrits), {k: set(v) for k, v in locaux.items()})
        valeurs: dict[str, list[bool]] = {}
        for f in fonctions:
            lus = locaux.setdefault(id(f), set())
            if not _decorateurs(f):  # helper non décoré : ses paramètres viennent d'un step
                lus |= {a.arg for a in f.args.args + f.args.kwonlyargs if a.arg != "context"}
            lecture = _Lecture(lus, contexte_lu)
            changement = True
            while changement:
                changement = False
                affectations: list = []
                _parcourir(f.body, lecture, False, affectations)
                for noms, attrs, lue in affectations:
                    if lue and not set(noms) <= lus:
                        lus |= set(noms)
                        changement = True
                    for a in attrs:
                        valeurs.setdefault(a, []).append(lue)
        for a in ecrits:
            ecrits[a] = all(valeurs.get(a, [False]))
        if (ecrits, locaux) == avant:
            break
    return fonctions, locaux, contexte_lu


def _condition_du_constat(appel: ast.Call):
    """La condition d'un `constater*` (positionnelle ou `condition=`), ou « » si l'appel la déballe (`*args`, `**kwargs`)."""
    if any(isinstance(a, ast.Starred) for a in appel.args) or any(k.arg is None for k in appel.keywords):
        return ""
    if appel.args:
        return appel.args[0]
    return next((k.value for k in appel.keywords if k.arg in {"condition", "locator", "element"}), None)


def _constat_sans_lecture(tree: ast.AST, attributs_harnais: frozenset[str] | None = None) -> str:
    """Un `constater*` dont la condition ne lit rien de l'application, ou qui est une tautologie, ou un `constater` redéfini."""
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _CONSTATER:
            return f"redéfinition de `{n.name}` : seule la bibliothèque définit les constats"
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in _CONSTATER for t in n.targets):
            return "réaffectation de `constater` : seule la bibliothèque définit les constats"
        if isinstance(n, ast.alias) and n.name in _CONSTATER and n.asname and n.asname != n.name:
            return f"`{n.name}` importé sous un autre nom (`{n.asname}`) : importe-le sous son nom"
    fonctions, locaux, contexte_lu = _analyse_des_lectures(tree, attributs_harnais)
    for func in fonctions:
        lecture = _Lecture(locaux.get(id(func), set()), contexte_lu)
        for appel in _noeuds_sans_fonctions(func):
            if not (isinstance(appel, ast.Call) and _nom_appele(appel) in _CONSTATER):
                continue
            condition = _condition_du_constat(appel)
            nom = _nom_appele(appel)
            if condition == "":
                return f"`{nom}(…)` dans `{func.name}` avec des arguments déballés (`*`/`**`) : écris la condition en clair"
            if condition is None:
                continue  # appel sans condition : le runtime le refuse (TypeError), rien à juger ici
            if isinstance(condition, ast.Constant):
                return f"`{nom}({ast.unparse(condition)}, …)` dans `{func.name}` : une condition constante ne vérifie rien"
            if (isinstance(condition, ast.Compare) and len(condition.comparators) == 1
                    and ast.dump(condition.left) == ast.dump(condition.comparators[0])):
                return f"`{ast.unparse(condition)}` dans `{func.name}` : une comparaison d'une valeur à elle-même est toujours vraie"
            if not lecture.depend(condition):
                return (f"`{nom}({ast.unparse(condition)[:60]}, …)` dans `{func.name}` ne lit rien de l'application : la "
                        "condition ne dépend que de valeurs écrites dans le test (Gherkin, constantes, ou rangées par le test "
                        "dans `context`). Lis la valeur à l'écran (`context.page`), par RPC (`context.odoo`) ou par l'oracle, "
                        "puis compare-la")
    return ""


def _condition_creuse(condition: ast.AST | None, lecture: _Lecture) -> bool:
    """Une condition de constat ou d'`assert` qui ne prouve rien : absente, constante, comparée à elle-même, ou sans lecture.
    Arguments déballés (`""`) : impossible à juger ici, donc réputée réelle (sens prudent)."""
    if isinstance(condition, str):
        return False
    if condition is None:
        return True
    if isinstance(condition, ast.Constant):
        return True
    if (isinstance(condition, ast.Compare) and len(condition.comparators) == 1
            and ast.dump(condition.left) == ast.dump(condition.comparators[0])):
        return True
    return not lecture.depend(condition)


def verifications_creuses(tree: ast.Module) -> set[int]:
    """`id` des fonctions `@then`/`@step` qui ne prouvent RIEN (décision D30, 2026-10-09).

    Sert à distinguer, dans une correction automatique, ce qui RENFORCE (une vérification vide réécrite en vraie) de ce qui
    AFFAIBLIT (une vérification réelle supprimée ou changée). Classement PRUDENT — dans le doute, la vérification est
    réelle (donc gelée) : une vérification n'est creuse que si
    - un `except` large y avale l'échec ; ou
    - toutes ses affirmations sont jugeables ici (`constater*`, `assert`) et AUCUNE ne lit l'application (constante,
      tautologie, valeur du seul test) — zéro affirmation compris.
    Un `expect(...)`, un helper de la bibliothèque qui constate, un appel à une fonction du fichier, un `raise`, ou tout
    appel qui reçoit `context` ou une valeur lue de l'application comptent comme une vraie lecture : on ne sait pas les
    juger ici, on ne les déclare donc jamais creux (revue D30-D32, C3).
    Harnais inconnu (`None`) : un attribut de `context` non écrit par le fichier est réputé lu — toujours le sens prudent.
    """
    fonctions, locaux, contexte_lu = _analyse_des_lectures(tree, None)
    locales = {f.name for f in fonctions}
    constatent = _helpers_qui_constatent() - _CONSTATER
    creuses: set[int] = set()
    for func in fonctions:
        if not (_decorateurs(func) & {"then", "step"}):
            continue
        if any(isinstance(n, ast.ExceptHandler) and _avale_l_echec(n) for n in ast.walk(func)):
            creuses.add(id(func))
            continue
        lecture = _Lecture(locaux.get(id(func), set()), contexte_lu)
        reelle = False
        for n in _noeuds_sans_fonctions(func):
            if isinstance(n, ast.Assert):
                reelle = reelle or not _condition_creuse(n.test, lecture)
            elif isinstance(n, ast.Raise):
                reelle = True  # revue D30-D32 (C3) : `if lu != attendu: raise AssertionError(…)` prouve quelque chose
            elif isinstance(n, ast.Call):
                nom = _nom_appele(n)
                if nom in _CONSTATER:
                    reelle = reelle or not _condition_creuse(_condition_du_constat(n), lecture)
                elif nom == "expect" or nom in constatent or nom in locales:
                    reelle = True
                elif any((isinstance(a, ast.Name) and a.id == "context") or lecture.depend(a)
                         for a in (*n.args, *(k.value for k in n.keywords))):
                    # Revue D30-D32 (C3) : un appel qu'on ne sait pas juger (helper par alias…) qui reçoit `context` ou
                    # une valeur lue de l'application peut vérifier — réputé réel (sens prudent).
                    reelle = True
        if not reelle:
            creuses.add(id(func))
    return creuses


def _forbidden_ecriture_rpc(tree: ast.AST) -> str:
    """Dans un `@when`/`@then`, un objet Odoo ne sert qu'à LIRE (liste blanche) — alias locaux suivis."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) or not (_decorateurs(func) & {"when", "then"}):
            continue
        odoo: set[str] = set()

        def touche_odoo(expr: ast.AST) -> bool:
            return any((isinstance(n, ast.Attribute) and n.attr == "odoo" and isinstance(n.value, ast.Name)
                        and n.value.id == "context") or (isinstance(n, ast.Name) and n.id in odoo)
                       for n in ast.walk(expr))

        change = True
        while change:
            change = False
            for n in ast.walk(func):
                if isinstance(n, ast.Assign) and touche_odoo(n.value):
                    for t in n.targets:
                        nouveaux = set(_cibles(t)) - odoo
                        if nouveaux:
                            odoo |= nouveaux
                            change = True
        for appel in ast.walk(func):
            if (isinstance(appel, ast.Call) and isinstance(appel.func, ast.Attribute)
                    and appel.func.attr not in _LECTURES_RPC_PERMISES and touche_odoo(appel.func.value)):
                return (f"`{ast.unparse(appel.func)[:70]}(…)` dans le step `{func.name}` : dans un Quand/Alors, Odoo ne sert "
                        "qu'à LIRE (search, read, browse…) ; une action par RPC contournerait l'interface et la logique "
                        "testées. Prépare les données dans un `@given`, agis par l'interface (`context.page`)")
    return ""


def _forbidden_python(tree: ast.AST) -> str:
    """Imports hors liste blanche, appels dynamiques (`exec`, `eval`, `open`…), introspection du harnais, secrets."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for alias in n.names:
                if alias.name.split(".")[0] not in _IMPORTS_AUTORISES:
                    return f"`import {alias.name}` : module non autorisé dans un fichier de steps"
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] not in _IMPORTS_AUTORISES:
            return f"`from {n.module} import …` : module non autorisé dans un fichier de steps"
        # Lot VH-06 (revue) : `from _base_helpers import _executer_oracle` contournait l'interdiction d'interroger l'oracle à
        # la main. Les noms privés de la bibliothèque sont son mécanisme, pas son interface.
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "_base_helpers":
            prives = [a.name for a in n.names if a.name.startswith("_")]
            if prives:
                return (f"`from _base_helpers import {prives[0]}` : nom privé de la bibliothèque — utilise les steps du "
                        "catalogue ou les helpers publics")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _APPELS_INTERDITS:
            return f"`{n.func.id}(…)` : appel interdit dans un fichier de steps"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"getattr", "setattr", "delattr", "hasattr"}:
            if len(n.args) < 2 or not isinstance(n.args[1], ast.Constant):
                return f"`{n.func.id}` avec un nom d'attribut calculé : écris l'attribut en clair"
            if str(n.args[1].value) in _ATTRIBUTS_INTERDITS:
                return f"`{n.func.id}(…, {n.args[1].value!r})` : attribut réservé au harnais ou secret"
        if isinstance(n, ast.Attribute) and n.attr in _ATTRIBUTS_INTERDITS:
            return f"`.{n.attr}` : attribut réservé au harnais ou secret, interdit dans un fichier de steps"
        # Revue D30-D32 : `global helper; helper = lambda …` dans une fonction réécrivait un helper lu par une vérification
        # sans toucher la liaison de module que le gel compare (réparation comme correction).
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            return (f"`{'global' if isinstance(n, ast.Global) else 'nonlocal'} {', '.join(n.names)}` : un step ne réaffecte "
                    "pas un nom du module ; range la valeur dans `context`")
    return ""


def _message_gel(outil: str, touche: list[str]) -> str:
    return (f"[{outil}] VERIFICATION_GELEE : une réparation corrige OÙ le test lit l'application (sélecteur, attente, "
            "navigation), jamais CE QU'IL VÉRIFIE : " + " ; ".join(touche[:6]) + ". Remets ces vérifications à "
            "l'identique ; si tu conclus que le test vérifie la mauvaise chose, ne réécris rien et dis-le.")


def _message_essai(outil: str, tires: list[str]) -> str:
    """Lot VH-07 (D26, condition 4) : ce que l'agent n'a vu QUE pendant un essai ne devient pas un attendu."""
    cites = " ; ".join(list(dict.fromkeys(tires))[:6])
    return (f"[{outil}] VALEUR_TIREE_DE_L_ESSAI : {cites} — la spécification ne le dit pas. Un « Alors » vérifie ce que la "
            "SPÉCIFICATION annonce, jamais une donnée que l'application a montrée à l'essai (elle peut justement se tromper). "
            "Cite la valeur de la spécification ; si elle n'en donne pas, vérifie ce qu'elle annonce autrement, ou dis dans ta "
            "réponse que ce point n'est pas vérifiable. (Les noms de champs, de boutons et de pages vus à l'essai restent "
            "utilisables.)")


def _chaines_hors_actions(tree: ast.AST) -> list[str]:
    """Les chaînes d'un fichier de steps qui peuvent servir une VÉRIFICATION : tout le fichier (constantes de module et
    fonctions d'aide comprises — une valeur recopiée s'y cachait, contre-relecture du 2026-10-11), sauf le corps des fonctions
    d'ACTION (`@given`/`@when` sans `@then`), où citer ce qu'un essai a montré sert à cliquer, pas à juger."""
    actions: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorateurs = _decorateurs(node)
            if decorateurs & {"given", "when"} and "then" not in decorateurs and "step" not in decorateurs:
                actions.update(id(n) for n in ast.walk(node))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in actions]


def _message_litteraux(outil: str, ecarts) -> str:
    lignes = [f"[{outil}] LITTERAL_NON_OBSERVE : ce test cite ce qui n'a pas été observé sur l'application."]
    for e in ecarts[:8]:
        lignes.append(f"- {e.ou} : « {e.cite} » — {e.raison}" + (f" ; observé : « {e.observe} »" if e.observe else ""))
    lignes.append("Utilise le nom observé À L'IDENTIQUE (accents et casse compris), ou inspecte la page "
                  "(`inspect_page_snapshot` / `inspect_page_form`) pour le relever, puis réécris.")
    return "\n".join(lignes)


# Lot VH-06 (banc base-4 essai 2 et base-5 essai 1, `client_creation_valide`) : l'agent a écrit dans le Gherkin la SÉQUENCE
# d'échappement d'un caractère (barre oblique inverse, `u`, quatre chiffres hexadécimaux) au lieu du caractère. Gherkin ne
# décode rien : le test cherchait ces six caractères à l'écran, ne les trouvait pas, et sortait `non_conforme` sur une
# application saine (faux rouge). Signal de STRUCTURE du fichier écrit, pas une lecture du sens du texte.
_ECHAPPEMENT_LITTERAL = re.compile(r"\\u[0-9a-fA-F]{4}")


def _echappements_litteraux(content: str) -> list[str]:
    """Hors commentaires, et hors du step à motif (une expression régulière peut légitimement écrire un point de code)."""
    trouves: set[str] = set()
    for ligne in content.splitlines():
        if ligne.lstrip().startswith("#") or 'un texte de la forme "' in ligne:
            continue
        trouves.update(_ECHAPPEMENT_LITTERAL.findall(ligne))
    return sorted(trouves)


# Lot VH-06 : le gabarit `{relevé:nom}` a existé le temps de deux relectures, puis a été RETIRÉ (il rendait `conforme` des
# vérifications qui ne prouvaient rien). Écrit quand même, il ne serait plus qu'un texte : « la page n'affiche pas
# "{relevé:numero}" » serait toujours vraie. Refusé, accents, casse et espaces pliés.
_GABARIT_DE_RELEVE = re.compile(r"\{\s*releve")


def _gabarit_de_releve(content: str) -> bool:
    plie = "".join(c for c in unicodedata.normalize("NFD", content) if unicodedata.category(c) != "Mn").casefold()
    return any(_GABARIT_DE_RELEVE.search(ligne) for ligne in plie.splitlines() if not ligne.lstrip().startswith("#"))


def _refus_secret_masque(content: str, outil: str) -> str:
    """Refus déterministe d'un test qui contient le MASQUE d'un secret (`[secret]`) au lieu d'une vraie valeur.

    Mesuré le 2026-10-06 (banc web, essai 1) : le harnais de qualification remplace les secrets du projet par
    `[secret]` dans ce que voit l'IA ; elle a recopié ce masque comme mot de passe, SauceDemo a refusé la
    connexion à juste titre, et le verdict a conclu « non conforme » sur une application saine. Le refus
    arrive à l'ÉCRITURE : l'IA peut se corriger tout de suite, au lieu d'un faux verdict après un run entier."""
    if SECRET_MASQUE not in content:
        return ""
    return (f"[{outil}] SECRET_NON_RESOLU : le texte contient « {SECRET_MASQUE} », le masque d'un secret et "
            "jamais une valeur saisissable. N'écris aucun identifiant ni mot de passe dans un test : la "
            "connexion du projet est AUTOMATIQUE (step « j'accède à la page d'accueil de l'application »), et "
            "pour un autre compte du projet utilise « je me connecte en tant que \"<libellé>\" ». Retire la "
            "saisie du secret puis rappelle l'outil.")


def write_feature_file(ctx: "ToolContext", content: str) -> "ToolOutcome":
    if not content.strip():
        return _outcome("[write_feature_file] contenu vide", ok=False)
    if _gabarit_de_releve(content):
        return _outcome(
            "[write_feature_file] RELEVE_INCONNU : `{relevé:…}` n'existe pas — aucune valeur n'est gardée d'un step à "
            "l'autre. Pour retrouver côté serveur ce que l'écran affiche : « la liste \"<chemin>\" de l'oracle \"<requête>\" "
            "contient un élément dont \"<clé>\" est la valeur affichée pour \"<libellé>\" ». Puis rappelle "
            "write_feature_file.", ok=False)
    echappements = _echappements_litteraux(content)
    if echappements:
        return _outcome(
            "[write_feature_file] ECHAPPEMENT_LITTERAL : le fichier contient " + ", ".join(echappements[:6]) + " écrit en "
            "toutes lettres. Gherkin ne décode pas ces séquences : le test chercherait ces caractères tels quels à l'écran. "
            "Écris le caractère lui-même (« » é à, espace ordinaire), puis rappelle write_feature_file.", ok=False)
    refus_secret = _refus_secret_masque(content, "write_feature_file")
    if refus_secret:
        return _outcome(refus_secret, ok=False)
    from behave.parser import ParserError, parse_feature
    try:
        feature = parse_feature(content, language="fr")
        scenarios = list(feature.walk_scenarios()) if feature else []
        outlines_vides = feature and any(
            hasattr(s, "examples") and not s.scenarios
            for s in feature.walk_scenarios(with_outlines=True))
    except ParserError as exc:
        return _outcome(f"[write_feature_file] GHERKIN_INVALIDE : {exc}", ok=False)
    if not scenarios or outlines_vides or any(not scenario.steps for scenario in scenarios):
        return _outcome(
            "[write_feature_file] SCENARIO_VIDE : fournis au moins un scénario avec des "
            "étapes ; chaque plan de scénario doit avoir des exemples exécutables.", ok=False)
    # Lot 12 (D11) : référence PROUVÉE inexistante → refus bloquant, là où la source fait autorité
    # (champ relationnel Odoo par `name_search` RPC ; `<select>` entièrement relevé).
    recherche = None
    if ctx.connector is not None:
        def recherche(modele, texte, limite):
            return ctx.connector.name_search(modele, texte, limite)
    # Lot PT-02d (interrupteur allumé, projet à variables) : variables inconnues, mal écrites, mal placées ou hors guillemets
    # refusées ici, avec les règles mêmes de l'exécution. BLOQUANT. Interrupteur éteint : contrôle d'avant, inchangé.
    from testpilot.generation import variables_de_test
    fautes = variables_de_test.refus(content, ctx.variables_de_test) if ctx.variables_de_test else []
    if ctx.references_figees is not None:   # réparation, correction : les variables du test de référence ne bougent pas
        fautes += variables_de_test.refus_references_changees(content, ctx.references_figees)
    if fautes:
        return _outcome("[write_feature_file] VARIABLE_DE_TEST : " + " ; ".join(fautes[:5])
                        + ". Puis rappelle write_feature_file.", ok=False)
    refus = verifier_references(content, ctx.options_select, ctx.champs_relationnels, recherche,
                                ignorer_variables=bool(ctx.variables_de_test or ctx.references_figees))
    if refus:
        return _outcome(message_refus(refus), ok=False)
    # F26(b), migration 58 : question DIFFÉRENTE de `verifier_references` ci-dessus — pas « cette
    # entité existe-t-elle » (lot 12, D11) mais « CE scénario a-t-il lui-même créé l'entité que le
    # métier a désignée avant de la référencer ». Les deux contrôles coexistent, aucun ne remplace
    # l'autre. Gated : appelé seulement quand le métier a déclaré la dépendance (`ToolContext`,
    # jamais une heuristique générale sur la nature de la référence — cf. le faux positif
    # SauceDemo mesuré en diagnostic, qui a écarté une portée non gated).
    if ctx.depend_dun_autre_cas_du_groupe and ctx.etat_a_creer_par_ce_cas:
        refus_entite = enregistrement_lint.verifier_entite_a_creer(content)
        if refus_entite:
            return _outcome(refus_entite, ok=False)
    # Lot VH-03 (V3) : en réparation, les vérifications de la version de référence sont GELÉES. BLOQUANT.
    if ctx.gel_feature:
        touche = gel_verifications.feature_modifiee(ctx.gel_feature, content)
        if touche:
            return _outcome(_message_gel("write_feature_file", touche), ok=False)
    # Lot VH-05 (D24) : tout champ, bouton ou page cité existe À L'IDENTIQUE dans ce que l'exploration a observé. BLOQUANT.
    indications = ""
    if ctx.annuaire is not None:
        ecarts = litteraux_observes.controler_feature(content, ctx.annuaire)
        refus = [e for e in ecarts if e.bloquant]
        if refus:
            return _outcome(_message_litteraux("write_feature_file", refus), ok=False)
        indications = "".join(f" Attention ({e.ou}) : « {e.cite} » — {e.raison}." for e in ecarts)
    # Lot VH-07 (D26, condition 4) : un littéral vu seulement pendant un essai n'est pas un attendu. BLOQUANT.
    tires = essai_tools.valeurs_tirees_de_l_essai(feature, getattr(ctx, "essai", None), ctx.requirements)
    if tires:
        return _outcome(_message_essai("write_feature_file", tires), ok=False)
    path = ctx.generated_dir / f"{ctx.module_name}.feature"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_feature_file] OK — {path.name}, {len(scenarios)} scénario(s).{indications}",
        feature_content=content,
    )


def write_steps_file(ctx: "ToolContext", content: str) -> "ToolOutcome":
    refus_secret = _refus_secret_masque(content, "write_steps_file")
    if refus_secret:
        return _outcome(refus_secret, ok=False)
    # Lot PT-02d (revue du 2026-10-14, faux vert) : une variable dans le code des steps n'est jamais remplacée — un constat
    # `"{{client}}" not in texte` y est toujours vrai. Dès que l'agent connaît la syntaxe (interrupteur allumé), ou que le
    # test de référence en écrit (réparation, correction) : refusée.
    if ctx.variables_de_test or ctx.references_figees:
        from testpilot.generation import variables_de_test
        fautes = variables_de_test.refus_dans_le_code(content)
        if fautes:
            return _outcome("[write_steps_file] VARIABLE_DE_TEST : " + " ; ".join(fautes[:5])
                            + ". Puis rappelle write_steps_file.", ok=False)

    # 1. Guillemets typographiques → ast.parse échouerait au run.
    curly = {c for c in content if c in _CURLY}
    if curly:
        return _outcome(
            "[write_steps_file] SYNTAX_ERROR : guillemets typographiques interdits "
            f"({''.join(sorted(curly))}). Utilise ' et \" ASCII, puis rappelle write_steps_file.",
            ok=False,
        )

    # 2. Syntaxe Python valide.
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return _outcome(f"[write_steps_file] SYNTAX_ERROR : {exc.msg} (ligne {exc.lineno})", ok=False)

    # 3. Aucun transport réinventé (décision 0003).
    forbidden = _forbidden_transport(tree, content)
    if forbidden:
        return _outcome(
            f"[write_steps_file] TRANSPORT_INTERDIT : {forbidden}. Un step ne fabrique pas ses "
            "propres appels HTTP — utilise `context.odoo` (lecture/écriture RPC) ou `context.page` "
            "(Playwright) pour agir dans le navigateur. Réutilise d'abord les steps partagés "
            "listés dans le prompt, puis rappelle write_steps_file.",
            ok=False,
        )

    # 3bis. Aucun comptage réécrit par l'agent (§F9) : régime BLOQUANT, comme le transport.
    recompte = _forbidden_recount(tree)
    if recompte:
        return _outcome(
            f"[write_steps_file] COMPTAGE_INTERDIT : {recompte}. Un step ne recompte pas les "
            "enregistrements lui-même (un tiers actif sur l'instance fausserait le verdict). "
            "Utilise les steps du catalogue : « le nombre d'enregistrements dans le modèle "
            "\"<modèle>\" est enregistré pour comparaison », puis « … augmente de 1 » ou "
            "« … n'a pas augmenté ». Si le besoin n'est pas couvert, dis-le dans ta réponse "
            "plutôt que de compter toi-même.",
            ok=False,
        )

    # 3ter. Aucun `source=` forgé sur `constater(...)` (lot 07e, D7) : régime BLOQUANT, comme le
    # transport et le comptage — seuls les helpers internes de la bibliothèque le renseignent.
    source_forgee = _forbidden_source_kwarg(tree)
    if source_forgee:
        return _outcome(
            f"[write_steps_file] SOURCE_FORGEE : {source_forgee}. Un step ne revendique pas lui-même "
            "un recoupement contre l'oracle backend — utilise les steps du catalogue "
            "(« l'oracle \"<nom>\" renvoie <n> résultat(s) », « le champ \"<chemin>\" de l'oracle "
            "\"<nom>\" vaut \"<valeur>\" ») ; `constater(...)` s'appelle sans `source=`.",
            ok=False,
        )

    # 3quater. Aucune référence au mécanisme de preuve réservé au socle (Q1) : BLOQUANT, comme `source=`.
    reserve = _forbidden_reserve_au_socle(tree)
    if reserve:
        return _outcome(
            f"[write_steps_file] MECANISME_RESERVE : {reserve}. Un step ne déclare pas lui-même qu'il est "
            "« non assertif » et ne touche pas au compteur de constats : écris `constater(condition, "
            "\"message\")` dans un `@then`, ou utilise un step du catalogue.",
            ok=False,
        )

    # 3quinquies. Lot VH-02 (V1, V9) : Python limité, aucune action par RPC, un constat lit l'application. BLOQUANT.
    for code, faute, conseil in (
            ("PYTHON_INTERDIT", _forbidden_python(tree), "Utilise les steps du catalogue et `context.page`."),
            ("ACTION_PAR_RPC", _forbidden_ecriture_rpc(tree), ""),
            ("CONSTAT_SANS_LECTURE", _constat_sans_lecture(tree, ctx.attributs_contexte or None), "")):
        if faute:
            return _outcome(f"[write_steps_file] {code} : {faute}. {conseil}".rstrip() + " Puis rappelle write_steps_file.",
                            ok=False)

    # 3septies. Lot VH-03 (V3) : en réparation, les fonctions qui VÉRIFIENT sont gelées, adressage mis à part. BLOQUANT.
    if ctx.gel_steps:
        touche = gel_verifications.steps_modifies(ctx.gel_steps, content)
        if touche:
            return _outcome(_message_gel("write_steps_file", touche), ok=False)

    # 3sexies. Lot VH-05 (D24) : réseau direct, `context.X` inventé ou secret (tous connecteurs) ; sélecteurs par texte libre et
    # libellés non observés (connecteur web avec annuaire). BLOQUANT.
    if ctx.attributs_contexte or ctx.annuaire is not None:
        from testpilot.generation.litteraux_observes import Annuaire
        ecarts = litteraux_observes.controler_steps(content, ctx.annuaire or Annuaire(),
                                                    set(ctx.attributs_contexte) or set())
        regles = {"reseau", "contexte"} | ({"selecteur", "libelle"} if ctx.annuaire is not None else set())
        if not ctx.attributs_contexte:
            regles.discard("contexte")
        refus = [e for e in ecarts if e.bloquant and e.regle in regles]
        if refus:
            return _outcome(_message_litteraux("write_steps_file", refus), ok=False)

    # 3octies. Lot VH-07 (D26, condition 4) : même règle pour un « Alors » écrit à la main. BLOQUANT.
    tires = essai_tools.chaines_tirees_de_l_essai(_chaines_hors_actions(tree), getattr(ctx, "essai", None), ctx.requirements)
    if tires:
        return _outcome(_message_essai("write_steps_file", tires), ok=False)

    # 4. Aucune redéfinition d'un step de la bibliothèque partagée.
    declared = {step.label for step in steps_library.extract_steps(content)}
    clashing = sorted(declared & ctx.reserved_steps)
    if clashing:
        return _outcome(
            "[write_steps_file] AmbiguousStep : ces steps existent déjà dans la "
            f"bibliothèque partagée, ne les redéfinis pas : {clashing}.",
            ok=False,
        )

    # 5. Placement des assertions (lot 03, D4) : régime BLOQUANT, comme le transport et le comptage.
    faute = _forbidden_assertion_placement(tree)
    if faute:
        return _outcome(
            f"[write_steps_file] ASSERTION_MAL_PLACEE : {faute}. Les vérifications s'écrivent "
            "`constater(...)` UNIQUEMENT dans un step `@then`, puis rappelle write_steps_file.",
            ok=False,
        )

    path = ctx.generated_dir / f"{ctx.module_name}_steps.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_steps_file] OK — {path.name}, {len(declared)} step(s) déclaré(s).",
        steps_content=content,
    )
