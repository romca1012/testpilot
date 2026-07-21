"""Assemblage des prompts du pilier generation.

Deux fonctions pures (ou quasi : lecture de fichier) :
  - ``build_system_prompt`` : socle connector-agnostic + catalogue des steps partagés
    + règles du connecteur actif.
  - ``build_initial_message`` : convertit le TestPlan en premier message utilisateur.
"""

from __future__ import annotations

from testpilot import config
from testpilot.analysis.plan import NavStep, TestPlan
from testpilot.connectors.base import Connector
from testpilot.generation import domain_model, steps_library
from testpilot.generation.steps_library import SharedStep

_SYSTEM_PROMPT_PATH = config.PROMPTS_DIR / "system_prompt.md"


def build_system_prompt(connector: Connector | None = None,
                        shared_steps: list[SharedStep] | None = None) -> str:
    """Prompt système + catalogue des steps partagés + règles du connecteur actif.

    Le catalogue est indispensable : le prompt demande de réutiliser la bibliothèque et
    interdit de la redéfinir, mais l'agent ne pouvait pas la voir — il inventait donc ses
    propres steps (et son propre transport HTTP). Cf. décision 0003.
    """
    base = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    catalogue = steps_library.as_prompt_section(shared_steps or [])
    if catalogue:
        base += "\n\n---\n\n## Steps partagés disponibles (à réutiliser)\n\n" + catalogue

    rules = connector.rules() if connector else ""
    if rules:
        base += "\n\n---\n\n## Connecteur actif\n\n" + rules
    return base


def _nav_to_gherkin_hint(navigation: list[NavStep]) -> str:
    """Traduit une séquence de navigation en indices Gherkin (aide, non contraignant)."""
    hints = []
    for step in navigation:
        if step.kind == "goto":
            hints.append(f'navigue vers "{step.target}"')
        elif step.kind == "click_tab":
            hints.append(f'clique sur l\'onglet "{step.target}"')
        elif step.kind == "click_item":
            hints.append(f'sélectionne "{step.target}"')
        elif step.kind == "js_trigger":
            hints.append(f'déclenche "{step.target}"')
    return " → ".join(hints)


