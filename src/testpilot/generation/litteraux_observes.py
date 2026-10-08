"""Littéraux observés : un test ne cite que ce qui a été vu sur l'application (lot VH-05, plan verdict honnête, T1/T4/T9).

Pourquoi. Les erreurs techniques après génération de la campagne `base-3` (2026-10-08) ont presque toutes la même forme :
l'agent cite un nom qui n'existe pas sur l'application — `username` au lieu de `identifiant`, « Quantite » sans accent, un
bouton visé par son texte alors que seul son nom accessible porte le libellé, un attribut `context.base_url` inventé, un appel
HTTP direct. L'annuaire de l'application (`data/domain/projet-<id>.json`, construit par l'exploration) contenait pourtant les
bons noms. Ce module confronte, sans LLM, chaque littéral d'un test à cet annuaire et rend la liste des écarts, avec la valeur
observée la plus proche.

Ce que le module NE fait PAS (dit, pas oublié) :
- il ne vérifie pas les TEXTES attendus des `Alors` (« la page affiche le texte … ») : l'annuaire ne relève pas les textes ;
- il ne sait pas sur quelle page on arrive après une action qui soumet : la route devient alors « inconnue » et le contrôle
  retombe sur « existe quelque part dans l'application » (plus faible, mais jamais un refus à tort) ;
- il ne juge pas un mot de passe : un test de connexion refusée a légitimement besoin d'une valeur fausse.

Module PUR : aucune I/O, aucun réseau, aucun LLM. Entrées = textes et dictionnaires, sortie = liste d'écarts.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

# Steps de la bibliothèque dont un paramètre DÉSIGNE un élément de l'application. Le reste des steps n'est pas contrôlé ici.
_ETAPE = re.compile(r'^\s*(?:Soit|Étant donné|Etant donné|Quand|Lorsque|Alors|Et|Mais)\s+(?P<texte>.+?)\s*$')
_CHAMP = [re.compile(r'^je renseigne le champ "(?P<champ>[^"]+)" avec la valeur "[^"]*"$'),
          re.compile(r'^je laisse le champ "(?P<champ>[^"]+)" vide$')]
_BOUTON = re.compile(r'^je clique sur le bouton "(?P<bouton>[^"]+)"$')
_PAGE = re.compile(r'^j\'ouvre la page "(?P<route>[^"]+)"$')
_CONNEXION = re.compile(r"^j'accède à la page de connexion sans me connecter$")
_ACCUEIL = re.compile(r"^j'accède à la page d'accueil de l'application$|^je me connecte ")

# Attributs que Behave pose lui-même sur `context`.
_CONTEXTE_BEHAVE = frozenset({"table", "text", "scenario", "feature", "config", "tags", "active_outline", "step",
                              "log_capture", "stdout_capture", "stderr_capture"})
# Lus par le code généré, ils exposeraient un secret ou le mécanisme du harnais : jamais autorisés.
_CONTEXTE_INTERDIT = frozenset({"web_password", "odoo_password", "totp_secret", "injected_session", "_runner"})

_SELECTEURS_TEXTE = re.compile(r":has-text\(|(?:^|[\s>])text=|xpath=")
_RESEAU_JS = re.compile(r"\bfetch\s*\(|XMLHttpRequest|sendBeacon")
_APPELS_LIBELLE = {"get_by_label", "get_by_placeholder", "get_by_text"}


@dataclass(frozen=True)
class Ecart:
    """Un littéral non observé. `observe` : la valeur observée la plus proche (à proposer à l'agent), si elle existe."""

    regle: str
    ou: str
    cite: str
    raison: str
    observe: str = ""


@dataclass
class Annuaire:
    """Ce que l'exploration a observé, par route : noms et libellés de champs, libellés de boutons, liens."""

    champs: dict[str, set[str]] = field(default_factory=dict)
    boutons: dict[str, set[str]] = field(default_factory=dict)
    liens: dict[str, dict[str, str]] = field(default_factory=dict)  # route -> {texte: href}
    page_connexion: str | None = None

    @property
    def routes(self) -> set[str]:
        return set(self.champs) | set(self.boutons)

    def tous(self, quoi: str) -> set[str]:
        source = self.champs if quoi == "champ" else self.boutons
        return set().union(*source.values()) if source else set()


def annuaire_depuis_modele(modele: dict) -> Annuaire:
    """`data/domain/projet-<id>.json` → `Annuaire`. Un champ se désigne par son nom technique OU son libellé (comme
    `fill_field`) ; un bouton par son libellé (nom accessible) ou, pour un lien, son texte."""
    annuaire = Annuaire()
    for route, page in (modele.get("pages") or {}).items():
        champs = annuaire.champs.setdefault(route, set())
        for champ in page.get("champs") or []:
            for cle in ("name", "label"):
                if champ.get(cle):
                    champs.add(str(champ[cle]).strip())
            if (champ.get("type") or "") == "password" and annuaire.page_connexion is None:
                annuaire.page_connexion = route
        boutons = annuaire.boutons.setdefault(route, set())
        for action in page.get("actions") or []:
            if action.get("label"):
                boutons.add(str(action["label"]).strip())
        liens = annuaire.liens.setdefault(route, {})
        for lien in page.get("liens") or []:
            if lien.get("text"):
                liens[str(lien["text"]).strip()] = str(lien.get("href") or "")
                boutons.add(str(lien["text"]).strip())  # `je clique sur le bouton` accepte aussi un lien (click_first_actionable)
    return annuaire


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn").casefold()


def _proche(cite: str, candidats: set[str]) -> str:
    """La valeur observée qui correspond à `cite` à l'accent ou à la casse près, sinon la plus proche ; « » si aucune."""
    cle = _sans_accents(cite)
    for candidat in sorted(candidats):
        if _sans_accents(candidat) == cle:
            return candidat
    proches = get_close_matches(cite, sorted(candidats), n=1, cutoff=0.6)
    return proches[0] if proches else ""


def _normaliser_route(route: str) -> str:
    return "/" + route.strip().lstrip("/").split("?")[0].split("#")[0].rstrip("/") if route.strip() else "/"


# ── Le .feature ───────────────────────────────────────────────────────────────────────────────────────────


def controler_feature(feature: str, annuaire: Annuaire) -> list[Ecart]:
    """Chaque champ, bouton ou page cité par un step de la bibliothèque doit exister, à l'identique, sur la route courante.

    La route courante suit le scénario : `j'ouvre la page` la fixe ; le clic sur un lien observé suit son `href` ; un clic sur
    un bouton (qui peut soumettre) ou l'accueil après connexion la rend inconnue. Route inconnue → le littéral doit exister
    quelque part dans l'application (contrôle plus faible, jamais un refus à tort)."""
    ecarts: list[Ecart] = []
    route: str | None = None
    for numero, ligne in enumerate(feature.splitlines(), start=1):
        if re.match(r"^\s*(Scénario|Scenario|Plan du scénario|Contexte)\b", ligne):
            route = None
            continue
        m = _ETAPE.match(ligne)
        if not m:
            continue
        texte, ou = m.group("texte"), f"ligne {numero}"
        if _CONNEXION.match(texte):
            route = annuaire.page_connexion
            continue
        if _ACCUEIL.match(texte):
            route = None
            continue
        page = _PAGE.match(texte)
        if page:
            cible = _normaliser_route(page.group("route"))
            if cible not in annuaire.routes and not any("{" in r or "<" in r for r in annuaire.routes):
                ecarts.append(Ecart("page", ou, page.group("route"), "page absente de l'annuaire de l'application",
                                    _proche(cible, annuaire.routes)))
                route = None
            else:
                route = cible if cible in annuaire.routes else None
            continue
        for motif in _CHAMP:
            champ = motif.match(texte)
            if champ:
                ecarts += _controler(champ.group("champ"), "champ", route, annuaire, ou)
        bouton = _BOUTON.match(texte)
        if bouton:
            libelle = bouton.group("bouton")
            ecarts += _controler(libelle, "bouton", route, annuaire, ou)
            href = (annuaire.liens.get(route) or {}).get(libelle) if route else None
            route = _normaliser_route(href) if href else None  # un bouton peut soumettre : page d'arrivée inconnue
    return ecarts


def _controler(cite: str, quoi: str, route: str | None, annuaire: Annuaire, ou: str) -> list[Ecart]:
    source = annuaire.champs if quoi == "champ" else annuaire.boutons
    if route is not None and cite in (source.get(route) or set()):
        return []
    if route is None and cite in annuaire.tous(quoi):
        return []
    sur_la_route = route is not None and cite in annuaire.tous(quoi)
    if sur_la_route:
        return [Ecart(quoi, ou, cite, f"« {cite} » existe dans l'application mais pas sur la page {route}",
                      _proche(cite, source.get(route) or set()))]
    candidats = (source.get(route) or set()) if route is not None else annuaire.tous(quoi)
    return [Ecart(quoi, ou, cite, f"{quoi} jamais observé{' sur la page ' + route if route else ''}",
                  _proche(cite, candidats) or _proche(cite, annuaire.tous(quoi)))]


# ── Le _steps.py ──────────────────────────────────────────────────────────────────────────────────────────


def attributs_de_contexte_poses(sources: list[str]) -> set[str]:
    """Les attributs `context.X` ÉCRITS par ces codes (affectation simple, multiple ou `setattr`) — calculés par AST."""
    poses: set[str] = set()
    for source in sources:
        try:
            arbre = ast.parse(source)
        except SyntaxError:
            continue
        for noeud in ast.walk(arbre):
            cibles = []
            if isinstance(noeud, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                cibles = noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
            for cible in cibles:
                for element in (cible.elts if isinstance(cible, ast.Tuple) else [cible]):
                    if isinstance(element, ast.Attribute) and getattr(element.value, "id", "") == "context":
                        poses.add(element.attr)
            if (isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "setattr" and len(noeud.args) >= 2
                    and getattr(noeud.args[0], "id", "") == "context" and isinstance(noeud.args[1], ast.Constant)):
                poses.add(str(noeud.args[1].value))
    return poses


def attributs_du_harnais(racine_behave_runtime: Path) -> set[str]:
    """Les attributs posés par `environment.py` et la bibliothèque partagée (lecture seule du dépôt, pas du code généré)."""
    sources = [p.read_text(encoding="utf-8") for p in Path(racine_behave_runtime).rglob("*.py")
               if "generated" not in p.parts]
    return attributs_de_contexte_poses(sources) | _CONTEXTE_BEHAVE


def controler_steps(code: str, annuaire: Annuaire, attributs_autorises: set[str]) -> list[Ecart]:
    """Le code Python généré : sélecteurs par texte libres, réseau direct, `context.X` inventé ou secret, libellés non observés."""
    try:
        arbre = ast.parse(code)
    except SyntaxError as erreur:
        return [Ecart("syntaxe", f"ligne {erreur.lineno}", "", "le fichier de steps ne se lit pas")]
    ecarts: list[Ecart] = []
    poses_ici = attributs_de_contexte_poses([code])
    libelles = annuaire.tous("champ") | annuaire.tous("bouton")
    for noeud in ast.walk(arbre):
        ou = f"ligne {getattr(noeud, 'lineno', '?')}"
        if isinstance(noeud, ast.Attribute):
            if noeud.attr == "request":
                ecarts.append(Ecart("reseau", ou, "request", "appel HTTP direct : la vérification serveur passe par l'oracle"))
            if isinstance(noeud.value, ast.Name) and noeud.value.id == "context" and isinstance(noeud.ctx, ast.Load):
                if noeud.attr in _CONTEXTE_INTERDIT:
                    ecarts.append(Ecart("contexte", ou, f"context.{noeud.attr}", "lecture d'un secret ou du harnais"))
                elif noeud.attr not in attributs_autorises and noeud.attr not in poses_ici:
                    ecarts.append(Ecart("contexte", ou, f"context.{noeud.attr}", "attribut jamais posé par le harnais ni par ce test",
                                        _proche(noeud.attr, attributs_autorises)))
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            if _SELECTEURS_TEXTE.search(noeud.value):
                ecarts.append(Ecart("selecteur", ou, noeud.value[:80],
                                    "sélecteur par texte libre : utiliser un step de la bibliothèque ou get_by_role + nom observé"))
            if _RESEAU_JS.search(noeud.value):
                ecarts.append(Ecart("reseau", ou, noeud.value[:80], "appel réseau dans du JavaScript injecté"))
        if isinstance(noeud, ast.JoinedStr) and any(isinstance(v, ast.Constant) and _SELECTEURS_TEXTE.search(str(v.value))
                                                    for v in noeud.values):
            ecarts.append(Ecart("selecteur", ou, "f-string", "sélecteur par texte libre dans une f-string"))
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute):
            nom = noeud.func.attr
            argument = noeud.args[0] if noeud.args else None
            if nom == "get_by_role":
                argument = next((k.value for k in noeud.keywords if k.arg == "name"), None)
            if nom in _APPELS_LIBELLE | {"get_by_role"} and argument is not None:
                ecarts += _libelle_observe(argument, libelles, ou, nom)
    return ecarts


def _libelle_observe(argument: ast.AST, libelles: set[str], ou: str, appel: str) -> list[Ecart]:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        cite = argument.value
        if cite in libelles:
            return []
        return [Ecart("libelle", ou, cite, f"{appel} : libellé jamais observé", _proche(cite, libelles))]
    if isinstance(argument, ast.JoinedStr):
        morceaux = [re.escape(v.value) if isinstance(v, ast.Constant) else ".+" for v in argument.values]
        motif = re.compile("^" + "".join(morceaux) + "$")
        if any(motif.match(libelle) for libelle in libelles):
            return []
        fixe = "".join(v.value for v in argument.values if isinstance(v, ast.Constant))
        return [Ecart("libelle", ou, "f-string " + fixe.strip(), f"{appel} : aucun libellé observé ne correspond",
                      _proche(fixe.strip(), {l[:len(fixe.strip())] for l in libelles}))]
    return []
