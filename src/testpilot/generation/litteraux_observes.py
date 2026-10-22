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

Aucun réseau, aucun LLM. Les contrôles sont purs (textes et dictionnaires → liste d'écarts) ; seule `attributs_du_harnais`
lit le dépôt (sources de `behave_runtime/`), jamais le code généré ni l'application.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

from testpilot.generation.gherkin_mots_cles import DEBUT_CONTEXTE, DEBUT_REGLE, DEBUT_SCENARIO

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
# Lot VH-06 (banc base-5, `commande_persistance_serveur`, 3 essais sur 3) : interrogé À LA MAIN, l'oracle a donné un faux rouge
# (numéro comparé à un texte mal lu) et deux erreurs du test (objet compté, `context.oracle(...)` appelé comme une fonction).
# Les steps du catalogue lisent l'oracle, classent ses erreurs et marquent le constat `source: oracle` ; du code libre ne fait
# rien de tout cela. Même doctrine que le transport (décision 0003) : l'accès au serveur n'est pas réécrit par un test.
_CONTEXTE_ORACLE = frozenset({"oracle", "oracle_erreur"})
_RAISON_ORACLE = ("l'oracle ne s'interroge pas à la main : utiliser « le champ \"<chemin>\" de l'oracle \"<requête>\" vaut "
                  "\"<valeur>\" », « … compte <n> élément(s) », « la liste \"<chemin>\" de l'oracle \"<requête>\" contient un "
                  "élément dont \"<clé>\" est \"<valeur>\" » — ou « … est la valeur affichée pour \"<libellé>\" » pour y "
                  "retrouver ce que l'écran montre")

_SELECTEURS_TEXTE = re.compile(r":has-text\(|(?:^|[\s>])text=|xpath=")
_RESEAU_JS = re.compile(r"\bfetch\s*\(|XMLHttpRequest|sendBeacon")
# Seuls les appels qui désignent un élément INTERACTIF sont confrontés à l'annuaire (qui relève champs, boutons et liens, pas
# les textes ni les titres) : `get_by_text` et `get_by_role("heading", …)` ne sont pas contrôlés ici (revue VH-02).
_APPELS_LIBELLE = {"get_by_label", "get_by_placeholder"}
_ROLES_INTERACTIFS = frozenset({"button", "link", "textbox", "searchbox", "spinbutton", "combobox", "checkbox", "radio",
                                "listbox", "option", "switch", "menuitem", "tab"})
_RECEPTEUR_NAVIGATEUR = re.compile(r"(^|\.)(page|context|browser|browser_context)$")


@dataclass(frozen=True)
class Ecart:
    """Un littéral non observé. `observe` : la valeur observée la plus proche (à proposer à l'agent), si elle existe."""

    regle: str
    ou: str
    cite: str
    raison: str
    observe: str = ""
    # `False` : indication seulement (ex. page absente de l'annuaire — une page dynamique, `/commande/<numéro>`, peut ne jamais
    # avoir été explorée) ; jamais un refus d'écriture.
    bloquant: bool = True


@dataclass
class Annuaire:
    """Ce que l'exploration a observé, par route : noms et libellés de champs, libellés de boutons, liens."""

    champs: dict[str, set[str]] = field(default_factory=dict)
    boutons: dict[str, set[str]] = field(default_factory=dict)
    liens: dict[str, dict[str, str]] = field(default_factory=dict)  # route -> {texte: href}
    page_connexion: str | None = None
    # Étape 5 (AV-6) : noms et libellés des champs de mot de passe, pour la garde de connexion (`garde_connexion`).
    champs_mot_de_passe: set[str] = field(default_factory=set)
    # Noms et libellés vus par les outils d'inspection PENDANT la génération : plus frais que l'exploration ; acceptés partout.
    observes_session: set[str] = field(default_factory=set)

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
            if (champ.get("type") or "") == "password":
                annuaire.champs_mot_de_passe.update(str(champ[c]).strip() for c in ("name", "label") if champ.get(c))
                if annuaire.page_connexion is None:
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


def controler_feature(feature: str, annuaire: Annuaire, *, page_d_arrivee_observee: bool = False) -> list[Ecart]:
    """Chaque champ, bouton ou page cité par un step de la bibliothèque doit exister, à l'identique, sur la route courante.

    La route courante suit le scénario : `j'ouvre la page` la fixe ; le clic sur un lien observé suit son `href` ; un clic sur
    un bouton (qui peut soumettre) ou l'accueil après connexion la rend inconnue. Route inconnue → le littéral doit exister
    quelque part dans l'application (contrôle plus faible, jamais un refus à tort).

    `page_d_arrivee_observee` (étape 5, interrupteur `TESTPILOT_PAGE_D_ARRIVEE_OBSERVEE`, éteint) : la page atteinte APRÈS UN
    CLIC qui n'a pas suivi un lien observé n'est plus jugée sur « existe quelque part » — le littéral doit avoir été observé
    pendant la génération (essai, inspection : `observes_session`). Un champ « Quantité » vu sur une autre page ne prouve pas
    qu'il existe sur la page de confirmation. Le début d'un scénario et l'accueil gardent le contrôle d'avant."""
    ecarts: list[Ecart] = []
    route: str | None = None
    apres_clic = ""   # le bouton cliqué qui a rendu la route inconnue (vide : route connue, ou inconnue sans clic)
    depart: str | None = None   # la route connue AVANT ce clic : un formulaire qui reste affiché garde ses champs
    for numero, ligne in enumerate(feature.splitlines(), start=1):
        if DEBUT_SCENARIO.match(ligne) or DEBUT_CONTEXTE.match(ligne) or DEBUT_REGLE.match(ligne):   # étape 2 : `Exemple:`
            route, apres_clic, depart = None, "", None
            continue
        m = _ETAPE.match(ligne)
        if not m:
            continue
        texte, ou = m.group("texte"), f"ligne {numero}"
        if _CONNEXION.match(texte):
            route, apres_clic = annuaire.page_connexion, ""
            continue
        if _ACCUEIL.match(texte):
            route, apres_clic = None, ""
            continue
        page = _PAGE.match(texte)
        if page:
            cible = _normaliser_route(page.group("route"))
            if cible not in annuaire.routes and not any("{" in r or "<" in r for r in annuaire.routes):
                ecarts.append(Ecart("page", ou, page.group("route"), "page absente de l'annuaire de l'application",
                                    _proche(cible, annuaire.routes), bloquant=False))
                route = None
            else:
                route = cible if cible in annuaire.routes else None
            apres_clic = ""
            continue
        for motif in _CHAMP:
            champ = motif.match(texte)
            if champ:
                ecarts += _controler_ici(champ.group("champ"), "champ", route, annuaire, ou,
                                         apres_clic if page_d_arrivee_observee else "", depart)
        bouton = _BOUTON.match(texte)
        if bouton:
            libelle = bouton.group("bouton")
            ecarts += _controler_ici(libelle, "bouton", route, annuaire, ou, apres_clic if page_d_arrivee_observee else "",
                                     depart)
            href = (annuaire.liens.get(route) or {}).get(libelle) if route else None
            if not href and route is not None:
                depart = route
            route = _normaliser_route(href) if href else None  # un bouton peut soumettre : page d'arrivée inconnue
            apres_clic = "" if href else libelle
            if href:
                depart = None
    return ecarts


def _controler_ici(cite: str, quoi: str, route: str | None, annuaire: Annuaire, ou: str, apres_clic: str,
                   depart: str | None = None) -> list[Ecart]:
    """`_controler`, plus la règle de la page d'arrivée (`apres_clic` non vide : la route est inconnue parce qu'un clic a pu
    soumettre). Le littéral doit alors avoir été OBSERVÉ pendant la génération, ou figurer sur la page de DÉPART (revue du
    2026-10-22 : un formulaire refusé reste affiché avec ses champs) — exister ailleurs dans l'application ne prouve rien
    sur la page atteinte."""
    source = annuaire.champs if quoi == "champ" else annuaire.boutons
    if (not apres_clic or route is not None or ("<" in cite and ">" in cite) or cite in annuaire.observes_session
            or (depart is not None and cite in (source.get(depart) or set()))):
        return _controler(cite, quoi, route, annuaire, ou)
    return [Ecart("page_inconnue", ou, cite,
                  f"la page atteinte après « {apres_clic} » n'a jamais été observée : rien ne prouve que le {quoi} "
                  f"« {cite} » y figure — essaie l'action ou inspecte la page atteinte avant de le citer",
                  _proche(cite, annuaire.observes_session))]


def _controler(cite: str, quoi: str, route: str | None, annuaire: Annuaire, ou: str) -> list[Ecart]:
    if "<" in cite and ">" in cite:  # paramètre d'un Plan du scénario : la valeur vient des Exemples
        return []
    if cite in annuaire.observes_session:
        return []
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
    return set(_attributs_du_harnais(str(Path(racine_behave_runtime).resolve())))


@lru_cache(maxsize=4)
def _attributs_du_harnais(racine: str) -> frozenset[str]:
    base = Path(racine)
    # `relative_to` : un déploiement sous un dossier nommé `generated` ne doit pas exclure tout le harnais (revue 2026-10-08).
    sources = [p.read_text(encoding="utf-8") for p in base.rglob("*.py") if "generated" not in p.relative_to(base).parts]
    return frozenset(attributs_de_contexte_poses(sources) | _CONTEXTE_BEHAVE)


def brancher_controles(ctx, connector_type: str | None, modele: dict | None, racine_behave_runtime: Path) -> None:
    """Arme les contrôles des littéraux sur un `ToolContext` — appelé par la génération, la correction ET la réparation (revue
    du 2026-10-08 : les deux dernières écrivaient sans ces contrôles). Annuaire : connecteur web seulement (l'annuaire d'un
    projet Odoo ne relève pas le back-office)."""
    ctx.attributs_contexte = frozenset(attributs_du_harnais(racine_behave_runtime))
    if connector_type == "web" and (modele or {}).get("pages"):
        ctx.annuaire = annuaire_depuis_modele(modele)


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
            if noeud.attr == "request" and _RECEPTEUR_NAVIGATEUR.search(ast.unparse(noeud.value)):
                # `page.request` / `context.request` émettent une requête ; `response.request` (observation) reste permis.
                ecarts.append(Ecart("reseau", ou, "request", "appel HTTP direct : la vérification serveur passe par l'oracle"))
            # Quel que soit le RÉCEPTEUR : `ctx = context; ctx.oracle`, `lambda c: c.oracle`, un paramètre renommé d'une
            # fonction d'aide passaient une garde qui ne regardait que le nom `context` (revue du lot VH-06, reproduit).
            if noeud.attr in _CONTEXTE_ORACLE:
                ecarts.append(Ecart("reseau", ou, f"context.{noeud.attr}", _RAISON_ORACLE))
            elif isinstance(noeud.value, ast.Name) and noeud.value.id == "context" and isinstance(noeud.ctx, ast.Load):
                if noeud.attr in _CONTEXTE_INTERDIT:
                    ecarts.append(Ecart("contexte", ou, f"context.{noeud.attr}", "lecture d'un secret ou du harnais"))
                elif noeud.attr not in attributs_autorises and noeud.attr not in poses_ici:
                    ecarts.append(Ecart("contexte", ou, f"context.{noeud.attr}", "attribut jamais posé par le harnais ni par ce test",
                                        _proche(noeud.attr, attributs_autorises)))
        if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "getattr"
                and len(noeud.args) >= 2 and getattr(noeud.args[0], "id", "") == "context"
                and isinstance(noeud.args[1], ast.Constant)):
            attr = str(noeud.args[1].value)
            if attr in _CONTEXTE_INTERDIT:
                ecarts.append(Ecart("contexte", ou, f"context.{attr}", "lecture d'un secret ou du harnais"))
            elif attr in _CONTEXTE_ORACLE:
                ecarts.append(Ecart("reseau", ou, f"context.{attr}", _RAISON_ORACLE))
            elif attr not in attributs_autorises and attr not in poses_ici and len(noeud.args) < 3:
                ecarts.append(Ecart("contexte", ou, f"context.{attr}", "attribut jamais posé par le harnais ni par ce test",
                                    _proche(attr, attributs_autorises)))
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
                role = noeud.args[0].value if noeud.args and isinstance(noeud.args[0], ast.Constant) else None
                argument = (next((k.value for k in noeud.keywords if k.arg == "name"), None)
                            if role in _ROLES_INTERACTIFS else None)
            if nom in _APPELS_LIBELLE | {"get_by_role"} and argument is not None:
                ecarts += _libelle_observe(argument, libelles | annuaire.observes_session, ou, nom)
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