def _section_champs_requis(plan: TestPlan, modele: dict | None) -> str:
    """La CONTRAINTE de complétude : les champs requis du formulaire visé, + l'obligation de
    soumettre. **Impérative, pas indicative.**

    ⚠️ **Pourquoi une contrainte et non une suggestion.** Le prompt système demandait déjà
    d'observer les champs requis (« lis-les sur le formulaire réel ») — une instruction qui dépend
    de l'exploration, donc du tirage, et que **rien ne vérifiait**. Mesuré sur la MÊME spec
    (2026-07-19) : une génération remplit 6 champs et soumet explicitement, la suivante en remplit
    **2 sur 8** et se contente d'« attendre la soumission ». Le second test ne crée rien : 4
    scénarios `non_conforme`, prouvés côté test (sonde HTTP/RPC : aucun POST, delta 0 ticket).
    L'annuaire connaissait pourtant les 8 requis depuis toujours — personne ne les lui donnait.

    Rien n'est injecté si aucun formulaire n'est identifié : on n'invente pas de contrainte
    (mieux vaut le silence qu'une consigne fausse). La section porte **la date du modèle** — c'est
    une photo, et le filet du gate reste le garant vivant (borne du principe 2).
    """
    routes = list(plan.portal_routes or [])
    if plan.entry_url:
        routes.append(plan.entry_url)
    formulaires = domain_model.formulaires_requis(modele, routes)
    if not formulaires:
        return ""

    date = (modele or {}).get("mesure_le", "?")
    lignes = [f"## Champs OBLIGATOIRES du formulaire — CONTRAINTE (annuaire mesuré le {date})", ""]
    for form in formulaires:
        # ⚠️ Un champ requis CACHÉ (`visible=False`) est injecté par le SERVEUR : le remplir par
        # l'interface est impossible (`TimeoutError` sur le sélecteur). Mesuré le 2026-07-21 sur
        # `/demande_avoir` (`partner_email`, `name`). On ne demande donc QUE les champs saisissables,
        # et on NOMME les autres pour que l'agent sache qu'ils sont couverts — sans quoi il croirait
        # la liste incomplète et tenterait de les remplir quand même.
        saisissables = [c for c in form["requis"] if c.get("visible", True)]
        caches = [c["name"] for c in form["requis"] if not c.get("visible", True)]
        lignes.append(f"Le formulaire `{form['route']}` EXIGE {len(form['requis'])} champs requis, "
                      f"dont **{len(saisissables)} à remplir par l'interface**. Tout scénario qui "
                      f"prétend CRÉER un enregistrement DOIT remplir TOUS ceux-ci :")
        fichiers = []
        for champ in saisissables:
            detail = ""
            if champ.get("type") == "file":
                # ⚠️ Le TYPE change la façon de remplir : un champ fichier refuse le texte.
                detail = " — **CHAMP FICHIER** : utilise `je joins un fichier au champ \"…\"`"
                fichiers.append(champ["name"])
            elif champ["options"]:
                detail = f" — valeurs possibles : {', '.join(champ['options'][:6])}"
            elif champ["tag"]:
                detail = f" ({champ['tag']})"
            lignes.append(f"  - `{champ['name']}`{detail}")
        if fichiers:
            lignes.append("")
            lignes.append(
                f"⚠️ **{len(fichiers)} champ(s) FICHIER** ({', '.join(f'`{f}`' for f in fichiers)}) : "
                "un `<input type=\"file\">` **n'accepte pas de texte** — écrire dedans lève "
                "`InvalidStateError` et le scénario échoue techniquement. Emploie le step partagé "
                "`je joins un fichier au champ \"<nom>\"`, qui téléverse une pièce jointe de test.")
        if caches:
            lignes.append("")
            lignes.append(
                f"⚠️ **NE tente PAS de remplir** {', '.join(f'`{c}`' for c in caches)} : "
                "ces champs requis sont **cachés** (`visible=false`) et **renseignés par le "
                "serveur**. Les chercher dans l'interface provoque un `TimeoutError` et fait "
                "échouer le scénario techniquement — alors qu'ils sont déjà couverts.")
        lignes.append("")
    lignes += [
        "**Deux obligations, non négociables :**",
        "1. **Remplir TOUS les champs requis ci-dessus** avant de soumettre. Un formulaire "
        "incomplet est refusé par l'application : rien n'est créé, et l'assertion de création "
        "échoue. Remplir un sous-ensemble produit un test qui ne teste rien.",
        "2. **Soumettre EXPLICITEMENT** par un step qui déclenche l'envoi (clic sur « Envoyer »). "
        "⚠️ « j'attends la soumission du formulaire » **n'envoie RIEN** — ce step se contente "
        "d'attendre. Un scénario qui remplit puis « attend » ne crée jamais rien.",
        "",
        "*(Exception légitime : un scénario `[ERREUR]` qui teste précisément l'omission d'un champ "
        "requis — là, l'omission est le sujet du test et doit être assumée comme telle.)*",
        "",
        "⚠️ **Mais UNIQUEMENT là.** Dans un scénario qui prétend CRÉER un enregistrement, "
        "`je laisse le champ \"…\" vide` sur un champ requis est une contradiction : le formulaire "
        "sera refusé et l'assertion de création échouera. "
        "*(Mesuré le 2026-07-21 : un scénario `[Nominal]` laissait vide un `<select>` requis.)*",
        "",
    ]
    return "\n".join(lignes)


