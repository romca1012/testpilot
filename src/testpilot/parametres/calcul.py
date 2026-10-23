"""Le calculateur des valeurs attendues (étape 7 du plan unique, décisions A108 et A110 du porteur, 2026-10-23).

Pourquoi. Un test qui vérifie un total recopie aujourd'hui le chiffre écrit dans la spécification : un chiffre faux dans la
spec passe en silence, et rien ne vérifie un calcul que l'IA ferait elle-même. Ici, la valeur attendue est CALCULÉE par du
code, à partir d'une **fiche de calcul** propre au projet : les éléments du calcul (chacun avec sa source), des étapes
simples lisibles par quelqu'un qui n'est pas développeur (D40, amendée par A110 : l'IA peut les proposer, une personne
choisit), et des exemples chiffrés que la fiche doit retrouver exactement avant d'être utilisée.

On ne sait jamais à l'avance ce qu'un test devra calculer (A108) : pas de liste de calculs métier figée, seulement des
opérations élémentaires qui se combinent (additionner, multiplier, pourcentage, arrondir, plafonner, barème, condition…).

Module PUR : aucune I/O, aucun réseau, aucun LLM. Tout est en `Decimal` (jamais de flottant : 0,1 + 0,2 doit valoir 0,3).

Forme d'une fiche (dictionnaire, stocké en JSON) :

    {"nom": "Total commande", "resultat": "total", "unite": "EUR",
     "elements": [{"nom": "quantite", "source": "variable {{quantite}}"},
                  {"nom": "taux_tva", "valeur": "20", "source": "CGI art. 278", "verifie_le": "2026-10-23"}],
     "etapes": [{"resultat": "ht", "operation": "multiplier", "termes": ["quantite", "prix"]},
                {"resultat": "total", "operation": "arrondir", "valeur": "ht", "decimales": 2}],
     "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "30"}]}

Un élément SANS `valeur` est une entrée, fournie à chaque calcul (une donnée de test, une saisie du test) ; un élément AVEC
`valeur` est une constante (un taux, un plafond) qui porte sa source et sa date de vérification (V8, A110 : rien d'autre).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)

ETAPES_MAX = 50          # au-delà, ce n'est plus un calcul qu'une personne relit : une fiche à scinder
TRANCHES_MAX = 30
_NOM = re.compile(r"^[a-z_][a-z0-9_]{0,59}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Les arrondis qu'une règle de gestion emploie, nommés comme une personne les dit — jamais un mode implicite : « arrondir à
# 2 décimales » sans dire comment donne 0,125 → 0,12 ou 0,13 selon l'outil, et le test serait faux une fois sur deux.
MODES_ARRONDI = {
    "au_plus_proche": ROUND_HALF_UP,          # 0,125 → 0,13 (l'arrondi « commercial »)
    "au_plus_proche_pair": ROUND_HALF_EVEN,   # 0,125 → 0,12 (l'arrondi « du banquier »)
    "inferieur": ROUND_FLOOR,
    "superieur": ROUND_CEILING,
    "tronquer": ROUND_DOWN,
}
COMPARATEURS = ("<", "<=", ">", ">=", "=", "!=")
OPERATIONS = ("additionner", "soustraire", "multiplier", "diviser", "pourcentage", "arrondir", "plafonner", "plancher",
              "minimum", "maximum", "bareme", "si")


class FicheInvalide(ValueError):
    """La fiche ne peut pas être utilisée telle quelle — le message dit quoi corriger, en clair."""


class CalculImpossible(ValueError):
    """Le calcul n'a pas pu aboutir avec ces entrées (une entrée manque ou n'est pas un nombre, une division par zéro).
    Jamais un résultat de repli : sans résultat, le test ne conclut pas."""


@dataclass(frozen=True)
class Calcul:
    """Le résultat et son DÉTAIL, une ligne par étape — montré à la relecture et dans le rapport."""
    resultat: Decimal
    unite: str
    detail: list[str] = field(default_factory=list)
    valeurs: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class EcartExemple:
    numero: int            # 1 = le premier exemple de la fiche
    attendu: str
    obtenu: str            # le résultat calculé, ou la raison pour laquelle il n'a pas pu l'être


def _nombre(texte, ou: str) -> Decimal:
    """Un nombre écrit par une personne ou par l'IA : « 12,5 » et « 12.5 » se lisent pareil ; rien d'autre n'est deviné
    (« 1 234,5 » oui, « 1,234.5 » non : deux séparateurs différents, la fiche le dit au lieu de choisir)."""
    if isinstance(texte, bool) or texte is None:
        raise FicheInvalide(f"{ou} : un nombre est attendu")
    if isinstance(texte, (int, Decimal)):
        return Decimal(texte)
    brut = str(texte).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    if brut.count(",") + brut.count(".") > 1 or not re.fullmatch(r"[-+]?\d+([.,]\d+)?", brut):
        raise FicheInvalide(f"{ou} : « {texte} » n'est pas un nombre (écrire par exemple 12,5)")
    return Decimal(brut.replace(",", "."))


def _ecrire(n: Decimal) -> str:
    """Un nombre tel qu'une personne le lit dans le détail : virgule décimale, aucun exposant."""
    texte = format(n, "f")
    return texte.replace(".", ",")


