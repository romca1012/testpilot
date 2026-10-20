"""Gel des vérifications : une réparation ne touche JAMAIS à ce qu'un test vérifie (lot VH-03, V3).

Pourquoi. Audit du 2026-10-08 : le gel du `.feature` pendant une réparation n'existait que dans le prompt ; l'agent disposait de
`write_feature_file` et `write_steps_file`, et une réparation pouvait réécrire un `Alors`, une valeur attendue ou une table
d'Exemples — puis le test « réparé » passait. Un test qui cesse d'accuser l'application parce qu'on a changé ce qu'il vérifie,
c'est exactement un faux `conforme`.

Gel TOTAL des vérifications, sans exception d'« adressage » (revue du 2026-10-08) : changer un sélecteur, un `nth`, un `exact`,
un texte cherché ou une f-string de sélecteur dans une vérification change ce qu'elle prouve (vérifié : `tr:has-text('{montant}')`
→ `tr` faisait disparaître la valeur attendue du contrôle). Et depuis que le circuit (`repair_circuit.evaluate`) n'ouvre plus
JAMAIS la réparation sur un échec sous un `Alors`, une vérification n'a aucune raison d'être réparée automatiquement.

Ce qui est gelé :
- dans le `.feature` : pour chaque scénario existant et pour le `Contexte`, la suite de ses steps `Alors` (type `then`, `Et`/`Mais`
  compris) et ses tables d'Exemples ; un scénario existant ne disparaît ni ne change de nom (en ajouter un reste possible) ;
- dans le `_steps.py` :
  * chaque fonction décorée `@then`/`@step` (identifiée par son décorateur, pas par son nom — plusieurs `step_impl` coexistent),
    et chaque fonction du module qu'elle référence, transitivement (appel ou passage en valeur) ;
  * aucune NOUVELLE fonction `@then`/`@step` : une nouvelle définition placée avant l'ancienne l'emporterait dans Behave ;
  * les affectations de niveau module des noms qu'une fonction gelée lit (constantes, `helper = lambda …`) ;
  * les écritures `context.X = …` faites ailleurs (un `@when`) quand une fonction gelée lit `context.X`.

Correction automatique (D30, validée par le porteur le 2026-10-09) : même gel, sauf pour les vérifications CREUSES de la
version d'origine (paramètre `creuses` de `steps_modifies`) — les réécrire en vraies vérifications est le métier de la
correction. Ce qu'elle change d'autre n'est pas refusé à l'écriture : la version corrigée reste à relire (point de vigilance
`verification_affaiblie_par_correction`, `generation_service.lint_warnings_for_version`).

Module PUR : aucune I/O, aucun LLM ; parsing Gherkin par Behave (déjà la référence de `write_feature_file`).
"""

from __future__ import annotations

import ast
import re
import unicodedata
from collections import Counter
from collections.abc import Callable

_DECORATEURS_DE_VERIFICATION = frozenset({"then", "step", "Then", "Step"})


# ── .feature ──────────────────────────────────────────────────────────────────────────────────────────────


def _alors_et_exemples(feature: str) -> dict[str, tuple] | None:
    from behave.parser import ParserError, parse_feature

    try:
        parsed = parse_feature(feature, language="fr")
    except ParserError:
        return None
    if parsed is None:
        return {}
    gel: dict[str, tuple] = {}
    if parsed.background is not None:
        gel["__contexte__"] = (tuple(s.name for s in parsed.background.steps if s.step_type == "then"), ())
    for scenario in parsed.walk_scenarios(with_outlines=True):
        alors = tuple(step.name for step in scenario.steps if step.step_type == "then")
        exemples = tuple(tuple(tuple(ligne.cells) for ligne in (ex.table.rows if ex.table else []))
                         for ex in getattr(scenario, "examples", []) or [])
        gel[scenario.name] = (alors, exemples)
    return gel


