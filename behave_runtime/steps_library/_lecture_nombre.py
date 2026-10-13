"""Lecture normalisée d'un nombre AFFICHÉ et comparaison à tolérance DÉCLARÉE (lot Q4, D21 — outils 1 et 2).

Pourquoi. Un montant affiché s'écrit « 1 234,50 € », « 1,234.50 », « 1.234,50 » ou « (12,50) » selon la langue et
l'application. Le comparer comme du texte (« la page contient "129,51" ») ne prouve ni que c'est le bon champ ni que la
valeur est la bonne. Ce module lit le texte en un NOMBRE, ou REFUSE de le lire : une lecture ambiguë (« 1,234 » : mille
deux cent trente-quatre ou un virgule deux cent trente-quatre ?) n'est jamais devinée — deviner donnerait un faux
`conforme` ou un faux `non_conforme` selon le hasard.

Module PUR (aucune I/O, aucun navigateur, aucun LLM) : importable depuis le sous-processus Behave comme depuis les tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

_ESPACES = "     "  # insécable, fine insécable, fine, tabulaire, espace
_MOINS = "−–‒"  # signe moins typographique, tirets
# Lot PT-03 (2026-10-13) — la devise varie d'un pays à l'autre : le lecteur ne connaissait que six monnaies, et
# « 412 000 MAD » ou « 1 500 ₦ » n'étaient pas des nombres pour lui. Codes ISO 4217 EN CIRCULATION, relevés le 2026-10-13
# dans la table officielle (unités de compte BOV, CHE, CHW, CLF, COU, MXV, USN, UYI, UYW exclues) : un code absent de la
# liste n'est jamais deviné, le texte reste « pas un nombre ».
_CODES_ISO = frozenset("""
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC
    CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR
    ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK
    MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE
    SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED VES VND VUV WST XAF XCD XCG XOF
    XPF YER ZAR ZMW ZWG
""".split())

# Symboles et abréviations qui ne sont pas un code ISO -> les codes POSSIBLES, le plus courant en premier. Un symbole partagé
# (« $ » : dollar américain, canadien… ; « F CFA » : Afrique de l'Ouest ou centrale) ne désigne PAS une seule monnaie :
# `NombreLu.devises` les garde toutes, et la comparaison dit ce qu'elle n'a pas pu distinguer au lieu de trancher.
_NOTATIONS = {
    "€": ("EUR",), "₹": ("INR",), "₦": ("NGN",), "₵": ("GHS",), "₽": ("RUB",), "₺": ("TRY",), "₪": ("ILS",), "₫": ("VND",),
    "₴": ("UAH",), "₱": ("PHP",), "₸": ("KZT",), "₼": ("AZN",), "₾": ("GEL",), "฿": ("THB",), "₩": ("KRW", "KPW"),
    "¥": ("JPY", "CNY"), "￥": ("JPY", "CNY"),
    "£": ("GBP", "EGP", "LBP", "SYP", "GIP", "FKP", "SHP", "SDG", "SSP"),
    "$": ("USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN", "ARS", "CLP", "COP", "TWD", "XCD", "BSD", "BBD", "BZD", "BMD",
          "JMD", "TTD", "NAD", "LRD", "FJD", "GYD", "SRD", "KYD", "BND", "SBD", "UYU", "DOP", "CUP"),
    "R$": ("BRL",), "zł": ("PLN",), "Kč": ("CZK",), "kr": ("SEK", "NOK", "DKK", "ISK"), "KSh": ("KES",),
    "F CFA": ("XOF", "XAF"), "F.CFA": ("XOF", "XAF"), "FCFA": ("XOF", "XAF"), "Fcfa": ("XOF", "XAF"), "CFA": ("XOF", "XAF"),
    "DH": ("MAD", "AED"), "Dhs": ("MAD", "AED"), "DA": ("DZD",), "DT": ("TND",), "FC": ("CDF",),
}
_DEVISES: dict[str, tuple[str, ...]] = {**{code: (code,) for code in _CODES_ISO}, **_NOTATIONS}
_LETTRE = r"[^\W\d_]"


def _motif_devise(notation: str) -> str:
    """Une notation faite de lettres ne se lit que comme un MOT entier (« USD », jamais dans « USDT » ni « kr » dans
    « krach ») ; un symbole se lit où qu'il soit collé (« €10 », « 10€ »)."""
    if re.search(_LETTRE, notation):
        # L'espace de « F CFA » peut être insécable à l'écran : `\s` les couvre toutes.
        coeur = re.escape(notation).replace(r"\ ", r"\s")
        return rf"(?<!{_LETTRE}){coeur}(?!{_LETTRE})"
    return re.escape(notation)


# Le plus long d'abord : « F CFA » avant « CFA », « R$ » avant « $ ».
_RE_DEVISE = re.compile("|".join(_motif_devise(n) for n in sorted(_DEVISES, key=len, reverse=True)))


# Lot PT-03 (demande du porteur, 2026-10-13) — une valeur n'est pas toujours une somme d'argent : un poids, une durée, une
# distance, un volume se vérifient de la même façon, et l'outil ne doit être propre à aucun secteur. Chaque unité connue
# appartient à une NATURE ; deux unités d'une même nature se convertissent quand un rapport EXACT existe (1,5 kg = 1500 g),
# jamais sinon (mois et années, °C et °F, Mo : aucune conversion devinée). Une unité que la table ne connaît pas n'est pas
# refusée : elle est gardée telle quelle (`INCONNUE`) et ne vaut alors que pour la même écriture.
MONNAIE, POURCENTAGE, INCONNUE = "monnaie", "pourcentage", "inconnue"


