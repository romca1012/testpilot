"""Données de test — résoudre la valeur d'une variable et la poser dans le texte d'un test (lot PT-02, décisions A26 à A29).

Un test écrit `{{nom}}` là où une valeur change d'une situation à l'autre. Au LANCEMENT d'une exécution, ce module :

1. retient pour chaque variable la valeur du niveau le plus précis qui en donne une (`resoudre`) — aujourd'hui deux niveaux,
   la colonne « Par défaut » puis le jeu de données choisi (A27 : une case vide reprend « Par défaut ») ; la bibliothèque
   commune (PT-05) et la campagne s'ajouteront devant et derrière sans changer la règle ;
2. remplace chaque `{{nom}}` du texte du test par cette valeur (`remplacer`), et dit ce qu'il n'a PAS pu remplacer : une
   variable inconnue ou sans valeur n'est jamais laissée telle quelle dans le texte — l'appelant ne lance pas l'exécution.

Ce que ce module garantit :
- un texte sans `{{…}}` ressort IDENTIQUE, octet pour octet ;
- un seul passage : une valeur qui contient elle-même `{{autre}}` n'est pas relue ;
- seule une écriture `{{nom}}` au nom bien formé est une variable ; « 10 % », `{x}` (un paramètre de step) ou `<x>` (un
  plan de scénario) ne sont jamais concernés.

Module PUR : aucune I/O, aucun LLM. Les valeurs sont déclarées par des personnes ; l'agent ne connaît que les noms (PT-02d).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from behave.i18n import languages as _LANGUES_GHERKIN

NOM_MAX = 40
VALEUR_MAX = 500
# Un nom : des lettres minuscules (accents admis), des chiffres, « _ » ; il commence par une lettre. Pas d'espace ni de
# majuscule : `{{Ville}}` désigne « ville » (la casse d'une référence est pliée), et deux variables ne diffèrent jamais par
# la seule casse.
_NOM = re.compile(r"[a-zà-öø-ÿ][a-zà-öø-ÿ0-9_]*")
# Une RÉFÉRENCE dans un texte : `{{` nom `}}`, espaces tolérés autour du nom, sur une seule ligne. Tout ce qui se trouve
# entre doubles accolades est une référence — bien formée ou non : une écriture ratée (« {{nom client}} ») doit se voir,
# pas partir telle quelle dans l'application.
_REFERENCE = re.compile(r"\{\{([^{}\r\n]*)\}\}")
# Les mots qui ouvrent une ÉTAPE (Soit, Quand, Alors, Et… ; Given, When, Then, And…), lus dans le dictionnaire de Behave
# lui-même, en français et en anglais. Une variable ne s'écrit que DANS une étape (après son mot-clé), dans une cellule de
# tableau ou dans un bloc de texte : posée dans une étiquette (`@{{x}}`), un commentaire, un titre ou à la place du mot-clé,
# sa valeur changerait la STRUCTURE du test (revue du 2026-10-14, mesuré : une valeur « # Alors » faisait disparaître
# l'étape, « Quand » changeait son type, `@{{x}}` valant « skip » ajoutait une étiquette, un titre changeait de nom).
_MOTS_D_ETAPE = tuple(sorted({mot for langue in ("fr", "en") for genre in ("given", "when", "then", "and", "but")
                              for mot in _LANGUES_GHERKIN[langue][genre]}, key=len, reverse=True))
_BLOC_DE_TEXTE = ('"""', "```")


class NomInvalide(ValueError):
    """Le nom d'une variable n'est pas utilisable (vide, trop long, majuscule, espace…). Le message dit pourquoi."""


class ValeurInvalide(ValueError):
    """Une valeur ne peut pas être posée dans le texte d'un test sans le casser. Le message dit pourquoi."""


def valider_nom(nom: str | None) -> str:
    """Le nom d'une variable, normalisé (espaces des bords retirés, minuscules) — ou `NomInvalide`."""
    propre = (nom or "").strip().lower()
    if not propre:
        raise NomInvalide("le nom de la variable est requis")
    if len(propre) > NOM_MAX:
        raise NomInvalide(f"le nom d'une variable ne dépasse pas {NOM_MAX} caractères")
    if not _NOM.fullmatch(propre):
        raise NomInvalide(f"« {(nom or '').strip()} » : un nom de variable commence par une lettre et ne contient que des "
                          "lettres minuscules, des chiffres et « _ » (pas d'espace)")
    return propre


