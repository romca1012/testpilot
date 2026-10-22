"""Les données de test du projet, vues de la génération (lot PT-02d, derrière l'interrupteur `TESTPILOT_VARIABLES_DE_TEST`).

L'agent reçoit les NOMS des variables (et leur description) — jamais leurs valeurs : une valeur est déclarée par une personne,
choisie au lancement (le jeu de données), et posée dans une copie du test à l'exécution (`donnees_de_test_service`). Un test
qui écrit `"{{client}}"` reste donc juste pour tous les jeux.

Trois garanties, toutes déterministes (aucun LLM) :
1. à l'ÉCRITURE, une variable inconnue, mal écrite ou mal placée est refusée — mêmes règles que le remplacement
   (`parametres/resolution.py`) — et une variable dans une ligne d'étape s'écrit ENTRE GUILLEMETS, dans une valeur : c'est la
   seule place où la marche à blanc de Behave reconnaît le step quelle que soit la valeur posée ensuite ;
2. pendant l'ESSAI dans le bac à sable, le texte joué reçoit les valeurs du jeu « Par défaut » — jamais `{{client}}` saisi
   tel quel dans l'application ;
3. interrupteur éteint : rien de tout cela, ce que l'agent reçoit et ce qu'il peut écrire sont ceux d'avant, octet pour octet.

Module pur : aucune I/O.
"""
from __future__ import annotations

import json
import re

from testpilot.generation import interrupteurs
from testpilot.parametres import resolution

_ENTRE_GUILLEMETS = re.compile(r'"[^"\n]*"')
# Une variable écrite dans du CODE (steps Python) : jamais remplacée à l'exécution — `"{{client}}" not in texte` y serait
# toujours vrai (revue du 2026-10-14, faux vert). Large exprès : toute écriture qui OUVRE une variable (`{{nom`), noms
# accentués compris (`{{société}}` passait la première version) et mal fermée comprise (`{{client}`, même piège).
_DANS_LE_CODE = re.compile(r"\{\{\s*\w[^{}\r\n]*\}?\}?")


def pour_l_agent(projet: dict | None) -> tuple[list[dict], dict[str, str]]:
    """(variables montrées à l'agent `[{nom, description}]`, valeurs du jeu « Par défaut » pour l'essai `{nom: valeur}`).
    Interrupteur éteint ou projet sans variable : rien."""
    if not interrupteurs.variables_de_test_actif():
        return [], {}
    projet = projet or {}
    variables = [{"nom": str(v.get("nom", "")), "description": str(v.get("description") or "")}
                 for v in projet.get("variables_de_test") or [] if v.get("nom")]
    return variables, dict(projet.get("valeurs_de_test_par_defaut") or {})