def _table_des_unites() -> dict[str, tuple[str, str, Fraction | None]]:
    """notation -> (nature, unité canonique, rapport vers l'unité de base de la nature — `None` : pas de conversion)."""
    table: dict[str, tuple[str, str, Fraction | None]] = {}

    def unite(nature: str, canonique: str, rapport, *autres: str) -> None:
        for notation in (canonique, *autres):
            table[notation] = (nature, canonique, None if rapport is None else Fraction(str(rapport)))

    unite("masse", "mg", "0.001")
    unite("masse", "g", 1, "gr", "gramme", "grammes")
    unite("masse", "kg", 1000, "Kg", "KG", "kilo", "kilos", "kilogramme", "kilogrammes")
    unite("masse", "t", 1000000, "tonne", "tonnes")
    unite("masse", "lb", "453.59237", "lbs")
    unite("masse", "oz", "28.349523125")
    unite("longueur", "mm", "0.001")
    unite("longueur", "cm", "0.01")
    unite("longueur", "dm", "0.1")
    unite("longueur", "m", 1, "mètre", "mètres", "metre", "metres")
    unite("longueur", "km", 1000, "Km", "KM", "kilomètre", "kilomètres")
    unite("longueur", "ft", "0.3048")
    unite("longueur", "mile", "1609.344", "miles")
    unite("surface", "mm²", "0.000001")
    unite("surface", "cm²", "0.0001")
    unite("surface", "m²", 1)
    unite("surface", "ha", 10000, "hectare", "hectares")
    unite("surface", "km²", 1000000)
    unite("volume", "ml", "0.001", "mL")
    unite("volume", "cl", "0.01", "cL")
    unite("volume", "dl", "0.1", "dL")
    unite("volume", "l", 1, "L", "litre", "litres")
    unite("volume", "hl", 100, "hL")
    unite("volume", "m³", 1000)
    unite("durée", "ms", "0.001")
    unite("durée", "s", 1, "sec", "seconde", "secondes")
    unite("durée", "min", 60, "mn", "minute", "minutes")
    unite("durée", "h", 3600, "heure", "heures")
    # Revue du 2026-10-13 : « 2 jours » contre « 16 heures » accusait une application saine, et « 2 jours » contre « 48 h »
    # réussissait à tort — dans un logiciel de gestion un jour est souvent un jour OUVRÉ, une semaine cinq jours. Jamais convertis.
    unite("durée", "j", None, "jour", "jours", "day", "days")
    unite("durée", "semaine", None, "semaines", "sem")
    unite("durée", "mois", None)  # un mois n'a pas une durée fixe : jamais converti
    unite("durée", "an", None, "ans", "année", "années")
    unite("température", "°C", None, "°c")
    unite("température", "°F", None, "°f")
    unite("données", "o", None, "octet", "octets")
    unite("données", "ko", None, "Ko", "KB", "kB")  # 1000 ou 1024 selon l'application : jamais converti
    unite("données", "Mo", None, "MB")
    unite("données", "Go", None, "GB")
    unite("données", "To", None, "TB")
    unite("énergie", "Wh", 1)
    unite("énergie", "kWh", 1000, "KWh")
    unite("énergie", "MWh", 1000000)
    unite("puissance", "W", 1)
    unite("puissance", "kW", 1000, "KW")
    unite("puissance", "MW", 1000000)
    unite("vitesse", "m/s", 1)
    unite("vitesse", "km/h", Fraction(5, 18), "Km/h", "KM/H")
    unite(POURCENTAGE, "‰", "0.1")  # même nature que « % » (rapport 1) : 5 ‰ = 0,5 % (revue du 2026-10-13)
    return table


_UNITES = _table_des_unites()
# Les natures dont une valeur SANS unité peut cacher une autre unité (« 1500 » pour « 1,5 kg »). Un taux n'en est pas : seul
# un facteur 10, 100 ou 1000 le sépare d'une autre écriture (`_meme_taux_ecrit_autrement`).
_NATURES_CONVERTIBLES = frozenset(nature for nature, _, rapport in _UNITES.values() if rapport is not None) - {POURCENTAGE}
# Ce qui peut s'écrire après un nombre : des lettres, et les signes des unités composées (« km/h », « m² », « °C »).
_RE_UNITE = re.compile(rf"(?:{_LETTRE}|[°µ‰²³/.'’\- ])+")
_LONGUEUR_MAX_UNITE = 24


class LectureImpossible(ValueError):
    """Le texte n'est pas un nombre, ou plusieurs lectures sont possibles. Le message dit POURQUOI (jamais deviné)."""