def valider_fiche(fiche, *, proposition: bool = False) -> dict:
    """La fiche normalisée, ou `FicheInvalide` avec ce qu'il faut corriger. Vérifie la FORME seulement — les exemples sont
    vérifiés par `verifier_exemples`, car une fiche bien formée peut calculer faux.

    `proposition=True` : une PROPOSITION de l'IA, présentée à une personne. L'IA n'a rien vérifié et ne calcule rien : elle
    ne date jamais un taux, et n'invente pas d'exemple quand la spécification n'en donne pas (un exemple qu'elle calculerait
    avec sa propre formule ne prouverait rien). Ces manques sont admis dans une proposition et dits dans `a_confirmer` ; une
    fiche n'est RETENUE qu'avec ses dates et au moins un exemple (`proposition=False`)."""
    if not isinstance(fiche, dict):
        raise FicheInvalide("une fiche de calcul est un objet")
    nom_fiche = str(fiche.get("nom") or "").strip()
    if not nom_fiche:
        raise FicheInvalide("la fiche n'a pas de nom")
    connus: set[str] = set()
    elements = []
    for i, element in enumerate(fiche.get("elements") or [], start=1):
        if not isinstance(element, dict):
            raise FicheInvalide(f"élément {i} : un objet est attendu")
        nom = str(element.get("nom") or "")
        if not _NOM.match(nom):
            raise FicheInvalide(f"élément {i} : « {nom} » n'est pas un nom (minuscules, chiffres et _ ; ex. taux_tva)")
        if nom in connus:
            raise FicheInvalide(f"élément « {nom} » déclaré deux fois")
        source = str(element.get("source") or "").strip()
        if not source:
            # A108 : un élément sans source est une QUESTION à une personne, jamais une hypothèse de la fiche.
            raise FicheInvalide(f"élément « {nom} » : sa source manque (d'où vient-il ?)")
        normal = {"nom": nom, "source": source}
        if element.get("valeur") not in (None, ""):
            normal["valeur"] = _ecrire(_nombre(element["valeur"], f"élément « {nom} »"))
            verifie = str(element.get("verifie_le") or "").strip()
            if not _DATE.match(verifie) and (not proposition or verifie):
                # V8 (A110) : une constante (un taux, un plafond) indique sa source ET sa date de vérification.
                raise FicheInvalide(f"élément « {nom} » : sa date de vérification manque (AAAA-MM-JJ)")
            normal["verifie_le"] = verifie
        if element.get("unite"):
            normal["unite"] = str(element["unite"]).strip()
        connus.add(nom)
        elements.append(normal)
    if not elements:
        raise FicheInvalide("la fiche ne déclare aucun élément")

    etapes_brutes = fiche.get("etapes") or []
    if not isinstance(etapes_brutes, list) or not etapes_brutes:
        raise FicheInvalide("la fiche n'a aucune étape de calcul")
    if len(etapes_brutes) > ETAPES_MAX:
        raise FicheInvalide(f"{len(etapes_brutes)} étapes : {ETAPES_MAX} au plus — scinder la fiche")
    etapes = [_valider_etape(e, i, connus) for i, e in enumerate(etapes_brutes, start=1)]

    resultat = str(fiche.get("resultat") or "")
    if resultat not in {e["resultat"] for e in etapes}:
        raise FicheInvalide(f"le résultat « {resultat} » n'est produit par aucune étape")
    exemples = []
    for i, exemple in enumerate(fiche.get("exemples") or [], start=1):
        if not isinstance(exemple, dict) or not isinstance(exemple.get("entrees", {}), dict):
            raise FicheInvalide(f"exemple {i} : des entrées et un résultat attendu sont attendus")
        exemples.append({"entrees": {str(k): _ecrire(_nombre(v, f"exemple {i}, « {k} »"))
                                     for k, v in (exemple.get("entrees") or {}).items()},
                         "attendu": _ecrire(_nombre(exemple.get("attendu"), f"exemple {i}, résultat attendu"))})
    if not exemples and not proposition:
        # A110 : une fiche qui ne retrouve pas d'exemple n'est jamais utilisée — sans exemple, rien ne le prouve.
        raise FicheInvalide("la fiche n'a aucun exemple chiffré à retrouver (ex. 3 articles à 10 € → 30)")
    normale = {"nom": nom_fiche, "resultat": resultat, "unite": str(fiche.get("unite") or "").strip(),
               "elements": elements, "etapes": etapes, "exemples": exemples}
    # Les points qu'une personne doit trancher avant de choisir la fiche (un arrondi que la spécification ne précise pas,
    # un exemple à fournir) — montrés à l'écran, jamais lus pour calculer.
    a_confirmer = [str(p).strip()[:300] for p in (fiche.get("a_confirmer") or []) if str(p or "").strip()][:10]
    if a_confirmer:
        normale["a_confirmer"] = a_confirmer
    return normale


