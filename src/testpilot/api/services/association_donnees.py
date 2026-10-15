"""Associer d'un clic un test DÉJÀ ÉCRIT aux données de test du projet (plan, chapitre 9, étape E1 ; décision A39).

Un test écrit avant les données de test saisit des valeurs en dur : « Martin SARL ». L'outil propose de les remplacer par la
variable dont c'est la valeur dans le jeu « Par défaut » (`{{client}}`) ; la personne coche, une nouvelle version est créée, à
relire comme toute modification. Aucune IA : la STRUCTURE des étapes (motifs de la bibliothèque, appariés comme Behave les
apparie) décide, jamais leur texte.

Ce qui empêche un faux vert (revues du 2026-10-15 : des faux verts reproduits sur les deux premières versions) :
1. **Tout ou rien, par variable.** Une variable n'est proposée que si CHAQUE occurrence de sa valeur dans les lignes
   exécutables est remplaçable, ET si la valeur n'y apparaît sous AUCUNE autre forme (casse, accents, espaces, un de ses mots,
   un morceau) : « Alors la page n'affiche pas le texte "Martin" » laissé en dur, avec un autre jeu, vérifierait l'absence
   d'un client jamais touché.
2. **Seulement là où l'étape attend une DONNÉE** : un paramètre de `VALEURS_D_ETAPES`, dans une étape de la bibliothèque
   reconnue comme Behave la reconnaît (accents pliés, casse respectée, type de l'étape — « Et »/« Mais »
   héritent du précédent). Jamais un nom de champ, un libellé, un sélecteur, une adresse ; jamais une étape écrite à la main,
   un bloc de texte, une cellule de tableau (la colonne peut porter un nom de champ ; dans un plan de scénario, elle alimente
   des étapes qu'on ne voit pas d'ici) : la valeur y rend la variable non proposable. Un nombre n'est remplacé que s'il est
   le paramètre entier.
3. Une valeur partagée par deux variables, ou présente sous une forme ou une autre dans le code Python des étapes (que le
   remplacement ne touche jamais), n'est pas proposée.
4. Une proposition qui touche une VÉRIFICATION (étape « then », ou ligne de type « Alors ») est signalée (`verification`) ;
   elle reste ouverte aux testeurs comme les autres — décision A40 du porteur, 2026-10-15 : la nouvelle version est à relire.

Contrôle de cohérence avant d'écrire : joué avec le jeu « Par défaut », le test associé redonne exactement le test d'origine.
Il ne rattrape qu'une erreur de remplacement — l'équivalence avec un AUTRE jeu, ce sont les règles 1 et 2 qui la portent.

Pur, hors la lecture des valeurs du projet et du catalogue d'étapes.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tokenize
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

import parse as parse_lib

from testpilot.parametres import resolution

# Les (étape, paramètre) de la bibliothèque qui portent une DONNÉE — relevé du catalogue un par un, 2026-10-15. Tout autre
# paramètre désigne un élément de l'application (champ, libellé, sélecteur, adresse, requête…) ou un code technique (l'état
# « posted » d'un document) : il n'est jamais remplacé. Liste fermée : une étape nouvelle n'y entre pas d'office, un test
# (`tests/test_association_donnees.py`) oblige à la classer.
VALEURS_D_ETAPES = frozenset({
    ('aucun enregistrement en double avec le champ "{field}" égal à "{value}" n\'existe dans le modèle "{model}"', "value"),
    ('dans le cadre "{nom_du_cadre}", je renseigne le champ "{field}" avec la valeur "{value}"', "value"),
    ('je clique sur "{libelle}" dans la ligne contenant "{texte}"', "texte"),
    ('je filtre la liste "{menu}" par "{texte}"', "texte"),
    ('je renseigne "{champ}" avec "{valeur}" dans la ligne contenant "{texte}"', "texte"),
    ('je renseigne "{champ}" avec "{valeur}" dans la ligne contenant "{texte}"', "valeur"),
    ('je renseigne la relation "{champ}" avec "{valeur}"', "valeur"),
    ('je renseigne le champ "{field}" avec la valeur "{value}"', "value"),
    ('je renseigne le champ "{field}" avec la valeur "{value}" rendue unique pour cette tentative', "value"),
    ('je sélectionne "{value}" dans le champ "{field}"', "value"),
    ('je sélectionne le produit dans la liste contenant "{partial}"', "partial"),
    ('la liste "{chemin}" de l\'oracle "{requete}" contient un élément dont "{cle}" est "{valeur}"', "valeur"),
    ('la page affiche le texte "{texte}"', "texte"),
    ('la page n\'affiche pas le texte "{texte}"', "texte"),
    ('la valeur affichée pour "{libelle}" est "{valeur}"', "valeur"),
    ('le champ "{chemin}" de l\'oracle "{requete}" vaut "{valeur}"', "valeur"),
    ('le champ "{field}" de cet enregistrement contient le nom "{partial}"', "partial"),
    ('le champ "{field}" de cet enregistrement est égal à "{expected}"', "expected"),
    ('le champ "{field}" de cet enregistrement dans le modèle "{model}" est égal à "{expected}"', "expected"),
    ('le champ "{field}" de cet enregistrement dans le modèle "{model}" pointe vers "{expected}"', "expected"),
    ('le fichier téléchargé contient "{texte}"', "texte"),
    ('le nombre affiché pour "{libelle}" vaut "{valeur}"', "valeur"),
    ('le tableau "{nom}" contient une ligne avec "{a}" et "{b}"', "a"),
    ('le tableau "{nom}" contient une ligne avec "{a}" et "{b}"', "b"),
    ('un enregistrement avec le champ "{field}" égal à "{value}" existe dans le modèle "{model}"', "value"),
    ('un enregistrement avec {field} contenant "{value}" existe dans le modèle "{model}"', "value"),
})
_VARIABLE_ECRITE = re.compile(r"\{\{[^{}\r\n]*\}\}")
# Un nombre écrit, groupes de milliers et décimales compris (« 1 234,50 », « 1'234.50 »).
_NOMBRE = re.compile(r"\d[\d   '’.,]*\d|\d")

# Le pliage du moteur d'étapes du runtime (`behave_runtime/steps_library/_accent_matcher.py`) : accents précomposés → base,
# un caractère pour un (les positions restent alignées). Recopié, le serveur n'important pas `behave_runtime` ; un test
# vérifie que les deux tables sont identiques.
_ACCENTUEES = "àáâãäåçèéêëìíîïñòóôõöùúûüýÿÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ"
PLIAGE = str.maketrans({c: unicodedata.normalize("NFD", c)[0] for c in _ACCENTUEES})

# Le TYPE de chaque mot qui ouvre une étape, lu dans le dictionnaire de Behave (fr, en). « * » est de tous les types : la
# ligne n'est pas reconnue (prudence). « and »/« but » : le type de l'étape précédente.
_TYPE_DU_MOT: dict[str, str] = {}
for _langue in ("fr", "en"):
    for _genre in ("given", "when", "then", "and", "but"):
        for _mot in resolution._LANGUES_GHERKIN[_langue][_genre]:
            if _mot.strip() != "*":
                _TYPE_DU_MOT[_mot] = "suite" if _genre in ("and", "but") else _genre


# Les mots qui ouvrent un scénario, un contexte, des exemples… (dictionnaire de Behave, fr et en), suivis de « : ».
_TITRES = tuple(sorted({f"{mot}:" for _langue in ("fr", "en")
                        for _genre in ("feature", "background", "scenario", "scenario_outline", "examples", "rule")
                        for mot in resolution._LANGUES_GHERKIN[_langue].get(_genre, [])}, key=len, reverse=True))


class AssociationImpossible(ValueError):
    """Le résultat ne rejouerait pas le test d'origine, ou une proposition n'existe plus : rien n'est écrit."""