@dataclass(frozen=True)
class NombreLu:
    valeur: Decimal
    devise: str | None = None  # la monnaie la plus courante pour la notation lue (« $ » -> USD)
    pourcentage: bool = False
    texte_source: str = ""
    devises: frozenset[str] = frozenset()  # TOUTES les monnaies que la notation lue peut désigner (« $ » -> USD, CAD…)
    notation_devise: str = ""  # la notation telle qu'elle est écrite (« $ », « F CFA », « EUR »)
    # Ce que la valeur MESURE : `MONNAIE`, `POURCENTAGE`, « masse », « durée »… `INCONNUE` pour une unité hors table,
    # vide quand aucune unité n'accompagne le nombre.
    nature: str = ""
    unite: str = ""  # l'unité canonique (« kg », « EUR », « % ») ou, pour une unité inconnue, son écriture normalisée
    rapport: Fraction | None = None  # vers l'unité de base de la nature ; `None` : aucune conversion exacte
    # Tout texte qui accompagne une devise ou un pourcentage sans être l'unité : « TTC », « HT », mais aussi « k » de « 5 k€ »,
    # « CA » de « 5 CA$ », « o » de « 5 %o ». Jamais ignoré : il peut cacher un facteur mille (`comparer_valeurs`).
    qualificatif: str = ""
    entre_parentheses: bool = False  # « (12,50) » : lu négatif (convention comptable), mais l'écriture est retenue
    # Une lettre est COLLÉE au symbole de la monnaie (« C$ », « HK$ », « k€ ») : ce n'est peut-être plus le symbole nu, et la
    # liste de ses monnaies ne vaut plus. « 129,51 $ HT », mention séparée, reste un montant en dollars.
    mention_collee: bool = False

    def __post_init__(self):
        # Une valeur construite à la main (`NombreLu(Decimal(5), "EUR")`) reste COHÉRENTE : la monnaie nommée fait partie
        # des monnaies possibles, et la nature se déduit de l'unité donnée (revues du 2026-10-13).
        if self.devise and self.pourcentage:
            raise ValueError("une valeur ne peut pas être à la fois un montant et un pourcentage")
        if self.nature == MONNAIE and not self.devise:
            if self.unite not in _CODES_ISO:
                raise ValueError("une valeur de nature monnaie doit nommer sa monnaie (code ISO)")
            object.__setattr__(self, "devise", self.unite)
        if (self.pourcentage or (self.nature == POURCENTAGE and self.unite == "%")) and self.rapport is None:
            object.__setattr__(self, "rapport", Fraction(1))
        if self.devise and not self.devises:
            object.__setattr__(self, "devises", frozenset({self.devise}))
        if not self.nature and (self.devise or self.pourcentage):
            object.__setattr__(self, "nature", MONNAIE if self.devise else POURCENTAGE)
            object.__setattr__(self, "unite", self.devise or "%")


def _groupes_de_trois(texte: str, sep: str) -> bool:
    return re.fullmatch(r"\d{1,3}(?:" + re.escape(sep) + r"\d{3})+", texte) is not None


