"""Catalogue des steps de la bibliothèque partagée (§6, décision 0003).

Sert deux besoins qui doivent parler du MÊME catalogue :
- ce qu'on **montre** à l'agent (pour qu'il réutilise au lieu de réinventer) ;
- ce qu'on **refuse** à l'écriture (redéfinition d'un step existant).

Extraction par AST et non par regex : les libellés de la bibliothèque sont souvent écrits
en concaténation implicite multi-lignes ::

    @then('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
          'n\\'existe dans le modèle "{model}"')

Une regex ne capture que le premier fragment et **tronque** le libellé — on montrerait alors
à l'agent un step inexistant, et la détection de collision porterait sur un texte partiel.
Le parseur Python, lui, fusionne ces littéraux : l'AST rend le libellé entier.
"""

from __future__ import annotations

import ast
import functools
import re
from dataclasses import dataclass
from pathlib import Path

import parse as parse_lib  # dépendance transitive de behave — motifs `{champ}` des libellés.

from testpilot import config
from testpilot.generation import interrupteurs

_DECORATORS = {"given", "when", "then", "step"}

# Mot-clé Gherkin (fr) correspondant au décorateur — pour que l'agent sache l'employer.
GHERKIN_KEYWORD = {
    "given": "Soit",
    "when": "Quand",
    "then": "Alors",
    "step": "Soit/Quand/Alors",
}


@dataclass(frozen=True)
class SharedStep:
    keyword: str  # given | when | then | step
    label: str
    source: str = ""  # fichier d'origine
    # Ce que le step FAIT, quand son libellé ne suffit pas à le deviner (décision 0012 / A2 de
    # 0007). Première ligne de la DOCSTRING de la fonction : le code reste la source de vérité,
    # plutôt qu'une table d'annotations à part qui divergerait du comportement réel.
    # Vide pour la grande majorité des steps — on n'annote que les pièges.
    note: str = ""
    # Q1 (D17) : `False` pour un step `@then`/`@step` dont la fonction ne peut consigner AUCUN constat
    # (ni `constater*` ni helper qui en appelle un — point fixe, lu par AST dans `_base_helpers.py`,
    # le code restant la source de vérité). Un tel step (ex. « j'attends la soumission du
    # formulaire ») est une attente, pas une assertion : `write_test_plan` ne le compte pas. `True` par
    # défaut = inconnu ou assertif (jamais plus strict que l'historique quand la bibliothèque n'est pas lisible).
    asserte: bool = True
    # Lot PT-03 : nom de la variable d'environnement qui doit être allumée pour que ce step soit MONTRÉ à l'agent
    # (`@derriere_interrupteur("…")`, lu par AST). Vide = toujours montré. Le step reste réservé et exécutable dans tous
    # les cas : seul le prompt change, pour que l'effet d'un step de plus se mesure avant d'être activé.
    interrupteur: str = ""
    # Lot PT-03 : `@compare_des_nombres` — la valeur attendue de ce step se compare comme un nombre. Lu par AST.
    compare_des_nombres: bool = False
    # Étape 5 (F24) : ce step POSE l'enregistrement courant (`context.last_record_ids`, lui-même ou par un helper), ou le
    # LIT sans le poser (« cet enregistrement »). Lu par AST, point fixe à travers les helpers : le code fait foi.
    pose_enregistrement: bool = False
    lit_enregistrement: bool = False


# ── Quels noms de la bibliothèque CONSIGNENT un constat ? (déplacé de `tools/write.py`, Q1) ──────────
CONSTATER = frozenset({"constater", "constater_visible", "constater_texte"})


def _nom_appele(noeud: ast.Call) -> str:
    cible = noeud.func
    if isinstance(cible, ast.Name):
        return cible.id
    if isinstance(cible, ast.Attribute):
        return cible.attr
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


