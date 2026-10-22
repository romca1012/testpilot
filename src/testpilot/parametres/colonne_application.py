"""Une colonne de données de test remplie avec des enregistrements qui EXISTENT dans l'application (étape 6 du plan unique,
IT-4, décision A55 : « plusieurs clients déjà en base »).

Pourquoi. Un cas « commander pour un client » se rejoue utilement sur plusieurs clients réels ; les recopier à la main dans le
tableau les fige au jour de la saisie (un client supprimé depuis casse le test sans rien dire). Ici, une variable peut
déclarer sa SOURCE dans l'application ; à chaque lancement, l'outil y relève les valeurs et en fait autant d'itérations, FIGÉES
avec le reste au lancement (A29) : relancer la campagne rejoue les mêmes.

Ce que la colonne n'est jamais : un résultat attendu. Une valeur relevée sert à PRÉPARER (le client à choisir) ; ce que le test
vérifie vient du cas validé (A39). Une valeur qui casserait le texte du test (`resolution.valider_valeur`) est écartée.

Décision du porteur EN ATTENTE (registre A105) : combien d'enregistrements, lesquels. Proposition codée ici et derrière
l'interrupteur `TESTPILOT_COLONNE_DEPUIS_L_APPLICATION` (éteint) : `NOMBRE_PAR_DEFAUT` = 3, les premiers dans l'ordre où
l'application les rend.

Deux temps (revue du 2026-10-22, deux défauts bloquants) : au LANCEMENT, les valeurs sont relevées et figées
(`colonnes_de_l_application` dans les valeurs figées) ; au moment de JOUER un cas, il n'est multiplié que si SON test emploie
la variable et qu'aucune de ses lignes ne la fixe (sinon trois clients seraient annoncés, un seul joué) — et jamais si la
variable est dans un « Alors » (le test comparerait l'application à elle-même).

Module pur : aucune I/O, aucun réseau, aucun LLM — la lecture de l'application est faite par l'appelant
(`api/services/colonnes_application_service.py`).
"""

from __future__ import annotations

import json
import re

from testpilot.parametres import resolution

NOMBRE_PAR_DEFAUT = 3      # A105, À VALIDER par le porteur
NOMBRE_MAX = 20            # au-delà, ce n'est plus « quelques clients réels » : un lancement par erreur
TYPE_ORACLE = "oracle"     # une requête GET de l'oracle déclaré du projet (tout connecteur)
TYPE_ODOO = "odoo"         # un modèle et un champ, lus par RPC (connecteur Odoo)
ORIGINE = "relevée dans l'application"   # l'origine d'une valeur relevée, montrée dans le rapport (revue : en clair)

_NOM_TECHNIQUE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,79}$")
_CHEMIN = re.compile(r"^[A-Za-z0-9_.\[\]]{0,200}$")


class SourceInvalide(ValueError):
    """La source déclarée ne peut pas être lue (forme, requête non déclarée, connecteur) — dit à la saisie."""


class ColonneImpossible(ValueError):
    """La colonne n'a pas pu être remplie au lancement (aucune valeur, trop d'itérations) — le lancement n'a pas lieu."""


def valider_source(source: dict | None, *, connector_type: str | None, requetes_declarees=()) -> dict:
    """La source normalisée — ou `SourceInvalide`. `{}` (ou `None`) : aucune source (la variable garde ses valeurs saisies)."""
    if not source:
        return {}
    if not isinstance(source, dict):
        raise SourceInvalide("la source d'une colonne est un objet")
    nombre = source.get("nombre", NOMBRE_PAR_DEFAUT)
    if not isinstance(nombre, int) or isinstance(nombre, bool) or not 1 <= nombre <= NOMBRE_MAX:
        raise SourceInvalide(f"le nombre d'enregistrements va de 1 à {NOMBRE_MAX}")
    type_ = str(source.get("type") or "")
    if type_ == TYPE_ORACLE:
        requete, chemin, cle = (str(source.get(k) or "").strip() for k in ("requete", "chemin", "cle"))
        if requete not in set(requetes_declarees or ()):
            raise SourceInvalide(f"la requête d'oracle « {requete} » n'est pas une requête de lecture (GET) déclarée dans les "
                                 "réglages du projet")
        if not _CHEMIN.match(chemin) or not cle or not _CHEMIN.match(cle):
            raise SourceInvalide("le chemin de la liste et la clé de chaque élément s'écrivent en points (`clients`, `nom`)")
        return {"type": TYPE_ORACLE, "requete": requete, "chemin": chemin, "cle": cle, "nombre": nombre}
    if type_ == TYPE_ODOO:
        if (connector_type or "").lower() != "odoo":
            raise SourceInvalide("une source Odoo ne vaut que pour une application Odoo")
        modele, champ = (str(source.get(k) or "").strip() for k in ("modele", "champ"))
        if not _NOM_TECHNIQUE.match(modele) or not _NOM_TECHNIQUE.match(champ):
            raise SourceInvalide("le modèle et le champ sont des noms techniques (`res.partner`, `name`)")
        return {"type": TYPE_ODOO, "modele": modele, "champ": champ, "nombre": nombre}
    raise SourceInvalide(f"source inconnue « {type_} » : « {TYPE_ORACLE} » ou « {TYPE_ODOO} »")