def lire_nombre(texte: str, *, separateur_decimal: str | None = None, avec_unite: bool = False,
                decimal_si_ambigu: str | None = None, milliers_si_ambigu: str | None = None) -> NombreLu:
    """Texte affiché -> `NombreLu`. `separateur_decimal` ('.' ou ',') lève l'ambiguïté quand l'appelant la connaît (langue).

    `avec_unite` : lit aussi ce qui SUIT le nombre comme une unité (« 1,5 kg », « 3 jours », « 12 pièces ») ; sans lui, tout
    texte autre qu'une devise ou un « % » reste refusé, comme avant le lot PT-03.

    `decimal_si_ambigu` et `milliers_si_ambigu` ('.' ou ',') : l'écriture des nombres DÉCLARÉE par le projet. Elle ne
    tranche QUE ce que le lecteur refuse de deviner (« 1,234 » : mille deux cent trente-quatre, ou un virgule deux cent
    trente-quatre ?), et seulement pour un séparateur qu'elle NOMME : « 1 234,56 » dit que la virgule est décimale, elle ne
    dit rien du point — « 1.234 » reste ambigu (revue du 2026-10-13 : le lire 1234 validait un poids affiché mille fois trop
    grand, et accusait un « 1.000 » sorti d'un arrondi à trois décimales). Une écriture lisible sans elle se lit comme
    avant. `separateur_decimal`, lui, s'IMPOSE à toute écriture à un seul séparateur (« 1234.50 » avec ',' imposé vaut
    123450) : il ne convient pas à un réglage de projet."""
    if separateur_decimal not in (None, ".", ","):
        raise ValueError("separateur_decimal doit être '.', ',' ou None")
    if decimal_si_ambigu not in (None, ".", ",") or milliers_si_ambigu not in (None, ".", ","):
        raise ValueError("decimal_si_ambigu et milliers_si_ambigu doivent être '.', ',' ou None")
    if decimal_si_ambigu is not None and decimal_si_ambigu == milliers_si_ambigu:
        raise ValueError("un même signe ne peut pas séparer à la fois les décimales et les milliers")
    brut = str(texte)
    reste = brut.strip()
    if not reste:
        raise LectureImpossible("texte vide")

    negatif = parentheses = False
    if reste.startswith("(") and reste.endswith(")"):  # convention comptable : (12,50) = -12,50
        negatif, parentheses, reste = True, True, reste[1:-1].strip()
    if avec_unite:  # « m2 », « km2 », « m3 » — avant tout le reste : le « 2 » de « 5 €/m2 » n'est pas un second nombre
        reste = re.sub(r"(?<=m)2(?!\d)", "²", re.sub(r"(?<=m)3(?!\d)", "³", reste))

    # Une unité se place AVANT ou APRÈS le nombre, jamais au milieu de ses chiffres : « 5€300 » ou « 5%300 » sont deux
    # nombres, et les lire 5300 ferait d'une espace de remplacement un séparateur de milliers (revue du 2026-10-13).
    for trouve in list(_RE_DEVISE.finditer(reste)) + list(re.finditer("%", reste)):
        if re.search(r"\d", reste[:trouve.start()]) and re.search(r"\d", reste[trouve.end():]):
            raise LectureImpossible(f"« {brut} » : une unité au milieu des chiffres (deux nombres ?)")
    def _lettre_en(indice: int) -> bool:
        return 0 <= indice < len(reste) and re.fullmatch(_LETTRE, reste[indice]) is not None

    mention_collee = any(_lettre_en(t.start() - 1) or _lettre_en(t.end()) for t in _RE_DEVISE.finditer(reste))
    notations_vues = [re.sub(r"\s", " ", n) for n in _RE_DEVISE.findall(reste)]
    reste = _RE_DEVISE.sub(" ", reste)
    if len(notations_vues) > 1:  # deux montants collés (« 12 € 15 € », prix barré...) ne sont pas UN nombre
        raise LectureImpossible(f"« {brut} » contient plusieurs devises ou montants : un seul nombre est attendu")
    notation = notations_vues[0] if notations_vues else ""
    possibles = _DEVISES.get(notation, ())
    if reste.count("%") > 1:
        raise LectureImpossible(f"« {brut} » contient plusieurs pourcentages : un seul nombre est attendu")
    pourcentage = "%" in reste
    if pourcentage and notation:  # « 5 € % » : ni un montant ni un taux
        raise LectureImpossible(f"« {brut} » porte à la fois une devise et un pourcentage")
    if pourcentage and negatif:  # « (20 %) » : les parenthèses comptables valent pour un montant, pas pour un taux
        raise LectureImpossible(f"« {brut} » : un pourcentage entre parenthèses ne se lit pas comme un nombre négatif")
    reste = reste.replace("%", " ")

    for c in _MOINS:
        reste = reste.replace(c, "-")
    reste = reste.strip(_ESPACES)
    if reste.startswith("-"):
        negatif, reste = True, reste[1:]
    elif reste.startswith("+"):
        reste = reste[1:]
    suite = ""
    if avec_unite:
        reste, suite = _separer_la_suite(reste, brut)
    reste = _sans_groupes_de_milliers(reste, brut)

    if not re.fullmatch(r"[\d.,]+", reste) or not re.search(r"\d", reste):
        raise LectureImpossible(f"« {brut} » n'est pas un nombre")

    valeur = _decimal(reste, separateur_decimal, brut, decimal_si_ambigu, milliers_si_ambigu)
    valeur = -valeur if negatif else valeur
    if notation or pourcentage:
        if suite.startswith("/") or suite.casefold().startswith("par "):
            # « 12 € / kg », « 3 % par mois » : un RAPPORT, pas un montant — gardé tel quel, comparable à la même écriture.
            # « € » ne désigne que l'euro : « 12 €/kg » vaut « 12 EUR/kg ». « $ » en désigne trente : « 45 $/h » ne vaut que
            # « 45 $/h » — le réduire à sa monnaie la plus courante validait « 45 USD/h » pour une application canadienne
            # (revue du 2026-10-13, faux vert reproduit).
            base = "%" if not notation else possibles[0] if len(possibles) == 1 else notation
            return NombreLu(valeur, None, False, brut, nature=INCONNUE, unite=_ecriture_normalisee(f"{base} {suite}"),
                            entre_parentheses=parentheses)
        if notation:
            return NombreLu(valeur, possibles[0], False, brut, frozenset(possibles), notation,
                            nature=MONNAIE, unite=possibles[0], qualificatif=suite, entre_parentheses=parentheses,
                            mention_collee=mention_collee)
        return NombreLu(valeur, None, True, brut, nature=POURCENTAGE, unite="%", qualificatif=suite)
    if not suite:
        return NombreLu(valeur, None, False, brut, entre_parentheses=parentheses)
    if parentheses:
        # « (12 pièces) », « (5 kg) » : hors d'un montant, des parenthèses ne disent pas « négatif » (revue du 2026-10-13 : une
        # application saine sortait `non_conforme`). Même refus que pour « (20 %) ».
        raise LectureImpossible(f"« {brut} » : une valeur entre parenthèses ne se lit comme un nombre négatif que pour un montant")
    connue = _UNITES.get(suite)
    if connue is None:
        return NombreLu(valeur, None, False, brut, nature=INCONNUE, unite=_ecriture_normalisee(suite))
    nature, canonique, rapport = connue
    return NombreLu(valeur, None, False, brut, nature=nature, unite=canonique, rapport=rapport)


def _ecriture_normalisee(unite: str) -> str:
    """Espaces réduits, CASSE GARDÉE : plier la casse rendait « 5 MPa » égal à « 5 mPa », « 5 mA » à « 5 MA » (un facteur un
    milliard, revue du 2026-10-13). Deux écritures qui ne diffèrent que par la casse ne concluent donc pas."""
    return re.sub(r"\s*/\s*", "/", re.sub(r"\s+", " ", unite)).strip()


