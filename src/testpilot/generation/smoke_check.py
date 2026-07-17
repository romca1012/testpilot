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

# Le Gherkin des cas générés cible les champs par ces tournures (mesuré sur les 3 cas réels) :
#     Et le champ demande "types_demandes" est rempli avec "new"
#     Et le champ "name" est rempli avec "..."
_CHAMP_VALEUR_RE = re.compile(
    r'champ\s+(?:demande\s+)?"(?P<champ>[^"]+)"\s+est\s+rempli\s+avec\s+"(?P<valeur>[^"]*)"',
    re.IGNORECASE)


@dataclass
class SmokeWarning:
    """Même forme que `LintWarning` (`0008`) : le gate affiche les deux dans le même bandeau."""

    kind: str
    subject: str
    message: str
    line: int = 0

    def as_dict(self) -> dict:
        return {"kind": self.kind, "subject": self.subject, "message": self.message,
                "line": self.line, "source": "smoke_check"}


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
        m = _CHAMP_VALEUR_RE.search(ligne)
        if not m:
            continue
        champ, valeur = m.group("champ"), m.group("valeur")
        connues = selects.get(champ)
        if connues is None:
            continue                      # pas un select connu : rien à dire (cf. docstring)
        if valeur in connues:
            continue
        apercu = ", ".join(sorted(v for v in connues if v)[:6])
        warnings.append(SmokeWarning(
            kind="valeur_option_inexistante", subject=champ, line=num,
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
        m = _CHAMP_VALEUR_RE.search(ligne)
        if not m:
            continue
        champ = m.group("champ")
        if champ in connus:
            continue
        warnings.append(SmokeWarning(
            kind="champ_inconnu", subject=champ, line=num,
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