@functools.lru_cache(maxsize=4)
def _noms_qui_constatent(chemin: str, mtime: float) -> frozenset[str]:
    """Les noms de la bibliothèque qui CONSIGNENT un constat : `constater*`, les fonctions décorées
    `@constat`, et — point fixe — toute fonction qui en appelle une. Lu dans `_base_helpers.py` par
    AST : le code reste la source de vérité, aucune liste à tenir à jour. `mtime` ne sert que de
    clé de cache (un fichier modifié est relu)."""
    try:
        with open(chemin, encoding="utf-8") as handle:
            arbre = ast.parse(handle.read())
    except (OSError, SyntaxError):
        return CONSTATER
    fonctions = {n.name: n for n in arbre.body if isinstance(n, ast.FunctionDef)}
    noms = set(CONSTATER) | {nom for nom, f in fonctions.items() if "constat" in _decorateurs(f)}
    change = True
    while change:
        change = False
        for nom, f in fonctions.items():
            if nom in noms:
                continue
            if any(isinstance(n, ast.Call) and _nom_appele(n) in noms for n in ast.walk(f)):
                noms.add(nom)
                change = True
    return frozenset(noms)


_ENREGISTREMENT_COURANT = "last_record_ids"


def _touche_l_enregistrement(fonction, mode) -> bool:
    """`context.last_record_ids` écrit (`ast.Store`) ou lu (`ast.Load`) dans le corps de `fonction`."""
    return any(isinstance(n, ast.Attribute) and n.attr == _ENREGISTREMENT_COURANT and isinstance(n.ctx, mode)
               and isinstance(n.value, ast.Name) and n.value.id == "context" for n in ast.walk(fonction))


def _point_fixe(fonctions: dict, depart: set[str]) -> set[str]:
    """`depart` + toute fonction de `fonctions` qui en appelle une (jusqu'à stabilité)."""
    noms = set(depart)
    change = True
    while change:
        change = False
        for nom, f in fonctions.items():
            if nom not in noms and any(isinstance(n, ast.Call) and _nom_appele(n) in noms for n in ast.walk(f)):
                noms.add(nom)
                change = True
    return noms