def valider_valeur(valeur: str | None) -> str:
    """Une valeur telle qu'elle sera posée dans le texte du test — ou `ValeurInvalide`.

    Le texte d'un test est du Gherkin : une valeur y arrive presque toujours entre guillemets (`"{{client}}"`) ou dans une
    cellule de tableau. Un guillemet double fermerait le paramètre, une barre verticale couperait la cellule, un retour à
    la ligne couperait l'étape — le test jouerait alors AUTRE CHOSE que ce qui est écrit, sans le dire. Refusés à la
    saisie, plutôt qu'échappés en devinant le contexte."""
    texte = "" if valeur is None else str(valeur)
    if len(texte) > VALEUR_MAX:
        raise ValeurInvalide(f"une valeur ne dépasse pas {VALEUR_MAX} caractères")
    # Behave découpe le texte du test avec `splitlines()` : « \u2028 », « \x85 » coupent une étape comme un retour à la ligne.
    # Un caractère INVISIBLE (catégories Cf, Zl, Zp, Cc) ferait d'une case qui paraît vide une case qui n'hérite pas du jeu
    # « Par défaut », et serait saisi tel quel dans l'application (revue du 2026-10-14).
    if len(texte.splitlines()) > 1 or any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") and c != "\t" for c in texte):
        raise ValeurInvalide("une valeur tient sur une seule ligne, sans caractère invisible")
    for interdit, nom in (('"', "guillemet double"), ("|", "barre verticale"), ("{{", "double accolade"), ("}}", "double accolade")):
        if interdit in texte:
            raise ValeurInvalide(f"une valeur ne contient pas de {nom} (« {interdit} ») : elle casserait le texte du test")
    # « <produit> » dans un plan de scénario : Behave le remplacerait par la colonne des exemples du même nom.
    if re.search(r"<[^<>]+>", texte):
        raise ValeurInvalide("une valeur ne contient pas « <…> » : dans un plan de scénario, Behave le remplacerait")
    return texte.strip()


def references(texte: str | None) -> list[str]:
    """Les noms référencés par `texte`, dans l'ordre de première apparition, sans doublon. Une référence mal formée
    (« {{nom client}} », « {{}} ») y figure telle qu'elle est écrite, accolades comprises : elle sera dite inconnue."""
    vues: dict[str, None] = {}
    for trouve in _REFERENCE.finditer(texte or ""):
        vues.setdefault(_nom_reference(trouve), None)
    return list(vues)


def places_des_lignes(lignes):
    """(ligne, place) pour chaque ligne : « delimiteur » (ouvre ou ferme un bloc de texte), « bloc » (dedans) ou « hors ».
    Seul le délimiteur qui a OUVERT le bloc le ferme, comme pour Behave : un « ``` » dans un bloc « \"\"\" » en fait partie
    (revue du 2026-10-15 : basculer sur n'importe quel délimiteur prenait le texte d'un bloc pour des lignes d'étape)."""
    bloc = None
    for ligne in lignes:
        propre = ligne.strip()
        if bloc is not None:
            if propre.startswith(bloc):
                bloc = None
                yield ligne, "delimiteur"
            else:
                yield ligne, "bloc"
            continue
        ouvrant = next((d for d in _BLOC_DE_TEXTE if propre.startswith(d)), None)
        if ouvrant:
            bloc = ouvrant
            yield ligne, "delimiteur"
        else:
            yield ligne, "hors"