@dataclass(frozen=True)
class MotifDEtape:
    motif: object        # parse.Parser, sur le libellé PLIÉ, casse respectée — comme le moteur du runtime
    type: str            # given | when | then | step
    verification: bool   # étape « then »
    libelle: str = ""


def motifs_du_catalogue(projet: dict) -> list[MotifDEtape]:
    from testpilot.generation import steps_library

    motifs = []
    for s in steps_library.catalogue(connector_type=projet.get("connector_type"),
                                     profil_instance=projet.get("profil_instance")):
        try:
            motif = parse_lib.compile(s.label.translate(PLIAGE), case_sensitive=True)
        except (ValueError, IndexError):
            continue
        motifs.append(MotifDEtape(motif, s.keyword, s.keyword == "then", s.label))
    return motifs


def valeurs_par_defaut(conn, project_id: int) -> tuple[dict[str, str], list[str]]:
    """({nom: valeur} du jeu « Par défaut », les variables sans valeur exclues ; tous les noms des variables du projet)."""
    from testpilot.store.repositories import TestDataRepo

    noms, niveaux = TestDataRepo(conn).niveaux(project_id)
    return {nom: v.valeur for nom, v in resolution.resoudre(niveaux, noms).items() if v.valeur}, list(noms)


def valeurs_de_tous_les_jeux(conn, project_id: int) -> list[str]:
    """Toutes les valeurs saisies, dans tous les jeux : « Martin » n'est pas remplacé dans « Martin SARL » même si « Martin SARL »
    n'existe que dans un autre jeu que « Par défaut » (revue A41, 2e passe)."""
    from testpilot.store.repositories import TestDataRepo

    tableau = TestDataRepo(conn).tableau(project_id)
    return list(dict.fromkeys(v for par_jeu in (tableau.get("valeurs") or {}).values() for v in par_jeu.values() if v))