def _poseurs_et_lecteurs(arbre, herites: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())
                         ) -> tuple[set[str], set[str]]:
    """F24 : (fonctions qui POSENT l'enregistrement courant, fonctions qui le LISENT) d'un module — elles-mêmes ou par un
    helper du module ou hérité (`_base_helpers`)."""
    fonctions = {n.name: n for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    posent = _point_fixe(fonctions, set(herites[0]) | {nom for nom, f in fonctions.items()
                                                        if _touche_l_enregistrement(f, ast.Store)})
    lisent = _point_fixe(fonctions, set(herites[1]) | {nom for nom, f in fonctions.items()
                                                        if _touche_l_enregistrement(f, ast.Load)})
    return posent, lisent


@functools.lru_cache(maxsize=4)
def _enregistrement_des_helpers(chemin: str, mtime: float) -> tuple[frozenset[str], frozenset[str]]:
    try:
        with open(chemin, encoding="utf-8") as handle:
            arbre = ast.parse(handle.read())
    except (OSError, SyntaxError):
        return frozenset(), frozenset()
    posent, lisent = _poseurs_et_lecteurs(arbre)
    return frozenset(posent), frozenset(lisent)


def helpers_et_enregistrement(directory: Path | None = None) -> tuple[frozenset[str], frozenset[str]]:
    """F24 : les helpers de `_base_helpers.py` qui posent / lisent l'enregistrement courant (vides si absent)."""
    chemin = (directory or config.STEPS_LIBRARY_DIR) / "_base_helpers.py"
    try:
        mtime = chemin.stat().st_mtime
    except OSError:
        return frozenset(), frozenset()
    return _enregistrement_des_helpers(str(chemin), mtime)


def helpers_qui_constatent(directory: Path | None = None) -> frozenset[str] | None:
    """Les noms qui constatent, lus dans `<directory>/_base_helpers.py` ; `None` si ce fichier est
    absent (bibliothèque factice : on ne présume alors rien, voir `SharedStep.asserte`)."""
    chemin = (directory or config.STEPS_LIBRARY_DIR) / "_base_helpers.py"
    try:
        mtime = chemin.stat().st_mtime
    except OSError:
        return None
    return _noms_qui_constatent(str(chemin), mtime)


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def extract_steps(source_code: str, source: str = "",
                  constatent: frozenset[str] | None = None,
                  enregistrement: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())) -> list[SharedStep]:
    """Steps déclarés dans un module Python (libellés entiers). Vide si le code est invalide.

    `constatent` (Q1, D17) : les noms qui consignent un constat. Fourni, il renseigne
    `SharedStep.asserte` des steps `@then`/`@step` ; absent, `asserte` reste `True` (inconnu)."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    steps: list[SharedStep] = []
    posent, lisent = _poseurs_et_lecteurs(tree, enregistrement)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Première ligne de la docstring = ce que le step FAIT (0012). Une seule ligne : le
        # catalogue est un prompt, pas une documentation — le noyer le rendrait moins lu.
        doc = ast.get_docstring(node) or ""
        note = doc.strip().splitlines()[0].strip() if doc.strip() else ""
        appels = {_nom_appele(n) for n in ast.walk(node) if isinstance(n, ast.Call)}
        interrupteur = next(
            (d.args[0].value for d in node.decorator_list
             if isinstance(d, ast.Call) and _decorator_name(d.func) == "derriere_interrupteur" and d.args
             and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)), "")
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not deco.args:
                continue
            name = _decorator_name(deco.func).lower()
            if name not in _DECORATORS:
                continue
            arg = deco.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                asserte = True
                if constatent is not None and name in ("then", "step"):
                    asserte = bool(appels & constatent)
                steps.append(SharedStep(keyword=name, label=arg.value.strip(), source=source, note=note,
                                        asserte=asserte, interrupteur=interrupteur,
                                        compare_des_nombres="compare_des_nombres" in _decorateurs(node),
                                        pose_enregistrement=node.name in posent,
                                        lit_enregistrement=node.name in lisent and node.name not in posent))
    return steps


def _sans_profils(dossier: Path, racine: Path):
    """Fichiers `.py` de `dossier`, récursivement, en EXCLUANT tout `profils/` (lot 06, D6) — un
    profil n'est jamais inclus par défaut, seulement sur choix explicite (`_fichiers_profil`)."""
    if not dossier.exists():
        return []
    return [p for p in dossier.rglob("*.py") if "profils" not in p.relative_to(racine).parts]


def profils_disponibles(connector_type: str | None, directory: Path | None = None) -> list[str]:
    """Les noms de profil valides pour `connector_type` (lot 06, D6) — un profil n'existe que s'il
    a AU MOINS un fichier (`generic/profils/<nom>.py` et/ou `<connector_type>/profils/<nom>.py`).
    Sert la validation API (`routes/projects.py`) : un `profil_instance` qui n'a NULLE PART de
    fichier est refusé à la saisie, jamais silencieusement ignoré."""
    directory = directory or config.STEPS_LIBRARY_DIR
    noms: set[str] = set()
    for dossier in (directory / "generic" / "profils",
                    directory / connector_type / "profils" if connector_type else None):
        if dossier is not None and dossier.is_dir():
            noms.update(p.stem for p in dossier.glob("*.py") if not p.stem.startswith("_"))
    return sorted(noms)


def _fichiers_profil(directory: Path, connector_type: str, profil_instance: str | None) -> list[Path]:
    """Les fichiers `profils/<profil_instance>.py` (volet `generic/` ET `<connector_type>/`) du
    profil DEMANDÉ — vide si aucun profil choisi, ou si le fichier n'existe pas pour ce volet."""
    if not profil_instance:
        return []
    candidats = [directory / "generic" / "profils" / f"{profil_instance}.py",
                directory / connector_type / "profils" / f"{profil_instance}.py"]
    return [c for c in candidats if c.exists()]