def _mal_placees_ou_mal_ecrites(texte: str) -> list[str]:
    """Les lignes où une variable est mal écrite ou mal placée — rendues telles quelles (60 caractères) pour être dites.

    Mal écrite : il reste « {{ » une fois les références bien formées retirées (« {{client} », « {{ {{client}} }} »,
    « {{\nclient}} »), ou une accolade colle à une référence (« {{{client}}} », « {{client}}} »). Revue du 2026-10-14 :
    ces écritures passaient pour du texte, le test se jouait sans la valeur annoncée. « }} » seul (la fin d'un JSON) ne
    compte pas. Mal placée : hors d'une étape (après son mot-clé), d'une cellule de tableau ou d'un bloc de texte."""
    fautives: list[str] = []
    for ligne, place in places_des_lignes(texte.splitlines()):
        if place == "delimiteur":
            continue
        propre = ligne.strip()
        dans_un_bloc = place == "bloc"
        trouvees = list(_REFERENCE.finditer(ligne))
        mal_ecrite = "{{" in _REFERENCE.sub("", ligne) or any(
            (t.start() > 0 and ligne[t.start() - 1] == "{") or (t.end() < len(ligne) and ligne[t.end()] == "}") for t in trouvees)
        bien_placee = dans_un_bloc or propre.startswith("|") or (
            propre.startswith(_MOTS_D_ETAPE) and not any(t.start() < len(ligne) - len(ligne.lstrip()) +
                                                         _longueur_du_mot_cle(propre) for t in trouvees))
        if mal_ecrite or (trouvees and not bien_placee):
            fautives.append(propre[:60])
    return fautives


def _longueur_du_mot_cle(propre: str) -> int:
    return next(len(mot) for mot in _MOTS_D_ETAPE if propre.startswith(mot))


def _nom_reference(trouve: re.Match) -> str:
    nom = trouve.group(1).strip().lower()
    return nom if _NOM.fullmatch(nom) else trouve.group(0)


@dataclass(frozen=True)
class Valeur:
    valeur: str
    origine: str   # le nom du niveau qui a fourni la valeur (« Par défaut », le nom du jeu…)


def resoudre(niveaux: Sequence[tuple[str, Mapping[str, str | None]]], noms: Iterable[str] | None = None) -> dict[str, Valeur]:
    """La valeur retenue pour chaque variable, avec le niveau qui l'a fournie.

    `niveaux` : du plus général au plus précis — `[("Par défaut", {...}), ("Grosse commande", {...})]`. Le plus précis
    l'emporte ; une valeur absente, `None` ou vide (espaces seuls) à un niveau laisse la main au niveau plus général (A27).
    `noms` : les variables à résoudre (toutes celles que les niveaux citent, sinon). Une variable sans valeur à AUCUN niveau
    n'est pas dans le résultat : l'appelant la traite comme « sans valeur »."""
    voulus = list(dict.fromkeys(noms)) if noms is not None else list(dict.fromkeys(n for _, valeurs in niveaux for n in valeurs))
    retenues: dict[str, Valeur] = {}
    for nom in voulus:
        for origine, valeurs in reversed(niveaux):
            valeur = valeurs.get(nom)
            if valeur is not None and str(valeur).strip():
                retenues[nom] = Valeur(str(valeur).strip(), origine)
                break
    return retenues


@dataclass(frozen=True)
class Remplacement:
    texte: str                                             # le texte, chaque référence RÉSOLUE remplacée
    jouees: dict[str, Valeur] = field(default_factory=dict)  # ce qui a réellement été posé dans le texte
    inconnues: tuple[str, ...] = ()                        # références qui ne désignent aucune variable connue
    sans_valeur: tuple[str, ...] = ()                      # variables connues, sans valeur à aucun niveau

    @property
    def complet(self) -> bool:
        """Vrai si TOUTES les références ont été remplacées : le texte peut être joué."""
        return not self.inconnues and not self.sans_valeur


def remplacer(texte: str | None, valeurs: Mapping[str, Valeur], connues: Iterable[str]) -> Remplacement:
    """Pose les valeurs dans `texte`. `connues` : les noms des variables du projet (pour distinguer « inconnue » de « sans
    valeur »). Une référence non résolue est LAISSÉE dans le texte rendu — qui ne doit alors pas être joué (`complet`)."""
    source = texte or ""
    connues = set(connues)
    jouees: dict[str, Valeur] = {}
    inconnues: dict[str, None] = {}
    sans_valeur: dict[str, None] = {}

    def poser(trouve: re.Match) -> str:
        nom = _nom_reference(trouve)
        if nom in valeurs:
            jouees[nom] = valeurs[nom]
            return valeurs[nom].valeur
        (sans_valeur if nom in connues else inconnues).setdefault(nom, None)
        return trouve.group(0)

    rendu = _REFERENCE.sub(poser, source)
    for fautive in _mal_placees_ou_mal_ecrites(source):
        inconnues.setdefault(f"variable mal écrite ou mal placée : « {fautive} »", None)
    return Remplacement(rendu, jouees, tuple(inconnues), tuple(sans_valeur))