# Un libellé présent sur beaucoup de pages est un élément de GABARIT, pas un repère de
# navigation : il ne dit rien sur « où aller ». Mesuré sur l'annuaire réel — `Envoyer` (le bouton
# de soumission des formulaires) apparaît sur 17 routes sur 37, `MyServices SAPIAN` (le logo) sur
# presque toutes. À 50 % ils passaient tous les deux, ajoutant 17 lignes qui n'apprennent rien.
# À 25 %, il ne reste que ce qui DISCRIMINE : `/myservices : Ordinateurs, Périphériques…` —
# exactement le fait qui manquait à `0020`.
_SEUIL_UBIQUITE = 0.25
# Bornes de taille : le prompt est payé à chaque tour de la boucle ReAct, pas une fois — c'est
# l'entrée répétée qui domine le coût (leçon mesurée du principe 3 : $0,2895/réparation, dominé
# par le renvoi du catalogue et du fichier à chaque tour).
# MESURÉ sur l'annuaire réel (38 routes) avec ces plafonds :
#   routes 974 car. · onglets 1 120 car. · selects 1 590 car. → 3 684 car. ≈ 920 tokens.
# Assumé : c'est le prix de faits qui remplacent de l'exploration payante et faillible. À
# resserrer si une mesure montre que la génération dérive — pas avant.
_MAX_ROUTES = 40
_MAX_SELECTS = 20


def _onglets_distinctifs(modele: dict) -> dict[str, list[str]]:
    """Les onglets propres à une route, débarrassés du gabarit commun à toutes les pages."""
    onglets = {k: v for k, v in (modele.get("onglets_internes") or {}).items() if v}
    if not onglets:
        return {}
    freq: dict[str, int] = {}
    for libelles in onglets.values():
        for lib in set(libelles):
            freq[lib] = freq.get(lib, 0) + 1
    plafond = max(1, int(len(onglets) * _SEUIL_UBIQUITE))
    retenus = {}
    for route, libelles in onglets.items():
        propres = sorted({lib for lib in libelles if freq.get(lib, 0) <= plafond})
        if propres:
            retenus[route] = propres
    return retenus