def _separer_la_suite(reste: str, brut: str) -> tuple[str, str]:
    """(le nombre, ce qui le suit) — « 1 234,5 kg » -> (« 1 234,5 », « kg »). Ce qui suit ne porte JAMAIS de chiffre : un
    second nombre (« 2 sur 5 », « 1 h 30 ») n'est pas une unité, et la lecture reste refusée par l'appelant."""
    trouve = re.fullmatch(r"(.*\d)(\D*)", reste, flags=re.S)
    if trouve is None:
        return reste, ""
    nombre, suite = trouve.group(1), re.sub(r"\s+", " ", trouve.group(2)).strip()
    if not suite:
        return nombre, ""
    if (len(suite) > _LONGUEUR_MAX_UNITE or not _RE_UNITE.fullmatch(suite)
            or not re.match(rf"{_LETTRE}|[°µ‰/]", suite) or not re.search(rf"{_LETTRE}|‰", suite)):
        raise LectureImpossible(f"« {brut} » : « {suite} » après le nombre n'est pas une unité")
    # Un exposant ou une fraction (« 5² », « 10⁶ », « 5½ ») compte comme une « lettre » pour une expression régulière, mais
    # c'est un chiffre : il change le nombre. Seuls « ² » et « ³ » collés à une lettre sont une unité (« m² », « cm³ »).
    for i, caractere in enumerate(suite):
        if caractere.isnumeric() and not (caractere in "²³" and i > 0 and suite[i - 1].isalpha() and not suite[i - 1].isnumeric()):
            raise LectureImpossible(f"« {brut} » : « {suite} » après le nombre porte un chiffre (exposant, fraction)")
    return nombre, suite


def _sans_groupes_de_milliers(reste: str, brut: str) -> str:
    """Espaces et apostrophes ne sont admis QUE comme séparateurs de milliers (`1 234 567`, `1'234`), dans la partie entière.

    Revue du 2026-10-07 : « 10 12 » ou « 1 2 3 » (pagination), « 12 5 € » (quantité puis prix) étaient fusionnés en un seul
    nombre (1012, 123, 125) — un `Alors` aurait alors pu réussir sans que la valeur soit prouvée."""
    marques = _ESPACES + "'’"
    if not any(c in reste for c in marques):
        return reste
    coupure = min((i for i in (reste.find("."), reste.find(",")) if i >= 0), default=len(reste))
    entier, queue = reste[:coupure], reste[coupure:]
    admis = (re.fullmatch(r"\d{1,3}(?:[" + re.escape(_ESPACES) + r"]\d{3})+", entier)
             or re.fullmatch(r"\d{1,3}(?:['’]\d{3})+", entier))
    if not admis or any(c in queue for c in marques):
        raise LectureImpossible(f"« {brut} » : espaces ou apostrophes en dehors de groupes de milliers (plusieurs nombres ?)")
    for c in marques:
        entier = entier.replace(c, "")
    return entier + queue


def _decimal(reste: str, impose: str | None, brut: str, decimal_declare: str | None = None,
             milliers_declare: str | None = None) -> Decimal:
    points, virgules = reste.count("."), reste.count(",")
    if points and virgules:  # le DERNIER séparateur est le décimal, l'autre ne peut être que des milliers
        decimal = "." if reste.rfind(".") > reste.rfind(",") else ","
        milliers = "," if decimal == "." else "."
        entier, _, fraction = reste.rpartition(decimal)
        if milliers in fraction or not _groupes_de_trois(entier, milliers):
            raise LectureImpossible(f"« {brut} » : séparateurs de milliers incohérents")
        return _construire(entier.replace(milliers, ""), fraction, brut)

    present = "." if points else "," if virgules else None
    if present is None:
        return _construire(reste, "", brut)
    if reste.count(present) > 1:  # « 1.234.567 » : forcément des milliers
        if impose == present:
            raise LectureImpossible(f"« {brut} » : plusieurs séparateurs décimaux '{present}'")
        if not _groupes_de_trois(reste, present):
            raise LectureImpossible(f"« {brut} » : groupes de milliers incohérents")
        return _construire(reste.replace(present, ""), "", brut)

    entier, _, fraction = reste.partition(present)
    if impose is not None:
        if impose == present:
            return _construire(entier, fraction, brut)
        return _construire(entier + fraction, "", brut)  # l'autre est le décimal : celui-ci sépare des milliers
    if len(fraction) == 3 and 1 <= len(entier) <= 3 and entier != "0":
        # Le projet a déclaré comment son application écrit les nombres : il tranche pour un séparateur qu'il a nommé.
        if present == decimal_declare:
            return _construire(entier, fraction, brut)
        if present == milliers_declare and not entier.startswith("0"):  # « 0.123 », « 00.123 » : jamais des milliers
            return _construire(entier + fraction, "", brut)
        raise LectureImpossible(
            f"« {brut} » est ambigu : {entier}{fraction} (milliers) ou {entier}.{fraction} (décimales) ? "
            "Préciser le séparateur décimal.")
    return _construire(entier, fraction, brut)