def feature_modifiee(reference: str, proposition: str) -> list[str]:
    """Ce que `proposition` change à ce que `reference` VÉRIFIE (liste vide si rien)."""
    avant, apres = _alors_et_exemples(reference), _alors_et_exemples(proposition)
    if avant is None or apres is None:
        return []  # un Gherkin illisible est refusé ailleurs (`write_feature_file`)
    ecarts = []
    for nom, (alors, exemples) in avant.items():
        etiquette = "du Contexte" if nom == "__contexte__" else f"du scénario « {nom} »"
        if nom not in apres:
            ecarts.append(f"le scénario « {nom} » a disparu ou changé de nom" if nom != "__contexte__"
                          else "le Contexte a disparu")
            continue
        alors_apres, exemples_apres = apres[nom]
        if alors_apres != alors:
            ecarts.append(f"les vérifications « Alors » {etiquette} ont changé")
        if exemples_apres != exemples:
            ecarts.append(f"les Exemples {etiquette} ont changé")
    return ecarts


_LITTERAL = re.compile(r'"([^"]*)"')


def _contenu_d_etape(step) -> tuple:
    """Tout ce qu'une étape porte : mot-clé, texte, texte joint, tableau (en-têtes et cellules)."""
    table = (tuple(step.table.headings), tuple(tuple(r.cells) for r in step.table.rows)) if step.table else ()
    return (step.step_type, step.name, step.text or "", table)


def _scenarios(feature: str) -> dict[str, tuple] | None:
    """Par scénario (Contexte compris, Plans et scénarios dépliés) : ses étapes complètes et ses tableaux d'Exemples."""
    from behave.parser import ParserError, parse_feature

    try:
        parsed = parse_feature(feature, language="fr")
    except ParserError:
        return None
    if parsed is None:
        return {}
    gel: dict[str, tuple] = {}
    if parsed.background is not None:
        gel["__contexte__"] = (tuple(parsed.background.steps), ())
    for scenario in parsed.walk_scenarios(with_outlines=True):
        exemples = tuple((tuple(ex.table.headings), tuple(tuple(r.cells) for r in ex.table.rows))
                         for ex in getattr(scenario, "examples", []) or [] if ex.table)
        gel[scenario.name] = (tuple(scenario.steps), exemples)
    return gel


def _ecarts_par_scenario(reference: str, proposition: str, comparer) -> list[str]:
    avant, apres = _scenarios(reference), _scenarios(proposition)
    if avant is None or apres is None:
        return []  # un Gherkin illisible est refusé ailleurs (`write_feature_file`)
    ecarts = []
    for nom, contenu in avant.items():
        etiquette = "du Contexte" if nom == "__contexte__" else f"du scénario « {nom} »"
        if nom not in apres:
            ecarts.append(f"le scénario « {nom} » a disparu ou changé de nom" if nom != "__contexte__"
                          else "le Contexte a disparu")
            continue
        ecarts += [f"{ecart} {etiquette}" for ecart in comparer(contenu, apres[nom])]
    for nom in apres:
        if nom not in avant:
            ecarts.append("le Contexte a été ajouté" if nom == "__contexte__" else f"nouveau scénario « {nom} »")
    return ecarts


def scenario_modifie(reference: str, proposition: str) -> list[str]:
    """Ce que `proposition` change à `reference`, étape par étape — pas seulement les « Alors ». Après un défaut
    FONCTIONNEL, changer une donnée d'un « Quand » (17 → 16 ans, mesuré en quatrième passe de revue) change ce que le test
    prouve autant que changer un « Alors » (A65)."""
    def comparer(avant, apres):
        (etapes, exemples), (etapes_apres, exemples_apres) = avant, apres
        ecarts = []
        if [_contenu_d_etape(e) for e in etapes] != [_contenu_d_etape(e) for e in etapes_apres]:
            ecarts.append("les étapes")
        if exemples != exemples_apres:
            ecarts.append("les Exemples")
        return [f"{quoi} ont changé" for quoi in ecarts]
    return _ecarts_par_scenario(reference, proposition, comparer)