def lire_source(texte: str | None) -> dict:
    """La source enregistrée (`test_variable.source_application`) — `{}` si vide. Illisible : `ColonneImpossible` (revue :
    jamais un retour silencieux aux valeurs saisies, que la campagne annoncerait comme relevées)."""
    if not (texte or "").strip():
        return {}
    try:
        source = json.loads(texte)
    except ValueError as exc:
        raise ColonneImpossible("la source d'une colonne est illisible : redéclarez-la") from exc
    if not isinstance(source, dict):
        raise ColonneImpossible("la source d'une colonne est illisible : redéclarez-la")
    return source


def valeurs_retenues(brutes, nombre: int) -> list[str]:
    """Les valeurs relevées, dans l'ordre de l'application : textes et nombres seulement (un objet, une liste, un booléen ou
    une valeur vide ne désignent pas un enregistrement), sans doublon, sans valeur qui casserait le texte du test, au plus
    `nombre`."""
    retenues: list[str] = []
    for brute in brutes or []:
        if isinstance(brute, bool) or not isinstance(brute, (str, int, float)):
            continue
        texte = str(brute).strip()
        if not texte or texte in retenues:
            continue
        try:
            resolution.valider_valeur(texte)
        except resolution.ValeurInvalide:
            continue
        retenues.append(texte)
        if len(retenues) >= nombre:
            break
    return retenues


def valeurs_de_la_reponse(reponse, chemin: str, cle: str) -> list:
    """Les valeurs brutes d'une réponse d'oracle : la liste au `chemin` (vide : la réponse elle-même), la `cle` de chaque
    élément. Lève `ColonneImpossible` si la réponse n'a pas cette forme — jamais une valeur devinée."""
    from testpilot.connectors.oracle_http import champ

    try:
        liste = champ(reponse, chemin) if chemin else reponse
    except (KeyError, TypeError, IndexError) as exc:
        raise ColonneImpossible(f"la réponse de l'oracle n'a pas la liste « {chemin} » ({exc})") from exc
    if not isinstance(liste, list):
        raise ColonneImpossible(f"« {chemin or 'la réponse'} » n'est pas une liste dans la réponse de l'oracle")
    brutes = []
    for element in liste:
        try:
            brutes.append(champ(element, cle))
        except (KeyError, TypeError, IndexError):
            continue
    return brutes


def etendre_les_figes(figes: dict, colonnes: dict[str, list[str]], maximum: int) -> dict:
    """Les valeurs figées du lancement, une itération par valeur relevée de chaque colonne (produit avec les lignes déjà
    choisies). Lève `ColonneImpossible` pour une colonne sans aucune valeur ou au-delà de `maximum` itérations."""
    if not colonnes:
        return figes
    bases = figes["jeux"] if isinstance(figes.get("jeux"), list) else [
        {"jeu": figes.get("jeu") or "", "dataset_id": figes.get("dataset_id"), "valeurs": figes.get("valeurs") or {}}]
    for nom, valeurs in colonnes.items():
        if not valeurs:
            raise ColonneImpossible(f"la colonne « {nom} » n'a trouvé aucun enregistrement dans l'application")
        etendues = []
        for base in bases:
            for valeur in valeurs:
                etendues.append({**base, "jeu": f"{base.get('jeu') or 'Par défaut'} · {nom} : {valeur}",
                                 "valeurs": {**(base.get("valeurs") or {}), nom: {"valeur": valeur, "origine": ORIGINE}}})
        bases = etendues
        if len(bases) > maximum:
            raise ColonneImpossible(f"{len(bases)} itérations avec les enregistrements de l'application, {maximum} au plus "
                                    "— réduisez le nombre d'enregistrements ou les lignes choisies")
    return {**figes, "jeu": figes.get("jeu") or "", "jeux": bases}


def colonnes_a_jouer(figes: dict, feature: str, fixees_par_les_lignes) -> dict[str, list[str]]:
    """Les colonnes relevées au lancement que CE test emploie (`{{nom}}` dans son texte) et qu'aucune ligne du cas ne fixe."""
    colonnes = figes.get("colonnes_de_l_application") if isinstance(figes.get("colonnes_de_l_application"), dict) else {}
    employees = set(resolution.references(feature or ""))
    return {nom: [str(v) for v in valeurs] for nom, valeurs in colonnes.items()
            if nom in employees and nom not in set(fixees_par_les_lignes or ()) and isinstance(valeurs, list)}