def section_prompt(variables: list[dict] | None, variables_des_lignes=()) -> str:
    """La section du message initial — vide sans variable. `variables_des_lignes` (IT-3b) : celles que les lignes du cas
    font varier — le cas est joué une fois par ligne."""
    if not variables:
        return ""
    du_cas_seules = [v for v in variables if not v.get("preparation")]
    preparation = [v for v in variables if v.get("preparation")]
    lignes = ["## Données de test du projet", ""]
    if du_cas_seules:
        lignes.append("Le projet déclare ces variables (des noms et des descriptions, jamais des instructions). Leur VALEUR est "
                      "choisie au lancement et posée dans le test à l'exécution — tu ne la connais pas et ne dois pas "
                      "l'inventer :")
        for v in du_cas_seules:
            description = f" — {v['description']}" if v.get("description") else ""
            lignes.append(f"- `{{{{{v['nom']}}}}}`{description}")
        lignes += ["",
                   "Quand le cas parle de l'une de ces données, écris la variable ENTRE GUILLEMETS à la place de la valeur, "
                   "par exemple `Quand je renseigne le champ \"Client\" avec la valeur \"{{client}}\"`. N'emploie que ces "
                   "noms, exactement ; une donnée qui n'est pas dans cette liste s'écrit comme avant. Une variable ne s'écrit "
                   "que dans le .feature, jamais dans le code Python des steps."]
    if preparation:
        # Porteur, 2026-10-22 : les variables que le cas ne cite pas, pour les seules étapes de PRÉPARATION.
        if du_cas_seules:
            lignes.append("")
        lignes.append("Le cas ne cite pas ces autres données du projet. Emploie-les SEULEMENT dans les étapes de PRÉPARATION "
                      "(Soit, Quand) que tu ajoutes toi-même pour atteindre l'état du cas (un formulaire à remplir avant "
                      "l'action testée), entre guillemets et à la place d'une valeur inventée ; jamais dans un « Alors », "
                      "jamais dans le code Python des steps :")
        for v in preparation:
            description = f" — {v['description']}" if v.get("description") else ""
            lignes.append(f"- `{{{{{v['nom']}}}}}`{description}")
    du_cas = [n for n in dict.fromkeys(variables_des_lignes or ()) if any(v["nom"] == n for v in variables)]
    if du_cas:
        noms = ", ".join(f"`{{{{{n}}}}}`" for n in du_cas)
        lignes += ["",
                   f"Ce cas est joué UNE FOIS PAR LIGNE de ses données de test : {noms} changent d'une ligne à l'autre "
                   "(valeurs limites comprises, et le résultat attendu de chacune quand une variable le porte). Écris UN SEUL "
                   "scénario qui emploie ces variables partout où le cas en parle — celle du résultat attendu dans l'« Alors », "
                   "jamais un « Alors » qui se contente de relire la valeur que le test vient de saisir —, jamais un scénario "
                   "par valeur, ni une valeur écrite en dur, ni un « Plan du scénario » avec des « Exemples » pour ces "
                   "variables : l'outil le rejoue lui-même pour chaque ligne."]
    return "\n".join(lignes)


def refus(feature: str, noms: frozenset[str] | set[str], source: str = "le projet déclare") -> list[str]:
    """Ce qui empêche d'écrire ce test (vide : accepté). Inconnues, mal écrites et mal placées : `resolution.remplacer`, les
    règles mêmes de l'exécution. Puis la règle des guillemets dans les lignes d'étape."""
    if "{{" not in (feature or "") and "}}" not in (feature or ""):
        return []
    rendu = resolution.remplacer(feature, {n: resolution.Valeur("x", "") for n in noms}, noms)
    fautes = [n if n.startswith("variable mal") else f"variable inconnue « {n} » ({source} : "
              f"{', '.join(sorted(noms)) or 'aucune'})" for n in rendu.inconnues]
    # Les mots d'étape sont ceux du dictionnaire de Behave (`resolution`), français et anglais : une liste écrite à la main
    # oubliait « Donc », « Sachant que »… (revue du 2026-10-14). Les lignes d'un bloc de texte ne sont pas des étapes.
    for ligne, place in resolution.places_des_lignes((feature or "").splitlines()):
        propre = ligne.strip()
        if place != "hors" or not propre.startswith(resolution._MOTS_D_ETAPE):
            continue
        if "{{" in _ENTRE_GUILLEMETS.sub("", propre):
            fautes.append(f"« {propre} » : une variable s'écrit entre guillemets, dans une valeur (\"{{{{nom}}}}\")")
    return fautes


def refus_dans_le_code(code: str) -> list[str]:
    """Une variable n'a pas sa place dans le code Python des steps : il n'est jamais remplacé à l'exécution."""
    trouvees = list(dict.fromkeys(m.group(0) for m in _DANS_LE_CODE.finditer(code or "")))
    return [f"« {t} » dans le code Python : une variable ne s'écrit que dans le .feature, jamais dans les steps"
            for t in trouvees]


def references_du_texte(texte: str) -> list[str]:
    """Toutes les écritures `{{…}}` du texte, dans l'ordre (doublons compris) — pour figer les variables en réparation."""
    return [m.group(0) for m in resolution._REFERENCE.finditer(texte or "")]


# ── Lot PT-02f (étape E2, A39) : le cas fait foi, aussi pour les données ─────────────────────────────────────────────────