def _motif(valeur: str) -> re.Pattern:
    debut = r"(?<!\w)" if valeur[:1].isalnum() else ""
    fin = r"(?!\w)" if valeur[-1:].isalnum() else ""
    return re.compile(f"{debut}{re.escape(valeur)}{fin}")


def _occurrences(texte: str, valeur: str) -> list[tuple[int, int]]:
    """Les occurrences EXACTES en mot entier, hors d'une variable déjà écrite (`{{client}}` n'est jamais réécrit)."""
    deja = [(m.start(), m.end()) for m in _VARIABLE_ECRITE.finditer(texte)]
    return [(m.start(), m.end()) for m in _motif(valeur).finditer(texte)
            if not any(d <= m.start() < f for d, f in deja)]


def _lache(texte: str) -> str:
    """Pour chercher une valeur SOUS UNE AUTRE FORME : sans accents, sans casse, espaces réduits."""
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sans_accents.casefold())


def _sous_une_autre_forme(texte: str, valeur: str) -> bool:
    """La valeur apparaît-elle dans `texte`, même autrement écrite ? Un texte : la valeur entière comme morceau, ou un de ses
    mots (dès 3 caractères, ou un sigle en majuscules). Un nombre : ses chiffres non collés à d'autres, ou le même nombre
    autrement écrit. `texte` a déjà ses places remplacées et ses variables retirées."""
    # Le même NOMBRE autrement écrit (« 1 234,50 € » pour « 1234.50 », ou « 1234.50 EUR » : A24 fait écrire l'unité) : une
    # étape qui compare des nombres l'y lirait. Les unités ne sont pas converties (1,5 kg et 1500 g) : écarter trop est sans
    # danger. Revue, 4e passe.
    lues = set().union(*(_lectures(n) for n in _NOMBRE.findall(valeur)))
    if lues and any(lues & _lectures(n) for n in _NOMBRE.findall(texte)):
        return True
    if not any(c.isalpha() for c in valeur):
        chiffres = re.sub(r"\s", "", valeur)
        return bool(chiffres) and re.search(rf"(?<!\d){re.escape(chiffres)}(?!\d)", re.sub(r"\s", "", texte)) is not None
    lache, cherchee = _lache(texte), _lache(valeur).strip()
    if cherchee and cherchee in lache:
        return True
    # Un DÉBUT d'un de ses mots, dès 4 lettres (« Martin » vérifié pour « Martinez ») : une troncature.
    debuts = {d for d in re.findall(r"\w{4,}", lache) if not d.isdigit()}
    if any(m != d and m.startswith(d) for m in re.findall(r"\w+", cherchee) for d in debuts):
        return True
    # Un de ses mots, dès 3 caractères (« BNP » de « BNP Paribas », « Bon » de « Le Bon Coin ») ; un sigle plus court
    # (« SA »), en majuscules seulement. Écarter trop ne coûte qu'une proposition ; trop peu, un vert sans preuve (revue,
    # 3e passe : « Alors la page n'affiche pas le texte "BNP" » restait en dur).
    mots = re.findall(r"\w+", valeur)
    if len(mots) < 2:
        return False
    longs = {_lache(m) for m in mots if len(m) >= 3}
    sigles = {m for m in mots if len(m) >= 2 and m.isupper()}
    return (any(re.search(rf"(?<!\w){re.escape(m)}(?!\w)", lache) for m in longs)
            or any(re.search(rf"(?<!\w){re.escape(m)}(?!\w)", texte) for m in sigles))