def _construire(entier: str, fraction: str, brut: str) -> Decimal:
    try:
        return Decimal(f"{entier or '0'}.{fraction}" if fraction else (entier or "0"))
    except InvalidOperation as erreur:
        raise LectureImpossible(f"« {brut} » n'est pas un nombre") from erreur


# ── Comparaison à tolérance DÉCLARÉE ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Comparaison:
    ok: bool
    message: str


def comparer(lu: Decimal | NombreLu, attendu, *, tolerance=None, source: str = "",
             devise_attendue: str | None = None, pourcentage_attendu: bool | None = None) -> Comparaison:
    """`lu` égal à `attendu` à `tolerance` près. Sans tolérance : égalité EXACTE (le message dit « exacte »).

    - Une tolérance non nulle EXIGE sa source (« arrondi de la devise », « demandé par la spec »…) : un écart accepté doit
      toujours pouvoir être justifié (D19). Elle doit être FINIE et strictement inférieure à la valeur attendue (à 1 si
      l'attendu est plus petit) : une tolérance infinie ou énorme accepterait n'importe quelle valeur.
    - `source` est du texte de traçabilité, PAS une preuve : au câblage, la tolérance et sa source viennent de la spec ou de
      la devise (signal structurel), jamais d'un texte écrit par l'agent (décision 0015).
    - Unités : si `devise_attendue` / `pourcentage_attendu` sont donnés et que `lu` est un `NombreLu` qui les contredit, la
      comparaison ÉCHOUE (5 $ n'est pas 5 €, 5 % n'est pas 5). Non donnés : unité non vérifiée, et le message le dit.
      Une notation partagée (« $ », « F CFA ») satisfait chacune des monnaies qu'elle peut désigner.
    Un `float` est converti par sa représentation texte, jamais par sa valeur binaire."""
    valeur_lue = lu.valeur if isinstance(lu, NombreLu) else lu
    cible = _en_decimal(attendu)
    marge = Decimal(0) if tolerance is None else _en_decimal(tolerance)
    if not (cible.is_finite() and valeur_lue.is_finite() and marge.is_finite()):
        raise ValueError("valeur, attendu et tolérance doivent être des nombres finis")
    if marge < 0:
        raise ValueError("la tolérance ne peut pas être négative")
    if marge > 0 and not source.strip():
        raise ValueError("une tolérance non nulle doit déclarer sa source")
    if marge > 0 and marge >= max(abs(cible), Decimal(1)):
        raise ValueError(f"tolérance {marge} excessive pour l'attendu {cible} : elle accepterait presque toute valeur")
    ecart = abs(valeur_lue - cible)
    qualif = "exacte, aucune tolérance" if marge == 0 else f"± {marge} — {source.strip()}"
    unites_ok, remarques = True, []
    if isinstance(lu, NombreLu):
        if devise_attendue is not None:
            if devise_attendue not in lu.devises:  # « 5 $ » peut être des CAD : la notation lue les admet tous
                unites_ok = False
                remarques.append(f"devise lue {lu.devise or 'aucune'}, attendue {devise_attendue}")
        elif lu.devise:
            remarques.append(f"devise lue {lu.devise} non vérifiée")
        if pourcentage_attendu is not None:
            if lu.pourcentage != pourcentage_attendu:
                unites_ok = False
                remarques.append("pourcentage lu" if lu.pourcentage else "pourcentage attendu mais non lu")
        elif lu.pourcentage:
            remarques.append("pourcentage lu non vérifié")
    suite = f" ; {' ; '.join(remarques)}" if remarques else ""
    return Comparaison(ecart <= marge and unites_ok, f"attendu {cible} ({qualif}), lu {valeur_lue}{suite}")


def _en_decimal(valeur) -> Decimal:
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))


# ── Deux valeurs ÉCRITES (l'attendu du test, la valeur de l'écran) — lot PT-03 ───────────────────────────────────────────────

EGAL, DIFFERENT, UNITE_NON_VERIFIABLE = "egal", "different", "unite_non_verifiable"


@dataclass(frozen=True)
class ComparaisonValeurs:
    etat: str  # EGAL | DIFFERENT | UNITE_NON_VERIFIABLE
    message: str


def _unite(n: NombreLu) -> str:
    if not n.nature:
        return "aucune unité"
    if n.nature == INCONNUE:
        return f"unité « {n.unite} », inconnue de l'outil"
    if n.nature != MONNAIE:
        return f"{n.nature}, {n.unite}"
    if len(n.devises) == 1:
        return f"monnaie, {n.unite}"
    exemples = sorted(n.devises - {n.unite})[:2]
    return f"monnaie, « {n.notation_devise} » : {n.unite}, {', '.join(exemples)}… ({len(n.devises)} possibles)"


def est_un_code_de_monnaie(code: str) -> bool:
    """`code` est-il un code ISO 4217 que le lecteur connaît ? Pour valider la monnaie déclarée par un projet."""
    return code in _CODES_ISO


def _meme_taux_ecrit_autrement(a: Decimal, b: Decimal) -> bool:
    """18 (%) et 0,18, 5 (‰) et 0,005 : le même taux écrit de deux façons — ni égal ni différent tant que l'unité manque
    d'un côté."""
    return any(a == b * facteur or b == a * facteur for facteur in (10, 100, 1000))


