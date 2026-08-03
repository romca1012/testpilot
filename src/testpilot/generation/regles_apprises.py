"""Les règles APPRISES d'un refus réel — ce que le crawl statique ne peut pas voir (§5bis n°1).

Le crawl ne lit que des attributs HTML. Une règle de validation écrite en **JavaScript**
(`setCustomValidity()`) lui est **structurellement invisible** : mesuré sur
`/fournisseur/creation`, le champ `tva_intracommunautaire` n'a **aucune** contrainte HTML, et le
navigateur le refuse pourtant — *« Le numéro de TVA doit contenir uniquement des chiffres. »*.
Enrichir le crawl ne corrigera jamais ça : c'est une limite de la méthode, pas de son
implémentation. **Prévenir ne peut pas être exhaustif ; détecter à l'exécution, si.**

Ce module porte donc ce que l'application a **refusé pour de vrai**, mesuré pendant un run.

⚠️ **Pourquoi un fichier SÉPARÉ de `data/domain/`, et non une extension de l'annuaire.**
L'annuaire est une **référence versionnée** dont la revue humaine sert à détecter une régression
applicative : *« un modèle qui change tout seul n'est pas une référence »* (voir `domain_model`).
Y écrire automatiquement aveuglerait ce détecteur. Ici, rien de tel : une liste de valeurs
refusées n'est la référence de rien — elle contraint **notre propre fabrication de données de
test**. Deux registres de vérité, deux cycles de vie, deux fichiers.

⚠️ **Pourquoi un fichier et non une table SQLite.** Le lecteur principal est le résolveur, qui
tourne **dans le sous-processus Behave** — un processus qui ne connaît pas la base. L'y faire
ouvrir SQLite prendrait un verrou de lecture pendant qu'un run écrit, sur plusieurs minutes et
sans WAL : « database is locked » intermittent, invisible en test, fatal en campagne.
Contrepartie assumée : deux campagnes **simultanées** sur un même projet ne sont pas garanties
(arbitrage du porteur, 2026-08-03 — les campagnes sont séquentielles).

⚠️ **Une règle apprise s'applique IMMÉDIATEMENT, et sa revue vient APRÈS** — en ouvrant le
fichier et en supprimant la ligne fautive (du JSONL, un fait par ligne, horodaté, portant son
`execution_id`). Le fichier est **gitignoré**, contrairement à l'annuaire : c'est une mesure
d'exécution propre à une instance, pas une référence relue avant adoption.
C'est tenable parce que la **direction de l'erreur est sûre**
(§4.4) : au pire, le résolveur produit une autre valeur, ou n'en trouve aucune et le verdict tombe
en `indetermine`. **Jamais une accusation contre l'application.** Exiger une revue préalable
reviendrait à ne pas livrer le mécanisme : une règle en attente de relecture se reproduit à chaque
rejeu — exactement le défaut qu'on corrige.

⚠️ **L'asymétrie est la vraie garde, pas la revue.** Une règle qui **INTERDIT** de répéter un
refus prouvé s'applique seule. Une règle qui **AFFIRME** une contrainte nouvelle ne descend dans
le résolveur que si le navigateur l'a **nommée** (`pattern`, `maxlength`…). `valueMissing` en est
exclu : « ce champ a été refusé vide » ne veut pas dire « ce champ est toujours obligatoire » —
un choix fait plus haut dans le formulaire peut le rendre requis. Le fait est enregistré et
remonté à l'agent ; il ne devient pas une contrainte.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from testpilot import config
from testpilot.generation import domain_model

logger = logging.getLogger(__name__)

REGLES_DIR = config.DATA_DIR / "regles-apprises"

FORMAT_VERSION = 1

# Plafond de lecture : le fichier est append-only, il grandit. Au-delà, les plus RÉCENTES priment
# (une application corrigée ne doit pas rester prisonnière de ses anciens refus).
_MAX_REGLES_LUES = 500

# Les drapeaux de `ValidityState` que le navigateur peut lever, plus les deux que notre
# bibliothèque pose elle-même. Une valeur hors de cette liste est un bug d'émission, pas une
# donnée : on la journalise et on la saute (voir `_depuis_json`).
TYPES_CONTRAINTE = frozenset({
    "valueMissing", "typeMismatch", "patternMismatch", "tooLong", "tooShort",
    "rangeUnderflow", "rangeOverflow", "stepMismatch", "badInput", "customError",
    "filtre_saisie", "refus_serveur",
})

ORIGINES = frozenset({"navigateur", "filtre_saisie", "serveur"})

# Ce qu'un type de contrainte permet de DÉDUIRE pour le résolveur. Absent de cette table =
# liste noire seulement (on interdit la valeur, on n'affirme aucune règle).
_CONTRAINTE_PAR_TYPE = {
    "patternMismatch": "pattern",
    "tooLong": "maxlength",
    "tooShort": "minlength",
    "rangeOverflow": "max",
    "rangeUnderflow": "min",
    "stepMismatch": "step",
    "filtre_saisie": "classe_conservee",
}


@dataclass(frozen=True)
class RegleApprise:
    """Un refus MESURÉ sur l'application réelle. Aucun champ n'est rédigé par un LLM."""

    route: str              # normalisée par `domain_model.normaliser_route`
    champ: str              # attribut HTML `name` — technique, jamais un libellé
    type_contrainte: str    # drapeau de `ValidityState`, ou `filtre_saisie` / `refus_serveur`
    valeur_contrainte: str  # `el.pattern`, `el.maxLength`… — vide si rien de lisible par machine
    valeur_refusee: str
    origine: str
    preuve: str = ""        # message du NAVIGATEUR ou de l'APPLICATION — informatif, jamais clé
    premiere_le: str = ""
    derniere_le: str = ""
    occurrences: int = 1

    def cle(self) -> tuple[str, str, str, str, str]:
        """L'identité d'une règle — **dérivée du runtime seul** (principe 1).

        `preuve` en est exclue **délibérément** : c'est un texte, et un texte change de casse, de
        ponctuation ou de langue sans que le fait change. L'y inclure ferait de deux mesures du
        même refus deux règles distinctes. Même raisonnement que `failure_signature`, qui refuse
        de se dériver du libellé écrit par l'agent.
        """
        return (self.route, self.champ, self.type_contrainte,
                self.valeur_contrainte, self.valeur_refusee)


def chemin(project_id: int) -> Path:
    """Un fichier PAR PROJET — même raison que l'annuaire (`0005`).

    Deux projets Odoo sont deux **applications** : une valeur refusée par l'une n'apprend rien
    sur l'autre.
    """
    return REGLES_DIR / f"projet-{int(project_id)}.jsonl"


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _texte(valeur, limite: int = 200) -> str:
    return ("" if valeur is None else str(valeur))[:limite]


def _depuis_json(brut: dict) -> RegleApprise | None:
    """Une ligne du fichier → une règle, ou `None` si elle est inexploitable.

    Tolérant par conception : le fichier est une trace, pas un contrat. Une ligne qu'on ne sait
    pas lire est **sautée et journalisée**, jamais une exception — le résolveur ne doit pas
    tomber parce qu'une écriture s'est mal passée il y a trois semaines.
    """
    route, champ = _texte(brut.get("route")), _texte(brut.get("champ"))
    type_contrainte = _texte(brut.get("type_contrainte"))
    if not route or not champ or type_contrainte not in TYPES_CONTRAINTE:
        return None
    return RegleApprise(
        route=route,
        champ=champ,
        type_contrainte=type_contrainte,
        valeur_contrainte=_texte(brut.get("valeur_contrainte")),
        valeur_refusee=_texte(brut.get("valeur_refusee")),
        origine=_texte(brut.get("origine")) or "navigateur",
        preuve=_texte(brut.get("preuve")),
        premiere_le=_texte(brut.get("mesure_le")),
        derniere_le=_texte(brut.get("mesure_le")),
        occurrences=1,
    )


def _fusionner_doublons(regles: list[RegleApprise]) -> list[RegleApprise]:
    """Deux mesures du même refus = UNE règle à deux occurrences.

    `occurrences` n'est **utilisé par aucune décision** aujourd'hui, et c'est voulu : inventer
    ici un seuil (« n'appliquer qu'après 2 fois ») serait la constante non mesurée que ce projet
    se reproche ailleurs. On l'enregistre pour pouvoir le calibrer plus tard, sur du réel.
    """
    par_cle: dict[tuple, RegleApprise] = {}
    for regle in regles:
        connue = par_cle.get(regle.cle())
        if connue is None:
            par_cle[regle.cle()] = regle
            continue
        par_cle[regle.cle()] = replace(
            connue,
            occurrences=connue.occurrences + 1,
            derniere_le=regle.derniere_le or connue.derniere_le,
            # La preuve la plus RÉCENTE prime : si l'application a reformulé son message, c'est
            # celui que l'utilisateur verra aujourd'hui.
            preuve=regle.preuve or connue.preuve,
        )
    return list(par_cle.values())


@lru_cache(maxsize=8)
def _lire(chemin_str: str, mtime: float) -> tuple[RegleApprise, ...]:
    """Cache indexé sur (chemin, mtime) — même motif que `domain_model._charger`.

    Sans le `mtime`, un run qui vient d'apprendre une règle ne la verrait pas au run suivant dans
    le même processus : « affiché ≠ réel » appliqué à un cache.
    """
    lignes = Path(chemin_str).read_text(encoding="utf-8").splitlines()
    regles: list[RegleApprise] = []
    for numero, ligne in enumerate(lignes[-_MAX_REGLES_LUES:], start=1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            regle = _depuis_json(json.loads(ligne))
        except (ValueError, TypeError, AttributeError):
            regle = None
        if regle is None:
            logger.warning("[règles apprises] %s ligne %d illisible — sautée", chemin_str, numero)
            continue
        regles.append(regle)
    return tuple(_fusionner_doublons(regles))


def charger(project_id: int | None) -> list[RegleApprise]:
    """Les règles apprises d'un projet. **Ne lève jamais** — aucune règle est un état normal.

    Doctrine de `read_field_fallbacks` : l'absence de fichier est le cas nominal (un projet qui
    n'a jamais essuyé de refus), pas une erreur.
    """
    if project_id is None:
        return []
    fichier = chemin(project_id)
    try:
        if not fichier.exists():
            return []
        return list(_lire(str(fichier), fichier.stat().st_mtime))
    except OSError:
        logger.exception("[règles apprises] %s illisible — le résolveur travaillera sans", fichier)
        return []


def enregistrer(project_id: int | None, refus, *, execution_id: int | None = None) -> int:
    """Ajoute des refus mesurés au fichier du projet. Rend le nombre de lignes écrites.

    **Best-effort, jamais fatal** : un disque plein ne doit pas faire tomber une exécution qui a
    créé de vraies données dans l'application testée (même arbitrage que l'archivage des
    artefacts). On journalise et on continue.

    `refus` accepte des `RegleApprise` ou des objets/dictionnaires portant les mêmes champs — le
    sous-processus Behave n'importe pas ce module (il ne connaît que la bibliothèque de steps).
    """
    if project_id is None or not refus:
        return 0
    lignes = []
    horodatage = _maintenant()
    for brut in refus:
        objet = _en_dict(brut)
        if objet is None:
            continue
        objet.update({"v": FORMAT_VERSION, "mesure_le": horodatage,
                      "execution_id": execution_id})
        lignes.append(json.dumps(objet, ensure_ascii=False, sort_keys=True))
    if not lignes:
        return 0
    fichier = chemin(project_id)
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with fichier.open("a", encoding="utf-8") as flux:
            flux.write("\n".join(lignes) + "\n")
    except OSError:
        logger.exception("[règles apprises] écriture impossible dans %s — les refus de ce run "
                         "sont perdus, le run lui-même reste valide", fichier)
        return 0
    return len(lignes)


def _en_dict(brut) -> dict | None:
    """Normalise une entrée (dataclass, objet, ou dict) en dictionnaire sérialisable."""
    lecture = brut.get if isinstance(brut, dict) else lambda nom, d=None: getattr(brut, nom, d)
    type_contrainte = _texte(lecture("type_contrainte"))
    route, champ = _texte(lecture("route")), _texte(lecture("champ"))
    if not route or not champ or type_contrainte not in TYPES_CONTRAINTE:
        logger.warning("[règles apprises] refus ignoré (route/champ/type invalides) : %r", brut)
        return None
    return {
        "route": route,
        "champ": champ,
        "type_contrainte": type_contrainte,
        "valeur_contrainte": _texte(lecture("valeur_contrainte")),
        "valeur_refusee": _texte(lecture("valeur_refusee")),
        "origine": _texte(lecture("origine")) or "navigateur",
        "preuve": _texte(lecture("preuve")),
    }


def pour_champ(regles, route: str, nom: str) -> list[RegleApprise]:
    """Les règles qui concernent ce champ, sur cette route.

    ⚠️ **Le rapprochement de route passe par `domain_model._meme_route`, jamais par l'égalité de
    chaînes.** La normalisation retire un préfixe de deux lettres qu'elle prend pour une langue :
    sur un portail Odoo, `/my/home` **sans** locale devient `/home`, alors que l'annuaire — mesuré
    depuis une URL localisée `/en/my/home` — a stocké `/my/home`. Une comparaison stricte
    perdrait la règle en silence. Le rapprochement par segments, lui, est celui que l'annuaire
    utilise déjà pour ses propres formulaires (voir `test_normalisation_route`).
    """
    if not regles or not nom:
        return []
    return [r for r in regles
            if r.champ == nom
            and (domain_model._meme_route(r.route, route)
                 or domain_model._meme_route(route, r.route))]


def valeurs_interdites(regles) -> list[str]:
    """Les valeurs que l'application a refusées — la partie NÉGATIVE, toujours applicable."""
    return sorted({r.valeur_refusee for r in regles if r.valeur_refusee})