def _lectures(ecrit: str) -> set[Decimal]:
    """Les valeurs possibles d'un nombre écrit : « 1,234 » se lit mille deux cent trente-quatre OU un virgule deux cent
    trente-quatre — on ne devine pas, on retient les deux."""
    brut = re.sub(r"[\s'’]", "", ecrit)
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", brut):
        return set()
    sans_separateur = Decimal(re.sub(r"[.,]", "", brut))
    dernier = max(brut.rfind("."), brut.rfind(","))
    if dernier < 0:
        return {sans_separateur}
    return {sans_separateur, Decimal(re.sub(r"[.,]", "", brut[:dernier]) + "." + brut[dernier + 1:])}


def _chaines_du_code(code: str) -> list[str] | None:
    """Les chaînes de texte du code Python des étapes (sur plusieurs lignes et f-strings comprises) : un mot de la valeur n'est
    cherché que là (« "Martin " + "SARL" ») — dans les instructions, « import » de « Durand Import » écartait la variable de
    tous les tests (mesuré sur la copie locale). `None` si le code ne se découpe pas : on cherche alors partout."""
    genres = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
    try:
        return [j.string for j in tokenize.generate_tokens(io.StringIO(code).readline) if j.type in genres]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None


def _dans_le_code(code: str, valeur: str) -> bool:
    chaines = _chaines_du_code(code)
    if chaines is None:
        return _sous_une_autre_forme(code, valeur)
    return _contenue(valeur, code) or any(_sous_une_autre_forme(c, valeur) for c in chaines)


def _contenue(courte: str, longue: str) -> bool:
    """`courte` est-elle un morceau de `longue` (sans casse ni accents ; un nombre, non collé à d'autres chiffres) ?"""
    if not any(c.isalpha() for c in courte):
        chiffres = re.sub(r"\s", "", courte)
        return bool(chiffres) and re.search(rf"(?<!\d){re.escape(chiffres)}(?!\d)", re.sub(r"\s", "", longue)) is not None
    return _lache(courte).strip() in _lache(longue)


def _identifiant(nom: str, valeur: str) -> str:
    return f"{nom}:{hashlib.sha256(valeur.encode('utf-8')).hexdigest()[:10]}"


@dataclass
class _Ligne:
    numero: int
    texte: str
    genre: str            # "etape" | "tableau" | "bloc" | "autre"
    spans: tuple = ()     # étape reconnue : (début, fin) des paramètres de valeur, dans la ligne
    reconnue: bool = False
    verification: bool = False


def _reconnaitre(corps: str, type_effectif: str | None, motifs: list[MotifDEtape]) -> tuple[bool, bool, tuple]:
    """(reconnue, vérification, spans des paramètres de valeur, relatifs au corps) — comme Behave : texte plié, casse
    respectée, motifs du type de l'étape et ceux de tout type. Plusieurs motifs qui ne s'accordent pas : non reconnue."""
    if type_effectif is None:
        return False, False, ()
    plie = corps.translate(PLIAGE)
    trouves = set()
    for m in motifs:
        if m.type not in (type_effectif, "step"):
            continue
        try:
            trouve = m.motif.parse(plie)
        except (ValueError, IndexError):
            continue
        if trouve is not None:
            spans = tuple(sorted(sp for nom, sp in trouve.spans.items() if (m.libelle, nom) in VALEURS_D_ETAPES))
            trouves.add((spans, type_effectif == "then" or m.verification))
    if len({s for s, _ in trouves}) != 1:
        return False, False, ()
    return True, any(v for _, v in trouves), next(iter(trouves))[0]