def _reference(terme, ou: str, connus: set[str]) -> str:
    """Un terme d'une étape : le nom d'un élément ou d'un résultat PRÉCÉDENT, ou un nombre écrit tel quel."""
    texte = str(terme).strip() if terme is not None and not isinstance(terme, bool) else ""
    if _NOM.match(texte):
        if texte not in connus:
            raise FicheInvalide(f"{ou} : « {texte} » n'est ni un élément ni le résultat d'une étape précédente")
        return texte
    return _ecrire(_nombre(terme, ou))


def _valider_etape(etape, i: int, connus: set[str]) -> dict:
    if not isinstance(etape, dict):
        raise FicheInvalide(f"étape {i} : un objet est attendu")
    operation = str(etape.get("operation") or "")
    if operation not in OPERATIONS:
        raise FicheInvalide(f"étape {i} : opération « {operation} » inconnue ({', '.join(OPERATIONS)})")
    ou = f"étape {i} ({operation})"
    sortie = {"operation": operation}
    if operation in ("additionner", "soustraire", "multiplier", "minimum", "maximum"):
        termes = etape.get("termes")
        if not isinstance(termes, list) or len(termes) < 2:
            raise FicheInvalide(f"{ou} : au moins deux termes")
        sortie["termes"] = [_reference(t, ou, connus) for t in termes]
    elif operation == "diviser":
        sortie["valeur"] = _reference(etape.get("valeur"), ou, connus)
        sortie["par"] = _reference(etape.get("par"), ou, connus)
    elif operation == "pourcentage":
        sortie["de"] = _reference(etape.get("de"), ou, connus)
        sortie["taux"] = _reference(etape.get("taux"), ou, connus)
    elif operation == "arrondir":
        sortie["valeur"] = _reference(etape.get("valeur"), ou, connus)
        decimales = etape.get("decimales")
        if not isinstance(decimales, int) or isinstance(decimales, bool) or not 0 <= decimales <= 10:
            raise FicheInvalide(f"{ou} : le nombre de décimales va de 0 à 10")
        mode = str(etape.get("mode") or "")
        if mode not in MODES_ARRONDI:
            raise FicheInvalide(f"{ou} : dire comment arrondir ({', '.join(MODES_ARRONDI)})")
        sortie.update(decimales=decimales, mode=mode)
    elif operation in ("plafonner", "plancher"):
        sortie["valeur"] = _reference(etape.get("valeur"), ou, connus)
        sortie["limite"] = _reference(etape.get("limite"), ou, connus)
    elif operation == "bareme":
        sortie["valeur"] = _reference(etape.get("valeur"), ou, connus)
        mode = str(etape.get("mode") or "")
        if mode not in ("progressif", "par_palier"):
            # Les deux lectures d'un barème donnent des résultats différents : jamais choisie à la place de la fiche.
            raise FicheInvalide(f"{ou} : dire si le barème est « progressif » (chaque tranche à son taux) ou "
                                "« par_palier » (tout le montant au taux de sa tranche)")
        tranches = etape.get("tranches")
        if not isinstance(tranches, list) or not 1 <= len(tranches) <= TRANCHES_MAX:
            raise FicheInvalide(f"{ou} : de 1 à {TRANCHES_MAX} tranches")
        normales, precedente = [], None
        for j, tranche in enumerate(tranches, start=1):
            if not isinstance(tranche, dict):
                raise FicheInvalide(f"{ou}, tranche {j} : un objet est attendu")
            borne = tranche.get("jusqu_a")
            borne = None if borne in (None, "") else _nombre(borne, f"{ou}, tranche {j}")
            if borne is None and j != len(tranches):
                raise FicheInvalide(f"{ou} : seule la dernière tranche peut être sans limite")
            if borne is not None and precedente is not None and borne <= precedente:
                raise FicheInvalide(f"{ou} : les tranches vont en croissant")
            normales.append({"jusqu_a": None if borne is None else _ecrire(borne),
                             "taux": _reference(tranche.get("taux"), f"{ou}, tranche {j}", connus)})
            precedente = borne if borne is not None else precedente
        sortie.update(mode=mode, tranches=normales)
    elif operation == "si":
        condition = etape.get("condition") or {}
        if not isinstance(condition, dict) or condition.get("comparateur") not in COMPARATEURS:
            raise FicheInvalide(f"{ou} : une condition « gauche comparateur droite » ({' '.join(COMPARATEURS)})")
        sortie["condition"] = {"gauche": _reference(condition.get("gauche"), ou, connus),
                               "comparateur": condition["comparateur"],
                               "droite": _reference(condition.get("droite"), ou, connus)}
        sortie["alors"] = _reference(etape.get("alors"), ou, connus)
        sortie["sinon"] = _reference(etape.get("sinon"), ou, connus)
    resultat = str(etape.get("resultat") or "")
    if not _NOM.match(resultat):
        raise FicheInvalide(f"étape {i} : le résultat doit porter un nom (ex. total_ht)")
    if resultat in connus:
        raise FicheInvalide(f"étape {i} : « {resultat} » est déjà un élément ou un résultat")
    connus.add(resultat)
    sortie["resultat"] = resultat
    return sortie