def pour_les_cas(projet: dict | None) -> list[dict]:
    """Les variables montrées à l'IA qui RÉDIGE les cas (noms et descriptions, jamais les valeurs). Interrupteur PT-02f
    éteint ou projet sans variable : rien — le prompt des cas est celui d'avant, octet pour octet."""
    if not interrupteurs.cas_dit_ses_donnees_actif():
        return []
    return [{"nom": str(v.get("nom", "")), "description": str(v.get("description") or "")}
            for v in (projet or {}).get("variables_de_test") or [] if v.get("nom")]


def _textes_executes_du_cas(metier: dict) -> list[str]:
    """Le texte du cas qui dit ce que le test fait : préconditions, étapes, résultat attendu (le titre le NOMME seulement)."""
    etapes = metier.get("steps") or []
    return [str(metier.get("preconditions") or ""), *(str(e) for e in etapes), str(metier.get("expected_result") or "")]


def variables_citees(metier: dict | None) -> list[str]:
    """Les variables que le cas cite (`{{client}}`), bien écrites, dans l'ordre, sans doublon."""
    vues: dict[str, None] = {}
    for texte in _textes_executes_du_cas(metier or {}):
        for nom in resolution.references(texte):
            if "{" not in nom:
                vues.setdefault(nom, None)
    return list(vues)


def refus_dans_le_cas(metier: dict, noms: frozenset[str] | set[str] | list[str]) -> list[str]:
    """Ce qui empêche de valider ce cas (vide : accepté) : une variable dans le TITRE (il nomme le cas, il n'est jamais
    joué), une variable mal écrite, ou inconnue du projet. Revue humaine du cas : la personne voit ce message et corrige."""
    fautes = []
    if "{{" in str(metier.get("title") or "") or "}}" in str(metier.get("title") or ""):
        fautes.append("le titre ne contient pas de variable : il nomme le cas")
    connues = set(noms)
    for texte in _textes_executes_du_cas(metier):
        for nom in resolution.references(texte):
            if "{" in nom:
                fautes.append(f"variable mal écrite : « {nom} »")
            elif nom not in connues:
                fautes.append(f"variable inconnue « {{{{{nom}}}}} » (le projet déclare : {', '.join(sorted(connues)) or 'aucune'})")
        if "{{" in resolution._REFERENCE.sub("", texte):
            fautes.append(f"variable mal écrite dans « {texte[:60]} »")
    return list(dict.fromkeys(fautes))


def du_cas(variables: list[dict], metier: dict | None, deja_dans_le_test=(),
           a_la_corbeille=()) -> tuple[list[dict], frozenset[str], bool]:
    """(variables montrées à l'agent technique, variables que le test DOIT employer, contrôle « aucune autre » actif).

    PT-02f allumé, cas connu, projet à variables vues par l'agent (PT-02d) : seulement celles que le cas cite — toutes
    requises — plus celles que le test actuel emploie déjà (A41 : une régénération garde l'association d'un clic quand le
    cas n'écrivait pas la valeur) ; toute autre est refusée à l'écriture, même si le cas n'en cite aucune. Sinon :
    inchangé (PT-02d), rien de requis, aucun contrôle de plus.

    IT-3b (A57 à A59) : les variables que les LIGNES du cas font varier (`metier["variables_des_lignes"]`) sont requises
    comme si le cas les citait — même PT-02f éteint : ces lignes, une personne les a saisies, et un test qui ne les emploie
    pas est bloqué à l'exécution (A59)."""
    lignes = {str(n) for n in (metier or {}).get("variables_des_lignes") or ()}
    if not interrupteurs.cas_dit_ses_donnees_actif() or metier is None:
        noms = {v["nom"] for v in variables}
        return variables, frozenset(lignes & noms), False
    citees = set(variables_citees(metier)) | lignes
    if not variables:
        # Aucune variable vivante, mais le projet en a déclaré (à la corbeille) et le cas en cite : rien n'est montré et toute
        # écriture `{{…}}` — .feature ou code des steps — est refusée (revue du 2026-10-15, faux vert `"{{client}}" not in
        # page`). Un projet qui n'en a JAMAIS déclaré garde son parcours : « {{ nom }} » y reste du texte (A39).
        # Aussi quand seul le TEST l'employait (A41) : l'échec renvoyé à la régénération y montre `{{client}}` (revue, 4e passe).
        return variables, frozenset(), bool((citees or set(deja_dans_le_test or ())) and a_la_corbeille)
    permises = citees | set(deja_dans_le_test or ())
    retenues = [v for v in variables if v["nom"] in permises]
    # Porteur, 2026-10-22 (mesuré sur SauceDemo : « John », « Doe », « 12345 » écrits en dur dans le CONTEXTE d'un cas qui ne
    # parlait pas du formulaire) : les autres variables du projet sont montrées aussi, pour les seules étapes de PRÉPARATION
    # (Soit, Quand). Jamais requises, jamais dans un « Alors » (`refus_preparation_dans_les_alors`) : ce que le test VÉRIFIE
    # vient toujours du cas validé (A39).
    retenues += [{**v, "preparation": True} for v in variables if v["nom"] not in permises]
    return retenues, frozenset(v["nom"] for v in retenues if v["nom"] in citees), True