def _cite(valeur: str, metier: str) -> bool:
    """La valeur figure dans le métier, ou elle porte un chiffre alors que le métier en porte un aussi. Fail-closed
    (cinquième passe de revue) : « 1 000 € » ou « 31/01/2026 » dans le cas ne ressemblent pas, en texte, aux littéraux
    « 1000 » ou « 2026-01-31 » — une borne écrite autrement échappait à la garde. Un nombre ou une date ne change donc sans
    avis que si le cas n'en cite aucun."""
    def plier(texte: str) -> str:   # « Prémium » et « Premium » : la même valeur
        return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)).casefold()

    valeur = valeur.strip()
    if not valeur:
        return False
    if plier(valeur) in plier(metier):
        return True
    return any(c.isdigit() for c in valeur) and any(c.isdigit() for c in metier)


def donnee_seule_modifiee(reference: str, proposition: str, metier: str) -> list[str]:
    """Décision A66 (porteur, 2026-10-20) : après une « donnée refusée », changer la DONNÉE saisie est la réparation
    attendue. Est une donnée : un littéral entre guillemets d'une étape qui n'est pas un « Alors », ou une cellule d'une
    colonne d'Exemples qu'aucun « Alors » ne cite (`<colonne>` dans son texte, son texte joint ou son tableau).

    Tout le reste est un écart, comme `scenario_modifie` : un « Alors » (texte, texte joint, tableau), la forme d'une
    étape, une colonne citée. Et une donnée dont l'ANCIENNE valeur figure dans le métier validé par une personne (`metier` :
    étapes, résultat attendu, préconditions) n'est pas « seulement une donnée » — le cas l'impose (quatrième passe : une
    application qui pose à tort `min="19"` refuse le 18 que le cas exige ; passer à 19 masquerait le défaut).

    Double protection, mesurée par mutation : les scénarios dépliés d'un Plan (« … -- @1.1 ») portent dans leurs « Alors »
    (texte, texte joint, tableau) la valeur de chaque ligne — eux voient déjà une colonne citée qui change ; la
    recherche des colonnes citées tient même si Behave cessait de les rendre."""
    def citees(etapes) -> set[str]:
        textes = " ".join(" ".join([e.name, e.text or ""] + (list(e.table.headings) + [c for r in e.table.rows
                                                                                       for c in r.cells]
                                                             if e.table else []))
                          for e in etapes if e.step_type == "then")
        return {m.group(1) for m in re.finditer(r"<([^<>]+)>", textes)}

    def comparer(avant, apres):
        (etapes, exemples), (etapes_apres, exemples_apres) = avant, apres
        ecarts = []
        if len(etapes) != len(etapes_apres):
            return ["les étapes ont changé"]
        for e, f in zip(etapes, etapes_apres):
            if e.step_type == "then" or f.step_type == "then" or e.text or f.text or e.table or f.table:
                if _contenu_d_etape(e) != _contenu_d_etape(f):
                    ecarts.append("une vérification ou une étape à tableau a changé")
                continue
            if (e.step_type, _LITTERAL.sub('""', e.name)) != (f.step_type, _LITTERAL.sub('""', f.name)):
                ecarts.append("la forme d'une étape a changé")
                continue
            litteraux, litteraux_apres = _LITTERAL.findall(e.name), _LITTERAL.findall(f.name)
            # Seule la DERNIÈRE valeur d'une étape est une donnée (`… le champ "age" avec la valeur "18"`) : le nom du champ
            # ou du bouton qui change, c'est une autre étape (cinquième passe de revue).
            # Une étape à un seul littéral (`j'ouvre la page "/acces"`, un clic) n'a pas de donnée : changer sa cible, c'est
            # contourner l'écran fautif (sixième passe de revue).
            if litteraux[:-1] != litteraux_apres[:-1] or (len(litteraux) < 2 and litteraux != litteraux_apres):
                ecarts.append("la cible d'une étape a changé")
            elif litteraux and litteraux[-1] != litteraux_apres[-1] and _cite(litteraux[-1], metier):
                ecarts.append(f"la donnée « {litteraux[-1]} », que le cas cite, a changé")
        colonnes_citees = citees(etapes) | citees(etapes_apres)
        if [ex[0] for ex in exemples] != [ex[0] for ex in exemples_apres]:
            ecarts.append("les colonnes des Exemples ont changé")
            return ecarts
        for (entetes, lignes), (_, lignes_apres) in zip(exemples, exemples_apres):
            if len(lignes) != len(lignes_apres):
                ecarts.append("le nombre de lignes des Exemples a changé")
                continue
            for ligne, ligne_apres in zip(lignes, lignes_apres):
                for entete, ancienne, nouvelle in zip(entetes, ligne, ligne_apres):
                    if ancienne == nouvelle:
                        continue
                    if entete in colonnes_citees:
                        ecarts.append(f"le résultat attendu « {entete} » des Exemples a changé")
                    elif _cite(ancienne, metier):
                        ecarts.append(f"la donnée « {ancienne} », que le cas cite, a changé")
        return ecarts
    return _ecarts_par_scenario(reference, proposition, comparer)