def catalogue(directory: Path | None = None, connector_type: str | None = None,
              profil_instance: str | None = None) -> list[SharedStep]:
    """Tous les steps de la bibliothèque partagée, éventuellement scopés à un connecteur et à un
    profil d'instance.

    Depuis l'audit DA du 2026-08-13, la bibliothèque est rangée en `generic/` (portable, tout
    connecteur) + un sous-dossier par connecteur (`odoo/`, futurs `sap/`, `web/`...) — avant,
    generic/odoo étaient mélangés à plat, sans distinction, ce qui aurait fait bloquer à tort un
    step d'un futur connecteur au libellé proche d'un step Odoo sans rapport.

    `connector_type=None` (défaut) : union complète de TOUT le dossier, récursivement — le même
    comportement qu'avant cette séparation (repli sûr pour les appelants qui n'ont pas encore de
    connecteur résolu, jamais plus restrictif que l'historique).
    `connector_type="odoo"` (etc.) : seulement `generic/` + `<connector_type>/` — jamais les steps
    d'un AUTRE connecteur.

    ⚠️ **`profils/` est TOUJOURS exclu de ces deux parcours** (lot 06, D6) : un profil n'est jamais
    inclus par défaut, seulement sur choix EXPLICITE du projet (`profil_instance`).
    """
    directory = directory or config.STEPS_LIBRARY_DIR
    if not directory.exists():
        return []
    if connector_type is None:
        paths = _sans_profils(directory, directory)
    else:
        paths = (_sans_profils(directory / "generic", directory)
                 + _sans_profils(directory / connector_type, directory)
                 + _fichiers_profil(directory, connector_type, profil_instance))
    constatent = helpers_qui_constatent(directory)
    enregistrement = helpers_et_enregistrement(directory)
    steps: list[SharedStep] = []
    for path in sorted(paths):
        try:
            source = str(path.relative_to(directory)).replace("\\", "/")
            steps.extend(extract_steps(path.read_text(encoding="utf-8"), source=source,
                                       constatent=constatent, enregistrement=enregistrement))
        except OSError:
            continue
    return steps


def reserved_labels(directory: Path | None = None, connector_type: str | None = None) -> frozenset[str]:
    """Libellés réservés — un step généré ne doit jamais les redéfinir (AmbiguousStep)."""
    return frozenset(step.label for step in catalogue(directory, connector_type))


def _origine(step: SharedStep) -> str:
    """Premier segment du chemin source — `generic` ou le nom du connecteur (Phase 1a)."""
    return step.source.split("/", 1)[0] if "/" in step.source else "generic"


# ── Intention (lot 09, C9) — sous-classement à l'INTÉRIEUR de chaque section Soit/Quand/Alors ────
#
# ⚠️ **Un classement par MOTS-CLÉS du libellé, pas une table tenue à jour à la main** — même
# motif que `defect_taxonomy.classify_failure` (référencé par `repair_agent.py`) : le libellé
# FRANÇAIS d'un step suit déjà une convention de verbe assez régulière dans ce dépôt (« je
# renseigne… », « je clique… », « j'accède… ») pour s'y appuyer, plutôt que d'ajouter un champ
# qu'il faudrait poser à la main sur chaque nouveau step et qui divergerait tôt ou tard du code
# réel. Purement COSMÉTIQUE (aide l'agent à scanner un long catalogue) : une mauvaise
# classification range un step dans le mauvais sous-titre, jamais ne le cache ni ne le refuse —
# contrairement aux gardes de `tools/write.py`, ceci ne bloque jamais rien.
_ORDRE_INTENTIONS = ("connexion", "navigation", "saisie", "action", "constat_ui",
                    "constat_serveur", "autre")
_LIBELLE_INTENTION = {
    "connexion": "Connexion", "navigation": "Navigation", "saisie": "Saisie", "action": "Action",
    "constat_ui": "Constat (interface)", "constat_serveur": "Constat (serveur)", "autre": "Autre",
}
_MOTS_CONNEXION = ("je me connecte", "je suis authentifié", "mot de passe", "connexion",
                   "déconnecte")
_MOTS_NAVIGATION = ("j'accède", "je navigue", "j'ouvre la page", "l'url courante",
                    "onglet", "section", "revient à la page précédente")