def ecart_cas_test(version: dict | None, noms_du_projet) -> list[str]:
    """Décision A42 (porteur, 2026-10-15) : les variables que le texte du cas cite et que son test technique n'emploie pas —
    après une modification faite à la main (le cas, ou le script). Non vide : le test ne peut être ni approuvé ni exécuté
    (une campagne sur trois jeux jouerait trois fois la même valeur en dur). L'inverse (le test emploie une variable que le
    cas ne cite pas) reste admis : A41. Rien hors PT-02f, ni pour un projet sans donnée de test, ni sans test technique."""
    version = version or {}
    feature = version.get("feature_content") or ""
    if not interrupteurs.cas_dit_ses_donnees_actif() or not noms_du_projet or not feature.strip():
        return []
    try:
        etapes = json.loads(version.get("test_steps") or "[]")
    except (TypeError, ValueError):
        etapes = [version.get("test_steps") or ""]
    metier = {"preconditions": version.get("preconditions"), "expected_result": version.get("expected_result"),
              "steps": etapes if isinstance(etapes, list) else [str(etapes)]}
    employees = set(resolution.references(feature))
    return [f"le cas cite « {{{{{nom}}}}} », le test ne l'emploie pas" for nom in variables_citees(metier)
            if nom not in employees]


ALORS_IDENTIQUE = "alors_identique_pour_toutes_les_lignes"


def lint_alors_sans_variable_des_lignes(feature: str, variables_des_lignes) -> list[dict]:
    """IT-3b (revue du 2026-10-19), signal DÉTECTIF : les lignes du cas font varier des variables, mais aucun « Alors » d'un
    scénario n'en VÉRIFIE une — il attend le MÊME résultat pour toutes les lignes. Légitime pour une classe d'équivalence ; un
    piège si le résultat attendu change d'une ligne à l'autre (une application qui refuse à tort à 18 ans passerait sur
    toutes les lignes). Une variable ne compte que si elle est dans un « Alors » ET dans aucune autre étape du scénario :
    « Alors le champ "Âge" contient "{{age}}" » relit la saisie, il ne vérifie aucun résultat (revue, 2e passe). Lu sur la
    STRUCTURE du Gherkin (type de step : « Alors » et les « Et »/« Mais » qui le suivent ; textes, tableaux et blocs de
    texte), jamais sur le libellé. Scénarios d'une « Règle » et plans compris. Jamais bloquant : le relecteur décide."""
    lignes = set(variables_des_lignes or ())
    if not lignes or not (feature or "").strip():
        return []
    from behave.parser import ParserError, parse_feature
    try:
        modele = parse_feature(feature, language="fr")
    except ParserError:
        return []
    if modele is None:
        return []

    def references_de(step) -> set[str]:
        texte = " ".join([step.name, *(c for r in (step.table.rows if step.table else []) for c in r.cells), step.text or ""])
        return set(resolution.references(texte)) & lignes

    contexte = set().union(*(references_de(s) for s in (modele.background.steps if modele.background else [])))
    avis = []
    for scenario in modele.walk_scenarios(with_outlines=True):
        if getattr(scenario, "_row", None) is not None:
            continue   # une instance d'un plan : le plan lui-même est lu (mesuré sur behave 1.3.3 : instances `_row` non nul)
        alors = [s for s in scenario.steps if getattr(s, "step_type", "") == "then"]
        if not alors:
            continue
        ailleurs = contexte.union(*(references_de(s) for s in scenario.steps if getattr(s, "step_type", "") != "then"))
        verifiees = set().union(*(references_de(s) for s in alors)) - ailleurs
        if not verifiees:
            noms = ", ".join("{{" + n + "}}" for n in sorted(lignes))
            avis.append({"step": scenario.name, "line": scenario.line, "kind": ALORS_IDENTIQUE,
                         "message": f"les lignes du cas font varier {noms}, mais aucun « Alors » n'en vérifie une (sans la "
                                    "saisir ailleurs) : ce scénario attend le même résultat pour toutes les lignes"})
    return avis