# ── _steps.py ─────────────────────────────────────────────────────────────────────────────────────────────


def _nom_du_decorateur(deco: ast.AST) -> str:
    cible = deco.func if isinstance(deco, ast.Call) else deco
    return getattr(cible, "id", getattr(cible, "attr", ""))


def _est_verification(f: ast.AST) -> bool:
    return any(_nom_du_decorateur(d) in _DECORATEURS_DE_VERIFICATION for d in f.decorator_list)


def _cle_de_decorateurs(f: ast.AST) -> tuple[str, ...]:
    return tuple(ast.unparse(d) for d in f.decorator_list)


def _signature(noeud: ast.AST) -> str:
    """Empreinte d'une fonction ou d'une instruction, sans la docstring (qui ne vérifie rien)."""
    copie = ast.parse(ast.unparse(noeud)).body[0]
    corps = getattr(copie, "body", None)
    if (isinstance(corps, list) and corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant)
            and isinstance(corps[0].value.value, str)):
        copie.body = corps[1:] or [ast.Pass()]
    return ast.dump(copie, annotate_fields=False)


class _Module:
    """Le fichier de steps vu par le gel : fonctions de vérification, liaisons de module, écritures de `context.X`.

    `exclues` : `id` des fonctions de vérification à NE PAS geler (D30 — une vérification creuse que la correction a le
    droit de réécrire) ; elles ne comptent ni comme vérifications ni comme racines des noms et attributs gelés."""

    def __init__(self, arbre: ast.Module, exclues: set[int] | frozenset[int] = frozenset()):
        self.verifications: dict[tuple[str, ...], list[ast.AST]] = {}
        self.liaisons: dict[str, list[ast.AST]] = {}  # nom de module -> instructions qui le lient (def, affectation)
        for n in arbre.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.liaisons.setdefault(n.name, []).append(n)
                if _est_verification(n) and id(n) not in exclues:
                    self.verifications.setdefault(_cle_de_decorateurs(n), []).append(n)
            elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
                for c in cibles:
                    for nom in (e.id for e in ast.walk(c) if isinstance(e, ast.Name)):
                        self.liaisons.setdefault(nom, []).append(n)
        self.fonctions = [n for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def gelees(self) -> tuple[set[str], set[str]]:
        """(noms de module gelés, attributs `context.X` lus par une vérification) — fermeture transitive."""
        a_voir = [f for fs in self.verifications.values() for f in fs]
        noms: set[str] = set()
        attributs: set[str] = set()
        vus: set[int] = set()
        while a_voir:
            noeud = a_voir.pop()
            if id(noeud) in vus:
                continue
            vus.add(id(noeud))
            for n in ast.walk(noeud):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in self.liaisons and n.id not in noms:
                    noms.add(n.id)
                    a_voir.extend(self.liaisons[n.id])
                if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "context"
                        and isinstance(n.ctx, ast.Load)):
                    attributs.add(n.attr)
        return noms, attributs

    def ecritures_de_contexte(self, attributs: set[str], cles_gelees) -> Counter:
        """Empreintes des instructions qui ÉCRIVENT `context.X` (X lu par une vérification), hors fonctions de vérification
        GELÉES (`cles_gelees` : leurs clés de décorateurs, prises sur la RÉFÉRENCE, déjà comparées en entier).

        Revue D30-D32 (B2) : les clés viennent de la référence pour les DEUX côtés. Avant, la proposition excluait toutes ses
        vérifications, creuses comprises : une écriture ajoutée dans une fonction creuse réécrite (un `@step` d'action) à un
        attribut lu par une vérification réelle échappait au gel."""
        empreintes: Counter = Counter()
        for f in self.fonctions:
            if _est_verification(f) and _cle_de_decorateurs(f) in cles_gelees:
                continue
            for n in ast.walk(f):
                cibles = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(
                    n, (ast.AugAssign, ast.AnnAssign)) else []
                ecrit = any(isinstance(c, ast.Attribute) and getattr(c.value, "id", "") == "context" and c.attr in attributs
                            for t in cibles for c in ast.walk(t))
                if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "setattr" and len(n.args) >= 2
                        and getattr(n.args[0], "id", "") == "context" and isinstance(n.args[1], ast.Constant)
                        and n.args[1].value in attributs):
                    ecrit = True
                if ecrit:
                    empreintes[_signature(n) if not isinstance(n, ast.Call) else ast.dump(n)] += 1
        return empreintes