_MOTS_SAISIE = ("je renseigne", "je sélectionne", "je laisse le champ", "je joins", "je coche",
                "je décoche", "je remplis le formulaire")
_MOTS_CONSTAT_SERVEUR = ("du modèle", "dans le modèle", "état technique", "vaut {nombre",
                        "document lié", "lié(s) par", "comptabilisée", "rapport pdf",
                        "société de travail", "enregistrement(s) existe", "id }")
_MOTS_CONSTAT_UI = ("affiche", "affichée", "affiché", "visible", "la page", "le tableau",
                   "erreur de validation", "fichier téléchargé", "étape affichée",
                   "barre d'état", "n'affiche pas")


def deviner_intention(label: str, keyword: str) -> str:
    """Intention devinée d'un step depuis son libellé (mots-clés français) — jamais une preuve,
    juste un classement de confort pour la lecture du catalogue. `keyword` restreint déjà le
    champ des possibles : un `@then` ne peut être qu'un constat (UI ou serveur), un `@given`/
    `@when` jamais un constat."""
    bas = label.lower()
    if keyword == "then":
        if any(mot in bas for mot in _MOTS_CONSTAT_SERVEUR):
            return "constat_serveur"
        if any(mot in bas for mot in _MOTS_CONSTAT_UI):
            return "constat_ui"
        return "constat_ui"  # défaut : la plupart des `@then` du catalogue portent sur l'écran
    if any(mot in bas for mot in _MOTS_CONNEXION):
        return "connexion"
    if any(mot in bas for mot in _MOTS_NAVIGATION):
        return "navigation"
    if any(mot in bas for mot in _MOTS_SAISIE):
        return "saisie"
    if bas.startswith(("je clique", "j'attends", "je télécharge", "j'accepte", "je refuse",
                       "j'ajoute", "j'enregistre", "j'annule", "je valide", "je déclare")):
        return "action"
    return "autre"


def _section_par_mot_cle(steps: list[SharedStep]) -> str:
    """Un groupe de steps rendu par mot-clé Gherkin (`### Soit (`@given`)`, etc.), sous-classé par
    intention (`#### Saisie`, etc.) dès que le groupe en mélange plusieurs — jamais pour un
    groupe homogène, où le sous-titre n'ajouterait rien à scanner."""
    # (libellé, note) — dédupliqué : une fonction à double décorateur (@when ET @then) apparaît
    # une fois par mot-clé, mais jamais deux fois dans la même section.
    by_keyword: dict[str, dict[str, str]] = {}
    for step in steps:
        note = step.note
        if step.keyword in ("then", "step") and not step.asserte:
            # Q1 (D17) : l'agent doit voir, AVANT d'écrire un plan, qu'une attente n'est pas une preuve.
            note = ("⚠ attente ou navigation : ne vérifie rien, ne compte pas comme assertion"
                    + (f" — {note}" if note else ""))
        by_keyword.setdefault(step.keyword, {}).setdefault(step.label, note)

    lines: list[str] = []
    for keyword in ("given", "when", "then", "step"):
        entrees = sorted(by_keyword.get(keyword, {}).items())
        if not entrees:
            continue
        lines.append(f"### {GHERKIN_KEYWORD[keyword]} (`@{keyword}`)")
        par_intention: dict[str, list[tuple[str, str]]] = {}
        for label, note in entrees:
            par_intention.setdefault(deviner_intention(label, keyword), []).append((label, note))
        sous_titres = len({i for i in par_intention if par_intention[i]}) > 1
        for intention in _ORDRE_INTENTIONS:
            groupe = par_intention.get(intention)
            if not groupe:
                continue
            if sous_titres:
                lines.append(f"#### {_LIBELLE_INTENTION[intention]}")
            for label, note in groupe:
                lines.append(f"- {label}")
                if note:
                    lines.append(f"  → {note}")
        lines.append("")
    return "\n".join(lines).rstrip()