def calculer(fiche: dict, entrees: dict) -> Calcul:
    """Applique la fiche VALIDÉE (`valider_fiche`) aux `entrees` (nom → nombre). Lève `CalculImpossible` si une entrée
    manque ou n'est pas un nombre, ou sur une division par zéro — jamais un résultat approché ou de repli."""
    valeurs: dict[str, Decimal] = {}
    detail: list[str] = []
    for element in fiche["elements"]:
        nom = element["nom"]
        if "valeur" in element:
            valeurs[nom] = Decimal(element["valeur"].replace(",", "."))
            verifie = f", vérifié le {element['verifie_le']}" if element.get("verifie_le") else ", date de vérification à remplir"
            detail.append(f"{nom} = {element['valeur']} (source : {element['source']}{verifie})")
            continue
        if nom not in entrees:
            raise CalculImpossible(f"l'entrée « {nom} » manque")
        try:
            valeurs[nom] = _nombre(entrees[nom], f"entrée « {nom} »")
        except FicheInvalide as exc:
            raise CalculImpossible(str(exc)) from exc
        detail.append(f"{nom} = {_ecrire(valeurs[nom])} (source : {element['source']})")

    def v(terme: str) -> Decimal:
        return valeurs[terme] if _NOM.match(terme) else Decimal(terme.replace(",", "."))

    with localcontext() as ctx:
        ctx.prec = 50   # aucune perte avant l'arrondi DÉCLARÉ par la fiche ; c'est lui seul qui décide des décimales
        for etape in fiche["etapes"]:
            op, nom = etape["operation"], etape["resultat"]
            if op == "additionner":
                r = sum((v(t) for t in etape["termes"]), Decimal(0))
                lu = " + ".join(etape["termes"])
            elif op == "soustraire":
                premier, *reste = [v(t) for t in etape["termes"]]
                r = premier - sum(reste, Decimal(0))
                lu = " − ".join(etape["termes"])
            elif op == "multiplier":
                r = Decimal(1)
                for t in etape["termes"]:
                    r *= v(t)
                lu = " × ".join(etape["termes"])
            elif op == "diviser":
                if v(etape["par"]) == 0:
                    raise CalculImpossible(f"« {nom} » : division par zéro ({etape['par']} vaut 0)")
                r = v(etape["valeur"]) / v(etape["par"])
                lu = f"{etape['valeur']} ÷ {etape['par']}"
            elif op == "pourcentage":
                r = v(etape["de"]) * v(etape["taux"]) / Decimal(100)
                lu = f"{etape['taux']} % de {etape['de']}"
            elif op == "arrondir":
                r = v(etape["valeur"]).quantize(Decimal(1).scaleb(-etape["decimales"]),
                                                rounding=MODES_ARRONDI[etape["mode"]])
                lu = f"{etape['valeur']} arrondi à {etape['decimales']} décimale(s), {etape['mode'].replace('_', ' ')}"
            elif op == "plafonner":
                r = min(v(etape["valeur"]), v(etape["limite"]))
                lu = f"{etape['valeur']} plafonné à {etape['limite']}"
            elif op == "plancher":
                r = max(v(etape["valeur"]), v(etape["limite"]))
                lu = f"{etape['valeur']} au moins {etape['limite']}"
            elif op == "minimum":
                r = min(v(t) for t in etape["termes"])
                lu = "le plus petit de " + ", ".join(etape["termes"])
            elif op == "maximum":
                r = max(v(t) for t in etape["termes"])
                lu = "le plus grand de " + ", ".join(etape["termes"])
            elif op == "bareme":
                r = _bareme(v(etape["valeur"]), etape, v)
                lu = f"barème {etape['mode'].replace('_', ' ')} appliqué à {etape['valeur']}"
            else:  # si
                c = etape["condition"]
                vrai = _comparer(v(c["gauche"]), c["comparateur"], v(c["droite"]))
                r = v(etape["alors"] if vrai else etape["sinon"])
                lu = (f"si {c['gauche']} {c['comparateur']} {c['droite']} ({'oui' if vrai else 'non'}) "
                      f"alors {etape['alors']} sinon {etape['sinon']}")
            valeurs[nom] = r
            detail.append(f"{nom} = {lu} = {_ecrire(r)}")
    return Calcul(resultat=valeurs[fiche["resultat"]], unite=fiche["unite"], detail=detail, valeurs=valeurs)


