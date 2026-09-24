"""Smoke-check pré-génération — le test référence-t-il des choses qui EXISTENT ? (étape 4).

Module **PUR** : il reçoit un modèle du domaine (dict), il ne fait **aucune I/O**, **aucun appel
LLM**. Coût : nul.

RAISON D'ÊTRE — la classe de bugs qui revient depuis le début. L'agent **devine** une propriété de
l'environnement réel au lieu de la lire, et personne ne s'en aperçoit avant un run Behave de
plusieurs minutes, parfois plusieurs tentatives de réparation :

    0019 : `types_demandes = "new"`      → la valeur n'existe pas ('nouvel_entrant', …)
    0020 : clic sur l'onglet du catalogue → mais depuis /my/home, où il n'est pas
    0007 : `champ "Raison de la demande"` → le nom technique est `name`

Chacune a coûté **un run réel** (30 s à 5 min) pour être découverte, puis des tentatives de
réparation à ~$0,21. Ici on les voit **avant le premier run**, en lisant un modèle déjà mesuré.

⚠️ **DÉTECTIF, JAMAIS BLOQUANT** — et ce n'est pas une prudence de façade. Le §6 du brief accorde
à l'agent le droit d'explorer ; la borne du principe 2 (`PRINCIPES.md`) en tire la règle : *une
garde qui pourrait refuser un test légitime doit être détective*. Ici le faux positif est **réel
et attendu** :

  • un champ peut n'apparaître qu'**après une interaction** (formulaire dynamique) — le crawl ne
    le voit pas ;
  • un `<select>` peut être **peuplé en JS** après chargement ;
  • un test peut viser une route **volontairement inexistante** (le cas `[ERREUR]` du cas 1 teste
    `/formulaire/0` — un ID invalide, c'est **le but du scénario**).

La sortie alimente donc le **même bandeau non-bloquant** que le lint `0008` au gate : `allowed`
n'est jamais touché, un humain tranche. Même contrat de sortie (`list[dict]`), même bandeau.

⚠️ **Le modèle est une PHOTO.** Il vieillit dès que l'application change : un avertissement peut
donc dire « ce champ n'existe pas » alors qu'il vient d'être ajouté. C'est la seconde raison de ne
jamais bloquer — et la raison pour laquelle chaque avertissement dit **la date du modèle**.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# ── Les tournures Gherkin qui posent une VALEUR dans un CHAMP ────────────────
#
# ⚠️ **Relevées sur les 3 cas RÉELS, pas imaginées** — et il en fallait plus d'une. Mon premier jet
# ne couvrait que la tournure du cas 1 (« le champ … est rempli avec … ») : le smoke-check était
# **muet sur les cas 2 et 6**, soit 2 cas sur 3, et son silence ressemblait à une validation.
# C'est le motif que ce projet traque — « l'absence de signal prise pour un signal positif ».
# Vérifié en le branchant sur la vraie base : 12 lignes reconnues sur le cas 1, **0** sur les
# autres. L'agent n'a aucune raison d'écrire toujours la même phrase : le §6 lui laisse composer.
#
# Ordre indifférent (champ→valeur ou valeur→champ), mais chaque motif nomme ses deux groupes.
_TOURNURES = (
    # cas 1  : Et le champ demande "types_demandes" est rempli avec "new"
    re.compile(r'champ\s+(?:demande\s+)?"(?P<champ>[^"]+)"\s+est\s+rempli\s+avec\s+"(?P<valeur>[^"]*)"',
               re.IGNORECASE),
    # cas 2/6 : Et je renseigne le champ "denomination" avec la valeur "Peugeot Expert 2024"
    re.compile(r'renseigne\s+le\s+champ\s+"(?P<champ>[^"]+)"\s+avec\s+(?:la\s+valeur\s+)?"(?P<valeur>[^"]*)"',
               re.IGNORECASE),
    # cas 6  : Et je sélectionne "new_aquisition" dans le champ "type_investissement"
    re.compile(r'(?:sélectionne|selectionne|choisis|choisit)\s+"(?P<valeur>[^"]*)"\s+dans\s+le\s+champ\s+"(?P<champ>[^"]+)"',
               re.IGNORECASE),
)

# ⚠️ **Ce qui N'EST PAS matché, volontairement** : les tournures de VÉRIFICATION
# (« le dernier ticket créé a le champ "team_id" pointant vers … », « … égal à … »). Elles
# affirment un état APRÈS coup et portent des noms de champs du **modèle Odoo** (RPC), pas des
# attributs HTML d'un formulaire. Les confondre ferait crier `champ_inconnu` sur des assertions
# parfaitement valides — un faux positif systématique, exactement ce que la borne du principe 2
# interdit.


def _extraire_champ_valeur(ligne: str):
    """`(champ, valeur)` si la ligne pose une valeur dans un champ, sinon `None`."""
    for motif in _TOURNURES:
        m = motif.search(ligne)
        if m:
            return m.group("champ"), m.group("valeur")
    return None


@dataclass
class SmokeWarning:
    """Contrat de sortie **identique** à `LintWarning` (`0008`) : `step`, `line`, `kind`, `message`.

    ⚠️ **Les clés ne sont pas « à peu près » les mêmes, elles SONT les mêmes.** La route du gate
    fait `schemas.LintWarning(**w)` : une clé en trop (`source`) ou un nom différent (`subject`)
    lève une `ValidationError` et **casse l'affichage du cas**, pour un module dont tout l'objet
    est d'informer sans nuire. `repair_diff` (`0017`) respecte déjà ce contrat — on ne fabrique pas
    un troisième format pour le même bandeau (principe 4 : une règle, un point de vérité).

    `step` porte ici le **champ concerné** — c'est ce que `0008` met dans ce slot pour un step, et
    ce qu'un relecteur cherche : *de quoi parle-t-on ?*
    """

    kind: str
    step: str
    message: str
    line: int = 0

    def as_dict(self) -> dict:
        return {"step": self.step, "line": self.line, "kind": self.kind, "message": self.message}


def _index_selects(modele: dict) -> dict[str, set[str]]:
    """`{nom_de_select: {valeurs valides}}`, tous formulaires confondus.

    ⚠️ **Union volontaire, et c'est un choix.** Le même `<select>` apparaît sur plusieurs pages
    (mesuré : 46 occurrences pour 22 noms distincts, et `country_id` sur 3 pages). On ne sait pas
    depuis le Gherkin **quelle page** est visée — le dire exigerait de suivre la navigation, ce
    que ce module pur ne fait pas. On unit donc les valeurs : **on ne signale que ce qui n'existe
    NULLE PART**. Moins précis, mais **zéro faux positif** sur une valeur valide ailleurs — et
    `0019` (« new » n'existe sur aucune page) est attrapé quand même.
    """
    par_nom: dict[str, set[str]] = {}
    for infos in (modele.get("pages") or {}).values():
        for champ in infos.get("champs") or []:
            if champ.get("tag") != "select" or not champ.get("options"):
                continue
            valeurs = {str(v) for v, _ in champ["options"]}
            libelles = {str(t) for _, t in champ["options"]}
            par_nom.setdefault(champ["name"], set()).update(valeurs | libelles)
    return par_nom


def _index_champs(modele: dict) -> set[str]:
    return {c["name"] for i in (modele.get("pages") or {}).values()
            for c in (i.get("champs") or [])}


_ROUTE_NAV = re.compile(r'navigue\s+vers\s+(?:l\'URL\s+du\s+portail\s+)?"(?P<url>[^"]+)"', re.IGNORECASE)

# ⚠️ Préfixe des sources `verified_fields` qui portent un TEXTE observé (§F8, 2026-09-23),
# jamais un nom de champ — `check_champs_existants` doit les ignorer, `check_messages_observes`
# (plus bas) est seul à les lire.
MESSAGE_SOURCE_PREFIX = "message:"

# ⚠️ Préfixe des sources `verified_fields` qui portent le CATALOGUE visible d'une page (liens,
# produits — lot 12, 2026-09-24) : des textes, jamais des noms de champ.
CATALOGUE_SOURCE_PREFIX = "catalogue:"

# Un scénario qui AFFIRME une création : c'est là, et seulement là, qu'une soumission est due.
_AFFIRME_CREATION = (
    re.compile(r"augmente\s+de\s+1", re.IGNORECASE),
    re.compile(r'existe\s+dans\s+le\s+modèle\s+"', re.IGNORECASE),
)

# Steps qui SOUMETTENT réellement (action), par opposition à l'attente passive.
#
# ⚠️ **Faux positif RÉEL, mesuré sur le cas C19 (Parc IT, 2026-09-18)** : le motif quoté exigeait
# une correspondance EXACTE au libellé du bouton (`"Envoyer"`, rien d'autre) — `je clique sur le
# bouton "Confirmer"` ne matchait donc PAS, alors que « Confirmer » est le VRAI bouton de
# soumission documenté (PDF Parc IT : « cliquer sur Confirmer », et `equipment_order.py::
# confirm_order()` crée bel et bien l'enregistrement). Le contrôle criait « rien ne sera créé »
# sur un scénario qui soumettait déjà correctement — exactement le risque qu'une fausse alerte
# fait perdre confiance dans le signal vrai. Deux corrections, mesurées sur les 6 sections du
# document Parc IT (boutons réels : Confirmer, Valider l'affectation, Confirmer la
# réaffectation, Confirmer le changement) :
# 1. Ajout de « confirme »/« confirmer » aux verbes reconnus.
# 2. Le motif quoté n'exige plus une correspondance EXACTE — un libellé de plusieurs mots
#    contenant le verbe (« Confirmer la réaffectation ») doit compter, pas seulement le mot seul.
#
# ⚠️ **Même classe de faux positif, cette fois sur Odoo** : « Enregistrer »/« Save » est le
# libellé STANDARD du bouton de sauvegarde Odoo (formulaires backoffice génériques), absent des
# deux motifs ci-dessus — chaque cas généré contre Odoo qui clique sur « Enregistrer » déclenche
# à tort le même « point de vigilance » que Parc IT avec « Confirmer ». Ajouté par le même patron.
_SOUMET = (
    re.compile(r'\b(?:soumets?|soumis|soumet|envoie|envoi|valide|confirme|confirmer'
              r'|enregistre|enregistrer|save)\b', re.IGNORECASE),
    re.compile(r'clique[^"\n]*"[^"]*\b(?:Envoyer|Soumettre|Valider|Confirmer|Submit|Confirm'
              r'|Enregistrer|Save)\b[^"]*"', re.IGNORECASE),
)
# ⚠️ « j'attends la soumission du formulaire » N'EST PAS une soumission : le helper partagé
# (`wait_form_submission`) ne fait qu'ATTENDRE, il ne clique rien. C'est la cause exacte du
# ticket jamais créé de v20 — le scénario remplissait puis « attendait » un envoi que personne
# n'avait déclenché. Il faut donc l'exclure explicitement, sinon le contrôle se tait dessus.
_ATTENTE_PASSIVE = re.compile(r"attends?\s+la\s+soumission", re.IGNORECASE)


def _index_formulaires(modele: dict) -> list[tuple[str, set[str], set[str]]]:
    """`[(route, tous_les_champs, champs_requis)]` pour chaque page portant des champs."""
    formulaires = []
    for route, infos in (modele.get("pages") or {}).items():
        champs = infos.get("champs") or []
        if not champs:
            continue
        noms = {c["name"] for c in champs if c.get("name")}
        requis = {c["name"] for c in champs if c.get("name") and c.get("required")}
        if requis:
            formulaires.append((route, noms, requis))
    return formulaires


def forme_cible(champs_remplis: set[str], routes: list[str], modele: dict):
    """Quel formulaire le scénario remplit-il ? → `(route, champs_requis)`, ou `None` si on ne
    peut pas le dire — **le silence est la position par défaut** (§4.4 : faux négatif acceptable,
    faux positif non-bloquant à éviter absolument sur un signal détectif).

    Clé principale : le **sous-ensemble des champs remplis** (le scénario arrive souvent au
    formulaire par des CLICS, sans jamais nommer sa route — c'est le cas de v20, d'où le refus
    d'exiger une route explicite). On retient les formulaires dont les champs **contiennent tous**
    ceux que le scénario remplit ; la route sert de **désambiguïsation**.

    ⚠️ **Raffinement décidé sur les données réelles, et il est indispensable.** L'ambiguïté n'est
    dirimante que si les candidats **ne s'accordent pas**. Mesuré : les champs de v20
    (`name` + `types_demandes`) désignent DEUX routes — `/formulaire/{id}` et
    `/product/{id}/accessories` — qui exigent **exactement les mêmes 8 champs**. Se taire là serait
    se taire sur le cas même qu'on veut attraper, alors qu'aucune information ne manque : peu
    importe laquelle des deux, la réponse est la même. On ne se tait donc que si les candidats
    **divergent** sur l'ensemble requis.
    """
    if not champs_remplis:
        return None
    candidats = [(r, req) for r, noms, req in _index_formulaires(modele)
                 if champs_remplis <= noms]
    if not candidats:
        return None
    if len(candidats) > 1:
        # Désambiguïsation par la route explicitement visitée, quand il y en a une.
        cible = [(r, req) for r, req in candidats
                 if any(_meme_route(r, u) for u in routes)]
        if len(cible) == 1:
            return cible[0]
        # Sinon : tolérable UNIQUEMENT si tous les candidats exigent la même chose.
        requis = {frozenset(req) for _, req in candidats}
        if len(requis) != 1:
            return None
        return " ou ".join(r for r, _ in candidats), set(candidats[0][1])
    return candidats[0]


def _meme_route(route_modele: str, url: str) -> bool:
    """`/formulaire/{id}` correspond-il à `…/formulaire/78` ? (segments, placeholders joker)."""
    a = [s for s in route_modele.strip("/").split("/") if s]
    b = [s for s in url.split("?")[0].rstrip("/").split("/") if s and "://" not in s]
    b = b[-len(a):] if len(b) >= len(a) else b
    if len(a) != len(b):
        return False
    return all(x.startswith("{") or x == y for x, y in zip(a, b))


def _scenarios(feature_content: str) -> list[tuple[str, int, list[str]]]:
    """Découpe le `.feature` en `(titre, ligne_de_début, lignes)`. Le Contexte est ignoré :
    il ne remplit pas de formulaire."""
    scenarios, courant = [], None
    for num, ligne in enumerate(feature_content.split("\n"), 1):
        if re.match(r"\s*(?:Scénario|Scenario)\b", ligne):
            courant = (ligne.strip().split(":", 1)[-1].strip() or "sans titre", num, [])
            scenarios.append(courant)
        elif courant is not None:
            courant[2].append(ligne)
    return scenarios


def check_champs_requis_remplis(feature_content: str, modele: dict) -> list[dict]:
    """Le scénario remplit-il TOUS les champs requis du formulaire qu'il vise ? — le motif de v20.

    Mesuré : v20 remplissait **2 champs sur 8 requis** puis affirmait qu'un ticket était créé. Le
    formulaire refuse la soumission (validation navigateur) → aucun ticket → 4 scénarios
    `non_conforme`, diagnostiqués à la main pour $0. Ce contrôle le dit **avant le run**, en
    nommant les champs manquants — jamais un générique « formulaire incomplet ».
    """
    date = modele.get("mesure_le", "?")
    warnings: list[SmokeWarning] = []
    for titre, ligne0, lignes in _scenarios(feature_content):
        # ⚠️ **Uniquement les scénarios qui AFFIRMENT une création** — borne trouvée sur les
        # données réelles, pas en théorie. Le scénario « [ERREUR] Soumission du formulaire sans
        # remplir le champ obligatoire » de v20 omet un champ requis **exprès** : c'est tout son
        # objet (§ couverture minimale : « champ requis manquant »). L'alerter serait le faux
        # positif systématique que la borne du principe 2 interdit — on crierait sur le scénario
        # le mieux écrit du lot. Un scénario qui ne prétend rien créer n'a aucune obligation de
        # complétude.
        corps = "\n".join(lignes)
        if not any(m.search(corps) for m in _AFFIRME_CREATION):
            continue
        remplis, routes = set(), []
        for ligne in lignes:
            trouve = _extraire_champ_valeur(ligne)
            if trouve:
                remplis.add(trouve[0])
            nav = _ROUTE_NAV.search(ligne)
            if nav:
                routes.append(nav.group("url"))
        cible = forme_cible(remplis, routes, modele)
        if cible is None:
            continue                        # formulaire non identifié → on se tait
        route, requis = cible
        manquants = sorted(requis - remplis)
        if not manquants:
            continue
        warnings.append(SmokeWarning(
            kind="champs_requis_manquants", step=titre[:60], line=ligne0,
            message=(f"Le formulaire {route} exige {len(requis)} champs requis ; "
                     f"{len(manquants)} ne sont pas remplis : {', '.join(manquants)}. "
                     f"Un formulaire incomplet est refusé à la soumission — le scénario ne créera "
                     f"rien, et son assertion de création échouera. "
                     f"(modèle mesuré le {date})")))
    return [w.as_dict() for w in warnings]


def check_step_soumission(feature_content: str) -> list[dict]:
    """Un scénario qui AFFIRME une création soumet-il vraiment ? — l'autre moitié du motif v20.

    ⚠️ **« j'attends la soumission du formulaire » ne soumet RIEN** : le helper partagé se contente
    d'attendre. v20 remplissait, attendait, puis affirmait « le nombre augmente de 1 » — sans que
    rien n'ait jamais été envoyé. Vérifié en réel (sonde HTTP/RPC) : **aucun POST**, delta 0.

    On ne se déclenche que si le scénario **affirme une création** : un scénario de consultation
    n'a rien à soumettre, l'alerter serait un faux positif systématique.

    **Limite assumée** : une tournure de soumission très exotique passerait inaperçue (faux
    négatif). Direction sûre — §4.4 tolère le faux négatif ici, jamais le faux positif bloquant.
    """
    warnings: list[SmokeWarning] = []
    for titre, ligne0, lignes in _scenarios(feature_content):
        corps = "\n".join(lignes)
        if not any(m.search(corps) for m in _AFFIRME_CREATION):
            continue
        actives = [l for l in lignes
                   if any(m.search(l) for m in _SOUMET) and not _ATTENTE_PASSIVE.search(l)]
        if actives:
            continue
        passif = " Le scénario « attend » la soumission, ce qui n'envoie rien." \
            if _ATTENTE_PASSIVE.search(corps) else ""
        warnings.append(SmokeWarning(
            kind="soumission_absente", step=titre[:60], line=ligne0,
            message=(f"Ce scénario affirme qu'un enregistrement est créé, mais aucun step ne "
                     f"SOUMET le formulaire.{passif} Ajoute un step qui déclenche l'envoi "
                     f"(clic sur « Envoyer »), sinon rien ne sera créé et l'assertion échouera.")))
    return [w.as_dict() for w in warnings]


def check_valeurs_de_select(feature_content: str, modele: dict) -> list[dict]:
    """Les valeurs passées aux `<select>` existent-elles ? — le motif `0019`, vu avant le run.

    On accepte **valeur technique OU libellé affiché** : le helper partagé
    (`select_option_strict`) résout les deux, donc signaler un libellé serait un faux positif.
    """
    selects = _index_selects(modele)
    if not selects:
        return []
    date = modele.get("mesure_le", "?")
    warnings: list[SmokeWarning] = []
    for num, ligne in enumerate(feature_content.split("\n"), 1):
        trouve = _extraire_champ_valeur(ligne)
        if not trouve:
            continue
        champ, valeur = trouve
        connues = selects.get(champ)
        if connues is None:
            continue                      # pas un select connu : rien à dire (cf. docstring)
        if valeur in connues:
            continue
        apercu = ", ".join(sorted(v for v in connues if v)[:6])
        warnings.append(SmokeWarning(
            kind="valeur_option_inexistante", step=champ, line=num,
            message=(f"« {valeur} » n'est pas une option connue de « {champ} ». "
                     f"Valeurs relevées sur l'application : {apercu}. "
                     f"(modèle mesuré le {date} — à revérifier si l'application a changé)")))
    return [w.as_dict() for w in warnings]


def check_champs_existants(feature_content: str, modele: dict,
                           verified_fields: dict[str, list[str]] | None = None) -> list[dict]:
    """Les champs référencés existent-ils quelque part ? — le motif `0007`.

    ⚠️ Union sur TOUT le domaine, comme les selects : on ne signale que l'introuvable **partout**.
    Un champ qui n'existe nulle part est une invention ; un champ existant ailleurs peut être une
    erreur de page (`0020`) — mais ça, ce module ne peut pas le trancher, et il ne prétend pas le
    faire.
    """
    connus = _index_champs(modele)
    for source, names in (verified_fields or {}).items():
        if source.startswith((MESSAGE_SOURCE_PREFIX, CATALOGUE_SOURCE_PREFIX)):
            continue  # §F8 / lot 12 : un texte observé (message, catalogue) n'est pas un nom de champ
        connus.update(names)
    if not connus and verified_fields is None:
        return []
    date = modele.get("mesure_le", "?")
    warnings: list[SmokeWarning] = []
    for num, ligne in enumerate(feature_content.split("\n"), 1):
        trouve = _extraire_champ_valeur(ligne)
        if not trouve:
            continue
        champ = trouve[0]
        if champ in connus:
            continue
        warnings.append(SmokeWarning(
            kind="champ_inconnu", step=champ, line=num,
            message=(f"Aucun champ « {champ} » relevé sur l'application. Si c'est un libellé "
                     f"affiché, le nom technique est attendu ({{field}} = attribut HTML `name`, "
                     f"cf. 0007). (crawl mesuré le {date}, inspections de cette version incluses)")))
    return [w.as_dict() for w in warnings]


# ── Un message affiché doit avoir été OBSERVÉ, jamais deviné (§F8, 2026-09-23) ────────────────
#
# ⚠️ **Le défaut mesuré en campagne réelle** (cas 97, projet Sapian portail, 23/09) : un step
# personnalisé (« le message de validation HTML5 contenant "…" est affiché sur le champ "…" »)
# figeait un texte DEVINÉ par l'agent — la Règle 6 du prompt le lui interdisait déjà explicitement,
# mais une règle lue par l'agent n'est pas une preuve (0011, décision 0015 : le texte de l'agent
# n'est jamais une source de vérité). Ce contrôle est le filet STRUCTUREL, indépendant de ce que
# l'agent choisit de suivre. Le refus réel de l'application était bien réel — c'est le TEXTE du
# test qui se trompait, produisant un faux `non_conforme` (l'app a raison, le test a tort).
#
# Réutilise le registre `verified_fields` déjà threadé partout dans la génération (0007), sous un
# préfixe dédié (`MESSAGE_SOURCE_PREFIX`, défini plus haut) — jamais un second mécanisme parallèle
# (cf. many2one, même principe : une valeur ou un texte affirmé doit être ADOSSÉ à une observation
# RÉELLE, pas à la mémoire de l'agent).

_MESSAGE_ATTENDU = re.compile(r'\bmessage\b[^"\n]{0,60}"(?P<message>[^"]+)"', re.IGNORECASE)


# Longueur minimale d'un message observé pour disculper un texte affirmé par SOUS-CHAÎNE : un
# message vide ou d'un caractère (« », « . ») est sous-chaîne de n'importe quel texte et
# disculperait tout (revue verdict-reviewer, 2026-09-24).
_LONGUEUR_MIN_MESSAGE_OBSERVE = 8


def _messages_observes(verified_fields: dict[str, list[str]] | None) -> set[str]:
    return {texte for source, valeurs in (verified_fields or {}).items()
            if source.startswith(MESSAGE_SOURCE_PREFIX) for texte in valeurs
            if len(str(texte).strip()) >= _LONGUEUR_MIN_MESSAGE_OBSERVE}


def check_messages_observes(feature_content: str,
                            verified_fields: dict[str, list[str]] | None) -> list[dict]:
    """Un texte de message attendu dans une assertion (`Alors`/`Et`/`Mais`) doit correspondre à un
    message RÉELLEMENT observé pendant la génération — sinon c'est une invention, exactement le
    motif du cas 97 (§F8).

    ⚠️ **Limite assumée, comme le reste de ce module** : ne détecte que les tournures qui passent
    le texte attendu en PARAMÈTRE Gherkin (quoté dans le `.feature`) — un step personnalisé qui
    figerait le texte entièrement en Python, sans jamais le faire transiter par le `.feature`,
    échapperait à ce contrôle (faux négatif accepté, §4.4, jamais un faux positif bloquant).

    `verified_fields is None` (version ancienne sans registre) ne peut rien prouver ni infirmer :
    silence, comme `check_champs_existants` dans le même cas.
    """
    if verified_fields is None:
        return []
    observes = _messages_observes(verified_fields)
    warnings: list[SmokeWarning] = []
    for num, ligne in enumerate(feature_content.split("\n"), 1):
        if not re.match(r"\s*(?:Alors|Et|Mais)\b", ligne, re.IGNORECASE):
            continue
        trouve = _MESSAGE_ATTENDU.search(ligne)
        if not trouve:
            continue
        texte = trouve.group("message")
        if any(texte in obs or obs in texte for obs in observes):
            continue
        warnings.append(SmokeWarning(
            kind="message_non_observe", step=texte[:60], line=num,
            message=(f"Le texte « {texte} » n'a jamais été observé pendant la génération (aucun "
                     f"outil d'inspection ne l'a rapporté). Un message affiché s'observe, il ne se "
                     f"devine jamais (Règle 6) — vérifie-le via `attempt_form_submission` si le "
                     f"projet l'autorise, ou limite l'assertion à une présence sans texte exact.")))
    return [w.as_dict() for w in warnings]


def plus_proches(valeur: str, candidats, n: int = 5) -> list[str]:
    """Les `n` valeurs réelles les plus proches de `valeur` (insensible à la casse, `difflib`)."""
    bas = {str(c).lower(): str(c) for c in candidats if str(c).strip()}
    return [bas[t] for t in difflib.get_close_matches(str(valeur).lower(), list(bas), n=n,
                                                      cutoff=0.0)]


_PRODUIT = (re.compile(r'produit\s+"(?P<p>[^"]+)"\s+dans\s+la\s+liste', re.IGNORECASE),
            re.compile(r'produit\s+dans\s+la\s+liste\s+contenant\s+"(?P<p>[^"]+)"', re.IGNORECASE))


def check_produits_observes(feature_content: str,
                            verified_fields: dict[str, list[str]] | None) -> list[dict]:
    """Un produit choisi dans une liste web doit avoir été OBSERVÉ pendant la génération (lot 12).

    ⚠️ **DÉTECTIF, jamais bloquant (D11)** : une liste de produits observée n'est pas exhaustive
    (pagination, filtres, produit créé par le scénario) — elle ne fait pas autorité. Avertit si le
    produit n'apparaît dans aucun catalogue relevé (avec les 5 plus proches), ou si aucun
    catalogue n'a été observé du tout (`{}` instrumenté ≠ `None` ancien registre, comme F8).
    """
    if verified_fields is None:
        return []
    observes = [t for source, textes in verified_fields.items()
                if source.startswith(CATALOGUE_SOURCE_PREFIX) for t in textes]
    warnings: list[SmokeWarning] = []
    for numero, ligne in enumerate(feature_content.split("\n"), 1):
        for motif in _PRODUIT:
            m = motif.search(ligne)
            if not m:
                continue
            produit = m.group("p")
            if any(produit.lower() in t.lower() or (len(t) >= 4 and t.lower() in produit.lower())
                   for t in observes):
                break
            proches = ", ".join(f"« {p} »" for p in plus_proches(produit, observes))
            detail = (f"Éléments réellement observés les plus proches : {proches}." if observes
                      else "Aucune liste de produits n'a été observée pendant la génération.")
            warnings.append(SmokeWarning(
                kind="produit_non_observe", step=produit[:60], line=numero,
                message=(f"Le produit « {produit} » n'a jamais été observé sur l'application. "
                         f"{detail} Un produit s'observe (inspecte la page de la liste), il ne se "
                         f"devine pas.")))
            break
    return [w.as_dict() for w in warnings]


def check_menus_observes(feature_content: str, modele: dict) -> list[dict]:
    """Signale un chemin non mesuré, sans supposer la cartographie exhaustive."""
    menus = {str(entry.get("menu_path") or entry.get("menu", "")).strip()
             for entry in (modele.get("modeles_backoffice") or []) if entry.get("menu")}
    if not menus:
        return []

    def normaliser(menu):
        return tuple(part.strip().casefold() for part in menu.split("/") if part.strip())

    connus = {normaliser(menu) for menu in menus}
    motif = re.compile(r'^\s*(?:Quand|Et|Soit|Lorsque|Alors|Mais)\s+'
                       r'je navigue vers le menu Odoo "([^"]+)"\s*$', re.IGNORECASE)
    warnings = []
    for num, line in enumerate(feature_content.splitlines(), 1):
        match = motif.match(line)
        if not match:
            continue
        menu = match.group(1)
        chemin = normaliser(menu)
        # Les parents d'une feuille mesurée sont aussi des chemins connus.
        if chemin and any(c[:len(chemin)] == chemin for c in connus):
            continue
        warnings.append(SmokeWarning(
            kind="menu_non_observe", step=menu, line=num,
            message=(f"Le chemin « {menu} » n'est pas étayé par les menus mesurés le "
                     f"{modele.get('mesure_le', '?')}. Vérifie le chemin et la langue du "
                     "compte connecté ; ne traduis pas les libellés et n'invente pas de "
                     "sous-menu. La cartographie peut être incomplète ou ancienne.")).as_dict())
    return warnings


def smoke_check(feature_content: str, steps_content: str = "", modele: dict | None = None,
                verified_fields: dict[str, list[str]] | None = None) -> list[dict]:
    """Sans crawl, seules les inspections de la version peuvent étayer l'avis sur les champs.

    `None` désigne une version ancienne sans registre ; `{}` une génération instrumentée
    qui n'a observé aucun champ. Les confondre ferait taire une génération sans preuve.
    """
    menus = check_menus_observes(feature_content, modele or {})
    # §F8 : ne consulte ni `modele` ni le crawl, seulement `verified_fields` — s'applique donc
    # dans les DEUX branches, comme `check_step_soumission` pour la même raison structurelle.
    messages = (check_messages_observes(feature_content, verified_fields)
                + check_produits_observes(feature_content, verified_fields))
    if not modele or not modele.get("pages"):
        return menus + messages + (
            check_champs_existants(feature_content, modele or {}, verified_fields)
            if verified_fields is not None else [])
    return (menus + messages + check_valeurs_de_select(feature_content, modele)
            + check_champs_existants(feature_content, modele, verified_fields)
            + check_champs_requis_remplis(feature_content, modele)
            # Seul contrôle qui ne consulte PAS le modèle (il lit la structure du scénario) : il
            # reste sous le garde « pas de modèle ⇒ pas d'avis » pour que le gate ait un
            # comportement unique, jamais un demi-avis selon la présence de l'annuaire.
            + check_step_soumission(feature_content))