def as_prompt_section(steps: list[SharedStep]) -> str:
    """Rend le catalogue pour le prompt système, groupé par ORIGINE (générique / connecteur)
    puis par mot-clé Gherkin, chaque origine dans sa propre balise XML.

    Sans cette section, l'agent ne PEUT PAS réutiliser la bibliothèque : on lui demandait de
    ne pas la redéfinir sans jamais la lui montrer (décision 0003).

    Le catalogue dit aussi ce que `{field}` DÉSIGNE (décision 0007, A1) : montrer le libellé
    d'un step sans la sémantique de ses paramètres laissait l'agent combler le vide par une
    convention raisonnable mais fausse (le libellé humain), d'où un `[name="Raison de la
    demande"]` introuvable. Le repli technique (phase B) rattrape ce cas ; cette annotation
    apprend la convention propre — sélecteur exact, donc plus fiable.

    Regroupement par origine (Phase 1d, recommandation Anthropic sur les balises XML pour du
    contenu long/de référence) : l'agent voit distinctement ce qui est portable (`generic`) de
    ce qui appartient au connecteur actif — utile dès qu'un 2ᵉ connecteur existera.
    """
    # Lot PT-03 : un step derrière un interrupteur éteint n'est pas montré (lu à chaque appel, jamais figé à l'import).
    steps = [s for s in steps if not s.interrupteur or interrupteurs.allume(s.interrupteur)]
    if not steps:
        return ""

    lines = [
        "Ces steps EXISTENT DÉJÀ et sont chargés automatiquement. Réutilise-les en copiant le",
        "libellé **mot pour mot** dans le `.feature` — ne les redéfinis pas (rejeté), et n'écris",
        "pas de variante qui ferait la même chose sous un autre nom.",
        "",
        "**Paramètre `{field}`** — c'est TOUJOURS le nom TECHNIQUE du champ, JAMAIS son libellé",
        "affiché : l'attribut HTML `name` du contrôle dans les steps d'interface (renseigner /",
        "sélectionner / laisser vide), le nom du champ du modèle dans les steps de vérification",
        "Odoo. Les deux se lisent sur l'application réelle. Un champ dont le libellé affiché est",
        "« Raison de la demande » peut très bien s'appeler `name`.",
        "",
        "En revanche, un bouton, un onglet ou un produit se désigne bien par son libellé VISIBLE",
        "(`{label}`, `{name}`) : ces steps-là résolvent par le texte affiché, pas par un sélecteur.",
        "",
        "⚠️ **Quand un step porte une note « → … », LIS-LA** : son libellé seul ne suffit pas à",
        "deviner ce qu'il fait, et deux libellés voisins peuvent agir très différemment.",
        "",
        "⚠️ **Avant d'écrire un nouveau step, cite (dans ton `[Thought]`) le libellé exact de",
        "celui ou ceux du catalogue que tu comptes réutiliser** : ça oblige à le relire au lieu",
        "de deviner, et évite d'en réinventer un qui existe déjà sous un autre nom.",
        "",
    ]

    par_origine: dict[str, list[SharedStep]] = {}
    for step in steps:
        par_origine.setdefault(_origine(step), []).append(step)

    blocs = []
    for nom in sorted(par_origine, key=lambda n: (n != "generic", n)):
        section = _section_par_mot_cle(par_origine[nom])
        if not section:
            continue
        if nom == "generic":
            blocs.append(f"<steps_partages_generiques>\n\n{section}\n\n</steps_partages_generiques>")
        else:
            blocs.append(f'<steps_partages_connecteur nom="{nom}">\n\n{section}\n\n'
                         f"</steps_partages_connecteur>")

    return "\n".join(lines).rstrip() + "\n\n" + "\n\n".join(blocs)


# ── Script effectif consultable (Phase 2, audit DA 2026-08-13) ─────────────────────────────────
# Ce qu'un cas EXÉCUTE réellement dépasse presque toujours son `steps_content` propre : la
# plupart de ses steps viennent de la bibliothèque partagée, chargée par Behave mais invisible
# dans l'onglet Script. Les deux fonctions ci-dessous résolvent, PUREMENT à partir du texte du
# `.feature` et du catalogue, quels steps partagés sont réellement en jeu et ce qu'ils font —
# sans dépendre de la base ni d'un run réel.