def _demi_pas_d_affichage(n: NombreLu) -> Fraction:
    """La moitié du dernier chiffre AFFICHÉ, dans l'unité de base de la nature : « 0,33 h » peut valoir de 0,325 à 0,335 h."""
    exposant = n.valeur.as_tuple().exponent
    return Fraction(1, 2) * Fraction(10) ** (exposant if isinstance(exposant, int) else 0) * (n.rapport or 1)


def _mention(n: NombreLu) -> str:
    return f"« {n.qualificatif} »" if n.qualificatif else "aucune mention"


def comparer_valeurs(lu: NombreLu, attendu: NombreLu, *, devise_du_projet: str = "") -> ComparaisonValeurs:
    """La valeur LUE à l'écran contre l'attendu du test, nombre ET unité. Trois issues, jamais deux :

    - `DIFFERENT` : le nombre diffère (égalité EXACTE, aucune tolérance : un centime d'écart est un écart), ou les deux
      portent des unités de natures différentes (18 % n'est pas 18 €, 5 kg n'est pas 5 km), ou deux monnaies distinctes ;
    - `UNITE_NON_VERIFIABLE` : rien ne permet de trancher — une unité ou une mention est écrite d'un côté et pas de l'autre,
      ou les deux unités ne se convertissent pas l'une dans l'autre (unité inconnue de l'outil, jours et heures, mois et
      années). Ni un succès ni un défaut de l'application ;
    - `EGAL` : même grandeur — même nombre dans la même unité, ou valeurs égales après une conversion EXACTE
      (1,5 kg = 1500 g) ; ou le même nombre sans unité des deux côtés.

    Décision A24 (porteur, 2026-10-13, « prudent ») — JAMAIS de réussite sans que l'unité soit vérifiée :
    - l'attendu n'écrit pas d'unité et l'écran en affiche une : si c'est une monnaie et que le projet a déclaré la sienne
      (`devise_du_projet`, un code ISO), l'attendu est lu dans la monnaie du projet (« 129,51 » attendu contre « 129,51 $ »
      affiché est un DÉFAUT pour un projet en euros) ; sinon l'outil ne conclut pas. Avant, ce cas RÉUSSISSAIT sans trace ;
    - une notation partagée par plusieurs monnaies (« $ », « F CFA ») ne prouve une monnaie précise que si le projet a
      déclaré celle-ci ; écrite à l'identique des deux côtés, elle se compare à elle-même.

    Deuxième revue (2026-10-13, faux verts reproduits) — ce qui accompagne une devise ou un pourcentage n'est JAMAIS ignoré :
    « 5 k€ » valait « 5 € », « 5 HK$ » valait « 5 USD », « 5 %o » valait « 5 % ». Les mentions doivent être les mêmes des
    deux côtés, casse comprise ; sinon l'outil ne conclut pas — même quand les nombres diffèrent (« 12 k€ » n'est pas un
    défaut face à « 12 000 € »).

    Une monnaie ne se convertit JAMAIS dans une autre."""
    base = f"attendu {attendu.valeur} ({_unite(attendu)}), lu {lu.valeur} ({_unite(lu)}), comparaison exacte"
    memes_nombres = lu.valeur == attendu.valeur

    def issue(etat: str, precision: str = "") -> ComparaisonValeurs:
        return ComparaisonValeurs(etat, base + (f" ; {precision}" if precision else ""))

    # « (3) » à côté d'un libellé : un compteur entre parenthèses, ou moins trois ? Hors d'un montant, on ne tranche pas.
    # Ni « différent de 3 » ni « égal à -3 » : si l'on ne sait pas ce que disent les parenthèses, on ne sait ni l'un ni l'autre.
    # La convention comptable ne vaut que si le côté ENTRE PARENTHÈSES est lui-même un montant : « (3) » face à « 3 € »
    # n'accuse pas l'application sur la seule lecture de parenthèses dont rien ne dit qu'elles entourent un montant.
    entre_parentheses = lu if lu.entre_parentheses else attendu
    if (lu.entre_parentheses != attendu.entre_parentheses and entre_parentheses.nature != MONNAIE
            and abs(lu.valeur) == abs(attendu.valeur) and lu.valeur != 0):
        return issue(UNITE_NON_VERIFIABLE, "parenthèses : un nombre négatif, ou une valeur simplement mise entre parenthèses ?")

    if not attendu.nature:
        if not lu.nature:  # aucune unité nulle part : deux nombres
            return issue(EGAL if memes_nombres else DIFFERENT)
        sans_unite = f"l'attendu n'écrit pas d'unité alors que l'écran en affiche une ({_unite(lu)}) : écrivez-la dans le test"
        if lu.nature == MONNAIE and devise_du_projet:
            lecture = f"l'attendu n'écrit pas d'unité : lu dans la monnaie du projet ({devise_du_projet})"
            if devise_du_projet not in lu.devises:
                if lu.mention_collee and len(lu.devises) > 1:  # « 5 C$ » : pas le « $ » nu, on n'accuse pas
                    return issue(UNITE_NON_VERIFIABLE, f"{lecture} ; l'écran précise son symbole par {_mention(lu)}")
                return issue(DIFFERENT, f"{lecture}, qui n'est pas celle de l'écran")
            if lu.qualificatif:
                return issue(UNITE_NON_VERIFIABLE, f"{lecture} ; l'écran ajoute {_mention(lu)}, que l'attendu n'écrit pas")
            return issue(EGAL if memes_nombres else DIFFERENT, lecture)
        if lu.qualificatif or memes_nombres:
            return issue(UNITE_NON_VERIFIABLE, sans_unite)
        if lu.nature == MONNAIE:
            return issue(DIFFERENT)  # une monnaie ne se convertit pas : un autre nombre est un autre montant, quelle qu'elle soit
        if lu.nature == POURCENTAGE and not _meme_taux_ecrit_autrement(lu.valeur, attendu.valeur):
            return issue(DIFFERENT)
        return issue(UNITE_NON_VERIFIABLE, sans_unite)
    if not lu.nature:
        if (memes_nombres or attendu.qualificatif or attendu.nature in _NATURES_CONVERTIBLES or attendu.nature == INCONNUE
                or (attendu.nature == POURCENTAGE and _meme_taux_ecrit_autrement(lu.valeur, attendu.valeur))):
            return issue(UNITE_NON_VERIFIABLE,
                         "aucune unité n'est affichée à côté de la valeur" + ("" if memes_nombres else
                                                                             " : elle est peut-être exprimée autrement"))
        return issue(DIFFERENT)  # une monnaie ou un pourcentage ne se convertit pas : un autre nombre est une autre valeur
    if INCONNUE in (lu.nature, attendu.nature):
        if lu.nature != attendu.nature or lu.unite != attendu.unite:
            return issue(UNITE_NON_VERIFIABLE, "l'outil ne sait pas rapprocher ces deux unités")
        return issue(EGAL if memes_nombres else DIFFERENT)
    if lu.nature != attendu.nature:
        return issue(DIFFERENT, "ce ne sont pas des grandeurs de même nature")
    if lu.nature == MONNAIE and not (attendu.devises & lu.devises):
        # « 5 C$ » (córdoba) contre « 5 NIO », « 5 T$ » contre « 5 TOP » : un symbole partagé PRÉCISÉ par une lettre collée
        # n'est plus le symbole nu — la liste de ses monnaies ne vaut plus, on n'accuse pas l'application. Une mention
        # SÉPARÉE (« 129,51 $ HT » contre « 129,51 € HT ») ne change rien à la monnaie : le défaut reste prouvé.
        if any(n.mention_collee and len(n.devises) > 1 for n in (lu, attendu)):
            return issue(UNITE_NON_VERIFIABLE, "une notation partagée, précisée par une mention que l'outil ne connaît pas")
        return issue(DIFFERENT, "une monnaie ne se convertit pas dans une autre")
    if lu.qualificatif != attendu.qualificatif:
        return issue(UNITE_NON_VERIFIABLE, f"{_mention(attendu)} attendue, {_mention(lu)} affichée")
    if lu.nature == MONNAIE:
        if not memes_nombres:
            return issue(DIFFERENT)
        if attendu.devises == lu.devises:
            return issue(EGAL, "la même notation des deux côtés ; elle ne distingue pas ces monnaies entre elles"
                         if len(lu.devises) > 1 else "")
        if devise_du_projet in (attendu.devises & lu.devises):
            return issue(EGAL, f"notation partagée, lue dans la monnaie du projet ({devise_du_projet})")
        return issue(UNITE_NON_VERIFIABLE, "une notation partagée par plusieurs monnaies ne prouve pas celle qui est attendue : "
                                           "déclarez la monnaie du projet, ou attendez la même notation")
    if lu.unite == attendu.unite:
        return issue(EGAL if memes_nombres else DIFFERENT)
    if lu.rapport is None or attendu.rapport is None:
        return issue(UNITE_NON_VERIFIABLE, f"aucune conversion exacte entre {attendu.unite} et {lu.unite}")
    convertie, voulue = Fraction(lu.valeur) * lu.rapport, Fraction(attendu.valeur) * attendu.rapport
    conversion = f"après conversion entre {lu.unite} et {attendu.unite}"
    if convertie == voulue:
        return issue(EGAL, conversion)
    # « 0,33 h » contre « 20 min », « 1 lb » contre « 0,454 kg » : l'écart tient dans l'arrondi de l'affichage — ce n'est pas
    # un défaut prouvé (revue du 2026-10-13), et ce n'est JAMAIS une égalité.
    # L'attendu n'entre dans la fenêtre que s'il est lui-même écrit avec des décimales (« 27,78 m/s ») : compter le demi-pas
    # d'un attendu entier (« 2 h ») rendait non concluants 91 comme 149 minutes, et « 600 kg » face à « 1 t ».
    fenetre = _demi_pas_d_affichage(lu)
    exposant = attendu.valeur.as_tuple().exponent
    if isinstance(exposant, int) and exposant < 0:
        fenetre = max(fenetre, _demi_pas_d_affichage(attendu))
    # Borne COMPRISE : 0,5 h s'affiche « 1 h » dès que l'application arrondit au demi supérieur — « 1 h » face à « 30 min »
    # n'est pas un défaut prouvé.
    if abs(convertie - voulue) <= fenetre:
        return issue(UNITE_NON_VERIFIABLE, f"{conversion}, l'écart est inférieur à l'arrondi de l'affichage")
    return issue(DIFFERENT, conversion)