def _section_domaine_mesure(plan: TestPlan, modele: dict | None) -> str:
    """Les FAITS mesurés sur l'application : routes réelles, onglets, valeurs de listes.

    ⚠️ **Pourquoi cette section existe.** Ces faits étaient mesurés depuis le 2026-07-17
    (`data/domain/…json`, crawl déterministe sans LLM) et **lus par personne** : seuls les champs
    requis en sortaient. L'agent devait donc redécouvrir par exploration ce que le dépôt savait
    déjà — en payant, et en se trompant. Deux des cinq causes d'échec du cas 1 sont exactement là :

    - `0020` — le test cliquait l'onglet « Ordinateurs » depuis `/my/home`, où il n'existe pas.
      L'annuaire sait qu'il vit sur `/myservices`. C'est **la** donnée qui manquait.
    - `0019` — l'agent inventait la valeur `"new"` pour un `<select>`. L'annuaire connaît les
      options réelles (`new_aquisition`, `remplacement`).

    ⚠️ **Les transitions brutes ne sont PAS injectées**, délibérément. Mesuré : 36 des 38 routes
    pointent vers `/home`, `/contactus`, `/my/home`… — c'est le menu global, présent partout. Les
    déverser ajouterait des centaines de lignes qui ne discriminent rien, et diluerait les faits
    utiles. On ne paie pas un prompt pour du bruit.

    C'est une **photo datée** : la section le dit, et le gate reste le garant vivant (borne du
    principe 2). Modèle absent ⇒ section vide : on n'invente jamais un fait.
    """
    pages = (modele or {}).get("pages") or {}
    if not pages:
        return ""

    date = modele.get("mesure_le", "?")
    lignes = [f"## L'application, telle qu'elle a été MESURÉE (crawl du {date}, aucun LLM)", ""]

    routes = sorted(pages)[:_MAX_ROUTES]
    lignes.append(f"**Routes réelles** ({len(pages)} mesurées) — n'en invente aucune autre :")
    lignes.append("  " + ", ".join(f"`{r}`" for r in routes))
    if len(pages) > _MAX_ROUTES:
        lignes.append(f"  *(+{len(pages) - _MAX_ROUTES} autres)*")
    lignes.append("")

    # ⚠️ Les routes ci-dessus sont NORMALISÉES (`{id}`). Un test doit naviguer vers une URL
    # RÉELLE : sans exemple, l'agent invente un identifiant (mesuré : `/demande_avoir/29789`,
    # page qui ne rend pas le formulaire → `TimeoutError` sur un champ pourtant visible).
    # On ne donne les exemples que pour les routes VISÉES : les donner toutes noierait le signal.
    vises = {r for r in (list(plan.portal_routes or []) + [plan.entry_url or ""]) if r}
    exemples = [(r, i["url_exemple"]) for r, i in pages.items()
                if i.get("url_exemple") and i["url_exemple"] != r
                and any(v in r or r in v for v in vises)]
    if exemples:
        lignes.append("**URL réelles à utiliser** — ces routes contiennent un identifiant : "
                      "emploie l'exemple mesuré, n'invente JAMAIS un numéro :")
        for route, exemple in exemples[:8]:
            lignes.append(f"  - `{route}` → naviguer vers `{exemple}`")
        lignes.append("")

    onglets = _onglets_distinctifs(modele)
    if onglets:
        lignes += [
            "**Où vivent les onglets** — un onglet n'existe QUE sur sa page. Pour cliquer l'un "
            "d'eux, il faut d'abord être sur la route qui le porte :",
        ]
        for route in sorted(onglets):
            lignes.append(f"  - `{route}` : {', '.join(onglets[route])}")
        lignes.append("")

    # Les listes déroulantes : priorité aux routes que le plan vise, puis complément borné.
    vises = {r for r in (list(plan.portal_routes or []) + [plan.entry_url or ""]) if r}
    selects = [(route, ch) for route, infos in pages.items()
               for ch in (infos.get("champs") or [])
               if ch.get("tag") == "select" and ch.get("options")]
    selects.sort(key=lambda rc: (0 if any(v in rc[0] or rc[0] in v for v in vises) else 1, rc[0]))
    if selects:
        lignes += [
            "**Valeurs RÉELLES des listes déroulantes** — n'invente jamais une valeur d'option, "
            "l'application refuse celles qui n'existent pas :",
        ]
        for route, ch in selects[:_MAX_SELECTS]:
            valeurs = ", ".join(f"`{v}`" for v, _ in (ch["options"] or [])[:6])
            suite = " …" if len(ch["options"] or []) > 6 else ""
            lignes.append(f"  - `{route}` · `{ch['name']}` : {valeurs}{suite}")
        lignes.append("")

    lignes.append("*(Mesure datée : si l'application a changé depuis, le gate le signalera.)*")
    lignes.append("")
    return "\n".join(lignes)


def _section_metier(metier: dict) -> str:
    """Le document métier VALIDÉ PAR UN HUMAIN — la source du Gherkin (décision `0022` n°5/6).

    Quand il est présent, il REMPLACE la liste des scénarios du plan : l'agent n'a plus à choisir
    quoi couvrir, un humain l'a déjà tranché. C'est tout l'intérêt des deux passes — le technique
    est écrit pour une intention **déjà validée**, jamais pour une intention supposée.

    Correspondance imposée par `0022` n°6 : **1 cas = 1 scénario**. Les préconditions deviennent
    le `Contexte`, les étapes les actions, le résultat attendu l'assertion finale.
    """
    etapes = "\n".join(f"{i}. {s}" for i, s in enumerate(metier.get("steps") or [], start=1))
    lines = [
        "## LE CAS À AUTOMATISER — document validé par un humain",
        "",
        "⚠️ Ce document fait FOI. N'invente pas d'autre scénario, n'en ajoute pas, n'en retire pas.",
        "Écris **UN SEUL scénario** qui implémente exactement ce qui suit.",
        "",
        f"**Titre** : {metier.get('title', '')}",
    ]
    if metier.get("preconditions"):
        lines += ["", f"**Préconditions** (→ `Contexte:`) : {metier['preconditions']}"]
    lines += ["", "**Étapes** (→ les actions du scénario) :", etapes,
              "", f"**Résultat attendu** (→ l'assertion FINALE) : {metier.get('expected_result', '')}"]
    return "\n".join(lines)