_GHERKIN_MOTS_CLES = ("Soit", "Quand", "Alors", "Et", "Mais")
_LIGNE_GHERKIN = re.compile(r"^\s*(?:" + "|".join(_GHERKIN_MOTS_CLES) + r")\s+(.+?)\s*$")


def _lignes_gherkin(feature_content: str) -> list[str]:
    """Le texte de chaque step du `.feature`, keyword Gherkin (fr) retiré."""
    return [m.group(1) for ligne in feature_content.splitlines()
            if (m := _LIGNE_GHERKIN.match(ligne))]


def match_referenced(feature_content: str, catalogue: list[SharedStep]) -> list[SharedStep]:
    """Les steps du CATALOGUE que ce `.feature` référence réellement.

    Comparaison par motif (`parse.compile(label).parse(ligne)`), pas par égalité de texte : un
    même libellé de catalogue (`je renseigne le champ "{field}" avec la valeur "{value}"`)
    couvre toutes ses instanciations concrètes dans le `.feature`, jamais littéralement égales.

    Un step qui ne matche AUCUNE ligne n'est simplement pas dans le résultat — ce n'est pas une
    erreur, la plupart du catalogue n'est jamais utilisée par un cas donné.
    """
    if not feature_content or not catalogue:
        return []
    # Précompilé une seule fois par step de catalogue, pas par (ligne × step) : le catalogue
    # peut porter plus de cent entrées, le refaire à chaque ligne serait un travail jeté.
    parseurs = [(step, parse_lib.compile(step.label)) for step in catalogue]
    trouves: dict[tuple[str, str], SharedStep] = {}
    for ligne in _lignes_gherkin(feature_content):
        for step, parseur in parseurs:
            cle = (step.keyword, step.label)
            if cle in trouves:
                continue
            try:
                if parseur.parse(ligne) is not None:
                    trouves[cle] = step
            except (ValueError, IndexError):
                continue
    return sorted(trouves.values(), key=lambda s: (s.source, s.label))


def load_step_source(steps: list[SharedStep], directory: Path | None = None) -> dict[str, str]:
    """Code complet (décorateur + corps) de chaque step, RELU depuis son fichier source.

    Jamais reconstruit à partir du `SharedStep` (qui ne porte que keyword+label+note) : la
    fonction réelle sur disque est la seule source de vérité pour ce qu'un step FAIT.

    Clé : le libellé (unique dans un catalogue — `write_steps_file` l'impose déjà via
    `AmbiguousStep`, cf. décision 0003). Un step demandé mais introuvable sur disque (fichier
    source disparu entre la génération et la consultation) est simplement absent du résultat.
    """
    directory = directory or config.STEPS_LIBRARY_DIR
    par_fichier: dict[str, list[SharedStep]] = {}
    for step in steps:
        if step.source:
            par_fichier.setdefault(step.source, []).append(step)

    code: dict[str, str] = {}
    for source, groupe in par_fichier.items():
        try:
            texte = (directory / source).read_text(encoding="utf-8")
            tree = ast.parse(texte)
        except (OSError, SyntaxError):
            continue
        lignes = texte.splitlines(keepends=True)
        labels_attendus = {s.label for s in groupe}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not deco.args:
                    continue
                if _decorator_name(deco.func).lower() not in _DECORATORS:
                    continue
                arg = deco.args[0]
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    continue
                label = arg.value.strip()
                if label not in labels_attendus or label in code:
                    continue
                # Le décorateur précède `def` dans le fichier mais PAS dans `node.lineno`
                # (toujours la ligne du `def`, cf. doc `ast`) : sans ce recalcul, le code
                # "complet" perdrait le `@given(...)`/`@when(...)` qui dit ce qui déclenche le step.
                debut = min([d.lineno for d in node.decorator_list] + [node.lineno])
                code[label] = "".join(lignes[debut - 1:node.end_lineno])
    return code