def _comparer(a: Decimal, comparateur: str, b: Decimal) -> bool:
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "=": a == b, "!=": a != b}[comparateur]


def _bareme(montant: Decimal, etape: dict, v) -> Decimal:
    """`progressif` : chaque part du montant à son propre taux (impôt sur le revenu) ; `par_palier` : tout le montant au taux
    de la tranche où il tombe (remise par volume). Une borne est INCLUSE dans sa tranche (« jusqu'à 1 000 » contient 1 000)."""
    tranches = [(None if t["jusqu_a"] is None else Decimal(t["jusqu_a"].replace(",", ".")), v(t["taux"]))
                for t in etape["tranches"]]
    if etape["mode"] == "par_palier":
        for borne, taux in tranches:
            if borne is None or montant <= borne:
                return montant * taux / Decimal(100)
        raise CalculImpossible(f"{_ecrire(montant)} dépasse la dernière tranche du barème")
    total, bas = Decimal(0), Decimal(0)
    for borne, taux in tranches:
        haut = montant if borne is None else min(montant, borne)
        if haut > bas:
            total += (haut - bas) * taux / Decimal(100)
        if borne is None or montant <= borne:
            return total
        bas = borne
    raise CalculImpossible(f"{_ecrire(montant)} dépasse la dernière tranche du barème")


def verifier_exemples(fiche: dict) -> list[EcartExemple]:
    """Les exemples que la fiche VALIDÉE ne retrouve pas EXACTEMENT (vide : tous retrouvés). Aucune tolérance : si l'arrondi
    compte, c'est à la fiche de le dire par une étape « arrondir » — une marge ne vient jamais d'ailleurs."""
    ecarts = []
    for i, exemple in enumerate(fiche["exemples"], start=1):
        try:
            obtenu = calculer(fiche, exemple["entrees"]).resultat
        except CalculImpossible as exc:
            ecarts.append(EcartExemple(i, exemple["attendu"], f"incalculable : {exc}"))
            continue
        except (InvalidOperation, ArithmeticError) as exc:
            ecarts.append(EcartExemple(i, exemple["attendu"], f"incalculable : {exc}"))
            continue
        if obtenu != Decimal(exemple["attendu"].replace(",", ".")):
            ecarts.append(EcartExemple(i, exemple["attendu"], _ecrire(obtenu)))
    return ecarts


def entrees_attendues(fiche: dict) -> list[str]:
    """Les éléments que chaque calcul doit recevoir (ceux sans valeur fixe), dans l'ordre de la fiche."""
    return [e["nom"] for e in fiche["elements"] if "valeur" not in e]