def steps_modifies(reference: str, proposition: str, *,
                   creuses: Callable[[ast.Module], set[int]] | None = None) -> list[str]:
    """Ce que `proposition` change aux vérifications de `reference` (liste vide si rien).

    `creuses` (D30, correction automatique) : rend les `id` des vérifications de `reference` qui ne prouvent rien ; celles-là
    peuvent être réécrites librement — c'est le métier de la correction. Tout le reste est gelé comme en réparation,
    y compris l'ajout d'une NOUVELLE vérification (elle pourrait l'emporter sur une vérification réelle dans Behave)."""
    try:
        arbre_avant = ast.parse(reference)
        avant = _Module(arbre_avant, creuses(arbre_avant) if creuses else frozenset())
        toutes_avant = _Module(arbre_avant).verifications if creuses else avant.verifications
        apres = _Module(ast.parse(proposition))
    except SyntaxError:
        return []  # refusé ailleurs (`write_steps_file`)
    ecarts = []
    for cle, fonctions in avant.verifications.items():
        decorateur = cle[0] if cle else "?"
        if cle not in apres.verifications:
            ecarts.append(f"la vérification `{decorateur}` a disparu ou changé de libellé")
        elif [_signature(f) for f in apres.verifications[cle]] != [_signature(f) for f in fonctions]:
            ecarts.append(f"la vérification `{decorateur}` a changé")
    for cle in apres.verifications:
        if cle not in toutes_avant:
            ecarts.append(f"nouvelle vérification `{cle[0] if cle else '?'}` : une réparation n'ajoute pas de step « Alors »")
    noms, attributs = avant.gelees()
    for nom in sorted(noms):
        if [_signature(n) for n in apres.liaisons.get(nom, [])] != [_signature(n) for n in avant.liaisons.get(nom, [])]:
            ecarts.append(f"`{nom}`, lu par une vérification, a changé")
    cles_gelees = set(avant.verifications)
    if apres.ecritures_de_contexte(attributs, cles_gelees) != avant.ecritures_de_contexte(attributs, cles_gelees):
        ecarts.append("une valeur que lit une vérification (`context." + "`, `context.".join(sorted(attributs))
                      + "`) est écrite autrement")
    return ecarts