def _analyser(feature: str, motifs: list[MotifDEtape]) -> list[_Ligne]:
    lignes, type_precedent = [], None
    parcours = resolution.places_des_lignes((feature or "").split("\n"))
    for numero, (texte, place) in enumerate(parcours, start=1):
        propre = texte.strip()
        if place != "hors":   # un bloc de texte et ses délimiteurs : seul celui qui l'ouvre le ferme (comme Behave)
            lignes.append(_Ligne(numero, texte, "bloc"))
            continue
        if propre.startswith("|"):
            lignes.append(_Ligne(numero, texte, "tableau"))
            continue
        if propre.startswith(resolution._MOTS_D_ETAPE):
            mot = next(m for m in resolution._MOTS_D_ETAPE if propre.startswith(m))
            genre = _TYPE_DU_MOT.get(mot)
            type_effectif = type_precedent if genre == "suite" else genre
            type_precedent = type_effectif
            debut = len(texte) - len(texte.lstrip()) + len(mot)
            corps = texte[debut:]
            debut += len(corps) - len(corps.lstrip())
            reconnue, verification, spans = _reconnaitre(corps.strip(), type_effectif, motifs)
            lignes.append(_Ligne(numero, texte, "etape", tuple((debut + d, debut + f) for d, f in spans), reconnue,
                                 verification))
            continue
        if propre.startswith(_TITRES) or propre.startswith("@"):
            type_precedent = None   # nouveau scénario, contexte, exemples : « Et » n'hérite plus de rien
        lignes.append(_Ligne(numero, texte, "autre"))   # titre, description, commentaire, étiquette : non exécuté
    return lignes


def _remplacements(ligne: _Ligne, valeur: str) -> list[tuple[int, int]] | None:
    """Les places à remplacer dans CETTE ligne, ou `None` si une occurrence n'est pas remplaçable (variable écartée)."""
    trouvees = _occurrences(ligne.texte, valeur)
    if not trouvees or ligne.genre == "autre":
        return []
    if ligne.genre != "etape" or not ligne.reconnue:
        return None
    numerique = not any(c.isalpha() for c in valeur)
    for d, f in trouvees:
        span = next(((a, b) for a, b in ligne.spans if a <= d and f <= b), None)
        if span is None:
            return None
        if ligne.texte[span[0]:span[1]] != valeur and (numerique or len(valeur) < 3):
            return None
    return trouvees


def _reste(texte: str, places: list[tuple[int, int]]) -> str:
    """La ligne sans ses places remplacées ni ses variables déjà écrites : ce qui y resterait EN DUR."""
    for d, f in sorted(places, reverse=True):
        texte = texte[:d] + "\x00" + texte[f:]
    return _VARIABLE_ECRITE.sub("\x00", texte)


def metier_de_la_version(version: dict | None) -> dict:
    """Le texte du cas d'une version : {preconditions, steps (liste), expected_result, etapes_lisibles}. Des étapes qui ne sont
    pas une liste JSON de textes (texte simple, que l'écran découpe par lignes ; vide) : `etapes_lisibles` faux, elles ne
    sont ni proposées ni réécrites (revue A41 : réécrites « [] », elles disparaissaient)."""
    version = version or {}
    try:
        etapes = json.loads(version.get("test_steps") or "")
    except (TypeError, ValueError):
        etapes = None
    lisibles = isinstance(etapes, list) and all(isinstance(e, str) for e in etapes)
    return {"preconditions": str(version.get("preconditions") or ""), "steps": list(etapes) if lisibles else [],
            "expected_result": str(version.get("expected_result") or ""), "etapes_lisibles": lisibles}


def _textes_du_cas(metier: dict) -> list[tuple[tuple, str, str]]:
    """((clé), libellé lisible, texte) pour chaque texte du cas — le titre n'en est pas : il nomme le cas."""
    textes = [(("preconditions",), "Préconditions", metier.get("preconditions") or "")]
    if metier.get("etapes_lisibles", True):
        textes += [(("steps", i), f"Étape {i + 1}", e) for i, e in enumerate(metier.get("steps") or [])]
    textes.append((("expected_result",), "Résultat attendu", metier.get("expected_result") or ""))
    return textes


def _dans_le_cas(metier: dict | None, valeur: str, nom: str, autres=()) -> list[dict]:
    """Décision A41 (porteur, 2026-10-15) : la valeur est aussi remplacée dans le TEXTE du cas, là où elle y est écrite, pour
    que le cas et le test restent d'accord (E2 : le test technique reprend les variables que le cas cite). Texte lu par des
    personnes, jamais exécuté : chaque occurrence exacte en mot entier, SAUF (revue A41) :
    - une valeur de moins de 3 caractères, ou un nombre (« 100 articles à 100 EUR » : la quantité ou le prix ?) ;
    - une occurrence à l'intérieur de la valeur d'une AUTRE variable (`autres`) : « Martin » dans « Martin SARL ».
    Le cas ne cite alors pas la variable ; la régénération admet celles que le test emploie déjà (A41)."""
    if not metier or len(valeur) < 3 or not any(c.isalpha() for c in valeur):
        return []
    sortie = []
    for cle, libelle, texte in _textes_du_cas(metier):
        englobees = [(d, f) for autre in autres if autre != valeur and valeur in autre for d, f in _occurrences(texte, autre)]
        places = [(d, f) for d, f in _occurrences(texte, valeur) if not any(a <= d and f <= b for a, b in englobees)]
        if places:
            sortie.append({"champ": libelle, "cle": list(cle), "avant": texte, "apres": _poser(texte, places, nom)})
    return sortie