def refus_non_iterable(feature: str, noms) -> list[str]:
    """A61 : le test, s'il emploie des variables, peut-il être rejoué ligne par ligne ? On le réécrit comme l'exécution le
    fera (`parametres/iterations.en_plan_de_scenario`) avec deux lignes fictives différentes : un refus de la réécriture est
    un test qui sortirait « bloqué » au lancement (mesuré le 2026-10-20 : un « Plan du scénario » dont les Exemples
    répétaient `{{client}} | {{age}}`). Vide : rejouable."""
    from testpilot.parametres import iterations

    employes = [n for n in dict.fromkeys(resolution.references(feature)) if n in set(noms or ())]
    if not employes:
        return []
    try:
        iterations.en_plan_de_scenario(feature, [("A", {n: f"essai-a-{i}" for i, n in enumerate(employes)}),
                                                 ("B", {n: f"essai-b-{i}" for i, n in enumerate(employes)})], list(noms))
    except iterations.IterationsImpossibles as exc:
        return [f"ce test ne pourrait pas être rejoué ligne par ligne ({exc}) — écris un « Scénario » simple qui emploie "
                "les variables directement dans ses étapes, sans « Plan du scénario » ni « Exemples » pour elles"]
    return []


def refus_variables_du_cas(feature: str, requises: frozenset[str] | set[str]) -> list[str]:
    """Le test technique reprend CHAQUE variable que le cas cite — vérifié à l'écriture, sans IA (A39)."""
    presentes = set(resolution.references(feature))
    return [f"le cas emploie « {{{{{nom}}}}} » : écris-la dans le test, entre guillemets, à la place de la valeur"
            for nom in sorted(set(requises) - presentes)]


def refus_references_changees(texte: str, figees: list[str]) -> list[str]:
    """Réparation et correction : les variables du test de référence restent EXACTEMENT les mêmes (ni ajout, ni retrait,
    ni renommage) — la valeur appartient au jeu de données choisi au lancement, pas à l'agent."""
    if sorted(references_du_texte(texte)) == sorted(figees):
        return []
    return [f"les variables du test sont figées ({', '.join(figees) or 'aucune'}) : ni ajout, ni retrait, ni renommage"]


def masquer(texte: str, valeurs: dict[str, str]) -> str:
    """Remet `{{nom}}` à la place de chaque valeur posée, dans un texte RENVOYÉ à l'agent (échec d'un essai, échec d'une
    exécution) : il ne doit jamais lire une valeur, qu'il recopierait en dur (revue du 2026-10-14).

    Un seul passage (une valeur courte ne réécrit pas ce qu'une plus longue a déjà masqué, ni une variable déjà écrite),
    les plus longues d'abord ; une valeur qui commence ou finit par une lettre ou un chiffre n'est masquée qu'en mot entier
    (« Lyon » dans « Lyonnais » reste tel quel : `{{ville}}nais` serait recopié et joué « Parisnais » avec un autre jeu).
    Une valeur d'un seul caractère n'est pas masquée : elle masquerait n'importe quoi."""
    retenues = sorted(((nom, v) for nom, v in valeurs.items() if len(v) >= 2), key=lambda nv: len(nv[1]), reverse=True)
    if not retenues:
        return texte
    motifs = [r"(\{\{[^{}\r\n]*\}\})"]   # une variable déjà écrite : gardée telle quelle
    for _nom, valeur in retenues:
        debut = r"(?<!\w)" if valeur[0].isalnum() else ""
        fin = r"(?!\w)" if valeur[-1].isalnum() else ""
        motifs.append(f"({debut}{re.escape(valeur)}{fin})")
    motif = re.compile("|".join(motifs))

    def poser(trouve: re.Match) -> str:
        if trouve.group(1) is not None:
            return trouve.group(1)
        nom = next(n for i, (n, _v) in enumerate(retenues, start=2) if trouve.group(i) is not None)
        return "{{" + nom + "}}"

    return motif.sub(poser, texte)