def fusionner(champ: dict, regles) -> dict:
    """Le champ de l'annuaire, enrichi de ce que les refus ont appris. **Rend une COPIE.**

    Règle de fusion, en une phrase : *le crawl fait foi sur ce qu'il a MESURÉ ; l'appris ne
    remplit que les BLANCS, et n'écrase jamais* (`setdefault`, jamais d'assignation). Si le crawl
    a lu `pattern="\\d{7}"`, un refus ne peut pas le contredire — il ne peut que documenter un
    champ sur lequel le crawl n'avait rien.

    ⚠️ **La copie du sous-dictionnaire `contraintes` n'est PAS cosmétique.** `domain_model`
    sert ses modèles depuis un `lru_cache`, et `formulaires_requis` **partage** l'objet
    `contraintes` au lieu de le copier. Le muter ici empoisonnerait l'annuaire en mémoire pour
    tout le processus — un modèle qui change tout seul, exactement ce que l'invariant interdit.
    """
    fusionne = dict(champ or {})
    contraintes = dict(fusionne.get("contraintes") or {})
    regles = list(regles or [])

    for regle in regles:
        cle = _CONTRAINTE_PAR_TYPE.get(regle.type_contrainte)
        if cle and regle.valeur_contrainte:
            contraintes.setdefault(cle, regle.valeur_contrainte)
        # `customError` : le navigateur n'expose AUCUNE contrainte machine, seulement sa phrase.
        # C'est le cas `tva_intracommunautaire`. On la range là où le résolveur sait déjà lire
        # une règle en français — `regle_lisible` porte aujourd'hui l'attribut `title`, donc du
        # texte de l'APPLICATION. Le principe 1 interdit le texte de l'AGENT ; la borne est la
        # même, et la valeur produite reste re-vérifiée déterministiquement.
        elif regle.type_contrainte == "customError" and regle.preuve:
            contraintes.setdefault("regle_lisible", regle.preuve)

    fusionne["contraintes"] = contraintes
    interdites = valeurs_interdites(regles)
    if interdites:
        fusionne["valeurs_interdites"] = interdites
    return fusionne