def cas_associe(metier: dict | None, retenues: list[dict], valeurs: dict[str, str] | None = None,
                autres_valeurs=()) -> dict | None:
    """Ce qui change dans le texte du cas après l'association des `retenues` (les plus longues valeurs d'abord) : SEULEMENT
    les champs modifiés (`preconditions`, `steps`, `expected_result`), ou `None` si rien ne change."""
    if not metier:
        return None
    autres = [*(valeurs or {}).values(), *autres_valeurs]
    nouveau = {"preconditions": metier.get("preconditions") or "", "steps": list(metier.get("steps") or []),
               "expected_result": metier.get("expected_result") or "", "etapes_lisibles": metier.get("etapes_lisibles", True)}
    for p in sorted(retenues, key=lambda p: len(p["valeur"]), reverse=True):
        for change in _dans_le_cas(nouveau, p["valeur"], p["variable"], autres):
            cle = change["cle"]
            if cle[0] == "steps":
                nouveau["steps"][cle[1]] = change["apres"]
            else:
                nouveau[cle[0]] = change["apres"]
    changes = {k: nouveau[k] for k in ("preconditions", "steps", "expected_result")
               if nouveau[k] != (metier.get(k) or ([] if k == "steps" else ""))}
    return changes or None


def propositions(feature: str, steps_content: str, valeurs: dict[str, str], motifs: list[MotifDEtape],
                 metier: dict | None = None, autres_valeurs=()) -> dict:
    """{"propositions": [{id, variable, valeur, verification, lignes: [{ligne, avant, apres}],
    lignes_du_cas: [{champ, cle, avant, apres}]}], "ecartees": [...]}. `metier` : le texte du cas (A41)."""
    par_valeur: dict[str, list[str]] = {}
    for nom, valeur in valeurs.items():
        par_valeur.setdefault(valeur, []).append(nom)
    lignes = _analyser(feature, motifs)
    code = _VARIABLE_ECRITE.sub(" ", steps_content or "")   # un octet nul ferait refuser le découpage du code
    executable = "\n".join(_VARIABLE_ECRITE.sub("\x00", l.texte) for l in lignes if l.genre != "autre")
    sortie, ecartees = [], []
    for valeur, noms in par_valeur.items():
        if len(noms) > 1:
            ecartees += [{"variable": n, "valeur": valeur, "raison": "valeur partagée par plusieurs variables"} for n in noms]
            continue
        nom = noms[0]
        if _dans_le_code(code, valeur):
            ecartees.append({"variable": nom, "valeur": valeur, "raison": "aussi écrite dans le code des étapes"})
            continue
        # « Martin » (prénom) dans « Martin SARL » (client) écrit dans le test : quelle variable ? Jamais deviné — la plus
        # courte n'est pas proposée (revue du 2026-10-15 : les deux l'étaient, et le clic par défaut échouait toujours).
        englobante = next((n for v, ns in par_valeur.items() for n in ns if v != valeur
                           and _contenue(valeur, v) and _contenue(v, executable)), None)
        if englobante:
            ecartees.append({"variable": nom, "valeur": valeur,
                             "raison": "contenue dans la valeur de {{" + englobante + "}}, écrite dans le test"})
            continue
        touchees, verification, raison, places_de = [], False, None, {}
        for ligne in lignes:
            places = _remplacements(ligne, valeur)
            if places is None:
                raison = "écrite aussi à une place où elle ne peut pas être remplacée"
                break
            if ligne.genre != "autre" and _sous_une_autre_forme(_reste(ligne.texte, places), valeur):
                raison = "écrite aussi sous une autre forme"
                break
            if places:
                places_de[ligne.numero] = places
                apres = _poser(ligne.texte, places, nom)
                touchees.append({"ligne": ligne.numero, "avant": ligne.texte.strip(), "apres": apres.strip()})
                verification = verification or ligne.verification
        if raison:
            ecartees.append({"variable": nom, "valeur": valeur, "raison": raison})
        elif touchees:
            sortie.append({"id": _identifiant(nom, valeur), "variable": nom, "valeur": valeur,
                           "verification": verification, "lignes": touchees, "_places": places_de,
                           "lignes_du_cas": _dans_le_cas(metier, valeur, nom, [*valeurs.values(), *autres_valeurs])})
    # Deux valeurs qui se CHEVAUCHENT dans le test (« Martin SARL » et « SARL Lyon » dans « Martin SARL Lyon ») : appliquer
    # l'une détruit l'autre. La plus courte n'est pas proposée (à égalité : aucune) — revue du 2026-10-15, 3e passe.
    retirees = set()
    for p in sortie:
        for q in sortie:
            if p is q or not any(a < f2 and a2 < f for n, places in p["_places"].items()
                                 for a, f in places for a2, f2 in q["_places"].get(n, [])):
                continue
            if len(p["valeur"]) <= len(q["valeur"]):
                retirees.add(p["variable"])
                ecartees.append({"variable": p["variable"], "valeur": p["valeur"],
                                 "raison": "chevauche la valeur de {{" + q["variable"] + "}} dans le test"})
                break
    sortie = [{k: v for k, v in p.items() if k != "_places"} for p in sortie if p["variable"] not in retirees]
    return {"propositions": sortie, "ecartees": ecartees}