def masquer_dans(donnees, valeurs: dict[str, str]):
    """`masquer` appliqué à chaque CHAÎNE d'une structure (dictionnaires, listes) — jamais au JSON sérialisé, où une valeur
    « 14 » réécrirait un nombre (`146`) et rendrait le texte illisible."""
    if isinstance(donnees, str):
        return masquer(donnees, valeurs)
    if isinstance(donnees, dict):
        return {cle: masquer_dans(v, valeurs) for cle, v in donnees.items()}
    if isinstance(donnees, list):
        return [masquer_dans(v, valeurs) for v in donnees]
    return donnees


def texte_de_l_essai(texte: str, valeurs: dict[str, str], noms: frozenset[str] | set[str]) -> tuple[str, list[str]]:
    """Le texte que l'essai jouera : variables remplacées par les valeurs du jeu « Par défaut ». Rend (texte, manques) ; un
    manque (variable inconnue, sans valeur, mal placée) : l'essai n'est pas joué."""
    if "{{" not in texte and "}}" not in texte:
        return texte, []
    rendu = resolution.remplacer(texte, {n: resolution.Valeur(v, "Par défaut") for n, v in valeurs.items()}, noms)
    manques = list(rendu.inconnues) + [f"variable sans valeur dans « Par défaut » : « {n} »" for n in rendu.sans_valeur]
    return rendu.texte, manques


def refus_preparation_dans_les_alors(feature: str, preparation: frozenset[str] | set[str]) -> list[str]:
    """Porteur, 2026-10-22 : une variable que le cas ne cite pas sert à PRÉPARER (Soit, Quand), jamais à VÉRIFIER — un
    « Alors » qui l'emploierait vérifierait une valeur du projet, pas ce que le cas a validé (A39). Lu par le parseur de
    Behave (type EFFECTIF des « Et »/« Mais »), sans IA. Un Gherkin illisible : rien ici, l'écriture le refuse ailleurs."""
    if not preparation:
        return []
    from behave.parser import ParserError, parse_feature

    try:
        parsed = parse_feature(feature or "", language="fr")
    except ParserError:
        return []
    if parsed is None:
        return []
    fautes = []
    etapes = []
    for conteneur in [parsed, *(getattr(parsed, "rules", None) or [])]:
        fond = getattr(conteneur, "background", None)
        etapes += list(fond.steps) if fond else []
    # Revue : les plans de scénario DÉVELOPPÉS (une valeur d'Exemples arrive dans l'« Alors » par `<v>`), et le tableau et le
    # bloc de texte de chaque étape — pas seulement son libellé.
    etapes += [e for s in parsed.walk_scenarios() for e in getattr(s, "steps", None) or []]
    for etape in etapes:
        if getattr(etape, "step_type", "") != "then":
            continue
        texte = [etape.name or "", getattr(etape, "text", None) or ""]
        table = getattr(etape, "table", None)
        if table is not None:
            texte += list(table.headings) + [c for ligne in table.rows for c in ligne.cells]
        for morceau in texte:
            for nom in sorted(set(resolution.references(str(morceau))) & set(preparation)):
                fautes.append(f"« {{{{{nom}}}}} » dans un « Alors » : le cas ne cite pas cette donnée, elle ne sert "
                              "qu'à préparer (Soit, Quand) ; ce que le test vérifie vient du cas")
    return list(dict.fromkeys(fautes))
