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


def check_champs_existants(feature_content: str, modele: dict) -> list[dict]:
    """Les champs référencés existent-ils quelque part ? — le motif `0007`.

    ⚠️ Union sur TOUT le domaine, comme les selects : on ne signale que l'introuvable **partout**.
    Un champ qui n'existe nulle part est une invention ; un champ existant ailleurs peut être une
    erreur de page (`0020`) — mais ça, ce module ne peut pas le trancher, et il ne prétend pas le
    faire.
    """
    connus = _index_champs(modele)
    if not connus:
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
                     f"cf. 0007). (modèle mesuré le {date})")))
    return [w.as_dict() for w in warnings]


def smoke_check(feature_content: str, steps_content: str = "", modele: dict | None = None
                ) -> list[dict]:
    """Tous les contrôles. Rend `[]` si aucun modèle : **pas de modèle ⇒ aucun avis**.

    ⚠️ Silence volontaire sans modèle, et il faut le dire : un module qui « ne trouve rien » parce
    qu'il n'a **rien à quoi comparer** ressemble à un module qui **valide**. C'est le motif que ce
    projet traque (« l'absence de signal prise pour un signal positif »). L'appelant doit donc
    savoir si un modèle existe — il ne peut pas le déduire d'une liste vide.
    """
    if not modele or not modele.get("pages"):
        return []
    return (check_valeurs_de_select(feature_content, modele)
            + check_champs_existants(feature_content, modele))