def _poser(texte: str, places: list[tuple[int, int]], nom: str) -> str:
    for d, f in sorted(places, reverse=True):
        texte = texte[:d] + "{{" + nom + "}}" + texte[f:]
    return texte


def appliquer(feature: str, steps_content: str, valeurs: dict[str, str], noms: list[str], motifs: list[MotifDEtape],
              choix: list[str]) -> tuple[str, list[dict]]:
    """(texte associé, propositions appliquées). Lève `AssociationImpossible` si un choix n'est pas une proposition du texte
    actuel, s'il resterait une valeur associée en dur (sous quelque forme que ce soit), ou si le résultat, joué avec le jeu
    « Par défaut », ne redonne pas exactement le test d'origine joué de même."""
    offertes = {p["id"]: p for p in propositions(feature, steps_content, valeurs, motifs)["propositions"]}
    if not choix or any(c not in offertes for c in choix):
        raise AssociationImpossible("ces propositions ne correspondent plus au test : rechargez-le")
    retenues = [offertes[c] for c in dict.fromkeys(choix)]
    associe = feature or ""
    for p in sorted(retenues, key=lambda p: len(p["valeur"]), reverse=True):
        analysees = _analyser(associe, motifs)   # relu en entier : chaque ligne garde son contexte
        lignes = associe.split("\n")
        for touchee in p["lignes"]:
            places = _remplacements(analysees[touchee["ligne"] - 1], p["valeur"])
            if not places:
                raise AssociationImpossible("ces propositions ne correspondent plus au test : rechargez-le")
            lignes[touchee["ligne"] - 1] = _poser(lignes[touchee["ligne"] - 1], places, p["variable"])
        associe = "\n".join(lignes)
    for p in retenues:   # tout ou rien : plus rien de la valeur en dur, sous aucune forme
        if any(_sous_une_autre_forme(_reste(l.texte, []), p["valeur"]) for l in _analyser(associe, motifs)
               if l.genre != "autre"):
            raise AssociationImpossible("une valeur associée resterait écrite en dur dans le test : rien n'est écrit")
    poses = {n: resolution.Valeur(v, "Par défaut") for n, v in valeurs.items()}
    avant, apres = resolution.remplacer(feature, poses, noms), resolution.remplacer(associe, poses, noms)
    # Une variable déjà écrite et sans valeur reste non résolue des DEUX côtés : comparé tel quel (elle bloquera le
    # lancement comme avant) ; rien d'autre ne doit différer.
    if (avant.texte, avant.inconnues, sorted(avant.sans_valeur)) != (apres.texte, apres.inconnues, sorted(apres.sans_valeur)):
        raise AssociationImpossible("le test associé ne rejouerait pas exactement le test d'origine : rien n'est écrit")
    return associe, retenues