def build_initial_message(plan: TestPlan, modele: dict | None = None,
                          metier: dict | None = None) -> str:
    """Message utilisateur initial : le plan mis en forme pour la boucle ReAct.

    `modele` — l'annuaire du domaine (`domain_model.charger_modele`). Optionnel : sans lui, le
    message est celui d'avant (aucune contrainte de complétude n'est inventée).

    `metier` — le document métier validé (passe 4b de `0022`). Présent, il remplace la liste des
    scénarios : le périmètre n'est plus déduit par l'agent, il est donné."""
    lines = [
        f"# Génère les tests Behave pour le module « {plan.module_name} »",
        "",
        f"Type de système : {plan.connector_type}",
        f"Modèles impliqués : {', '.join(f'`{m}`' for m in plan.models) or '(à découvrir)'}",
        f"Personas : {', '.join(plan.personas)}",
        f"Routes : {', '.join(plan.portal_routes) or '(aucune)'}",
    ]
    if plan.entry_url:
        lines.append(f"URL d'entrée : {plan.entry_url}")
    if plan.server_injected_fields:
        lines.append(f"Champs injectés côté serveur : {', '.join(plan.server_injected_fields)}")
    if plan.required_role:
        lines.append(f"Rôle requis : {plan.required_role}")
    if plan.risks:
        lines.append("Ambiguïtés signalées : " + "; ".join(plan.risks))

    # Les FAITS mesurés d'abord : routes réelles, où vivent les onglets, valeurs des listes. Ils
    # cadrent tout le reste — un scénario écrit contre une route inexistante est perdu quel que
    # soit son contenu, et c'est la cause de 2 des 5 échecs du cas 1 (`0019`, `0020`).
    domaine = _section_domaine_mesure(plan, modele)
    if domaine:
        lines.append("\n" + domaine)

    # La contrainte de complétude AVANT les scénarios : elle conditionne la façon de les écrire.
    contrainte = _section_champs_requis(plan, modele)
    if contrainte:
        lines.append("\n" + contrainte)

    # Le document métier validé PRIME sur les scénarios déduits par l'analyse : les deux listés
    # ensemble donneraient à l'agent deux périmètres concurrents, et c'est le non-validé qui
    # risquerait de gagner (il est plus détaillé). Un seul périmètre, celui qu'un humain a signé.
    if metier:
        lines.append("\n" + _section_metier(metier))
        if plan.raw_spec:
            lines.append("\n## Spécification originale (contexte)\n")
            lines.append(plan.raw_spec[:3000])
        return "\n".join(lines)

    lines.append("\n## Scénarios à couvrir\n")
    for s in plan.scenarios:
        lines.append(f"### [{s.type.upper()}] {s.name}")
        lines.append(f"- Action : {s.action}")
        lines.append(f"- Persona : {s.persona}")
        if s.preconditions:
            lines.append(f"- Prérequis : {', '.join(s.preconditions)}")
        lines.append(f"- Résultat attendu : {s.expected_outcome}")
        nav = _nav_to_gherkin_hint(s.navigation)
        if nav:
            lines.append(f"- Navigation indicative : {nav}")
        if s.assertions:
            checks = "; ".join(f"{a.get('field')}={a.get('expected')}" for a in s.assertions)
            lines.append(f"- Assertions : {checks}")
        lines.append("")

    if plan.raw_spec:
        lines.append("## Spécification originale (extrait)\n")
        lines.append(plan.raw_spec[:3000])

    return "\n".join(lines)
