"""Lot VH-07 (T10, décision D26) — « exécuter puis écrire » : l'agent joue des ACTIONS sur un bac à sable avant d'écrire son test.

Pourquoi. Mesuré (banc base-4 et base-5, octobre 2026) : la première cause d'erreur technique après génération est une page qui
CHANGE après une action — l'agent, qui écrit sans exécuter, cherche ensuite un champ sur une page qu'on a quittée (quantité
cherchée dans le panier au lieu de la page des produits). Aucun contrôle à l'écriture ne peut le deviner : l'annuaire ne sait pas
où mène une soumission. Il faut jouer l'action pour le voir.

Les quatre conditions de D26, tenues par le CODE et pas par le prompt :

1. **bac à sable déclaré** : l'outil n'existe que si le projet a autorisé la calibration en écriture ET déclaré une adresse de
   remise à zéro de la même application (`construire` ; sinon l'outil n'est même pas proposé à l'agent). La déclaration est une
   adresse COMPLÈTE : si l'adresse du projet change, elle ne vaut plus (on ne remet pas à zéro une application non déclarée) ;
2. **remise à zéro avant ET après chaque essai**, prouvée par une réponse 2xx directe (une redirection n'est pas une preuve) ;
   sans remise à zéro avant, pas d'essai ; sans remise à zéro après, l'agent le sait, plus aucun essai n'est joué et les
   exécutions réelles de l'application sont retenues tant qu'elle n'est pas remise à zéro (`guardrails/bac_a_sable`) ;
3. **jamais en production** : l'essai est joué par le même harnais que les exécutions — son garde-fou (`ODOO_ENV=prod`) reste
   seul juge, intact ; cet outil ne le contourne ni ne le remplace ;
4. **ce que l'agent observe sert à ÉCRIRE, jamais à juger** :
   - seules des ACTIONS sont jouées — le fichier joué est relu par l'analyseur de Behave lui-même : autant de steps que de
     lignes, tous de type action, sans tableau ni texte joint (une liste de caractères interdits ne ferme jamais la classe) ;
   - l'observation ne contient que l'adresse de la page et ses CONTRÔLES (champs, boutons, liens : rôle et nom) — ni valeur de
     champ, ni message, ni total ; un échec ne rend que le TYPE de l'erreur, jamais son message (qui cite la page) ;
   - ce qui n'a été vu QUE pendant un essai ne peut pas être cité sous un « Alors » sans que la spécification le dise
     (`valeurs_tirees_de_l_essai`, refus à l'écriture) ;
   - un essai n'apprend rien au projet et ne produit ni verdict, ni cause, ni trace d'exécution.

Aucun moteur d'action nouveau : l'essai est un `.feature` temporaire joué par le VRAI harnais Behave avec la bibliothèque de
steps — ce qui marche à l'essai marchera au run. Coût : un run Behave par essai, aucun appel LLM ; nombre d'essais borné.
"""

from __future__ import annotations

import contextlib
import json
from decimal import Decimal, InvalidOperation
import logging
import re
import shutil
import tempfile
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, unquote, urljoin, urlparse

from testpilot.guardrails import bac_a_sable
from testpilot.parametres.ia_peut_agir import ia_peut_ecrire

if TYPE_CHECKING:
    from testpilot.generation.tools import ToolContext, ToolOutcome

logger = logging.getLogger(__name__)

NOM_OUTIL = "essayer_les_actions"
# Nom DUPLIQUÉ côté `behave_runtime/environment.py` (le harnais ne dépend pas du paquet) : un test d'accord les compare.
ESSAI_ETAT_FILE_ENV = "TP_ESSAI_ETAT_FILE"
MAX_ESSAIS_PAR_GENERATION = 6
# Appels à l'outil, refus compris : un agent ne relance pas indéfiniment un essai refusé (chaque appel est un tour payé).
MAX_TENTATIVES = 12
MAX_ETAPES = 12
# Un essai joue au plus `MAX_ETAPES` actions : au-delà de ce délai il est interrompu (le délai d'une exécution réelle, de
# l'ordre du quart d'heure, bloquerait la génération ET les exécutions réelles de l'application, qui attendent la fin de l'essai).
DELAI_ESSAI_S = 180
REPRISES_REMISE_A_ZERO = 3
_MOTS_D_ACTION = ("Soit ", "Etant donné ", "Étant donné ", "Quand ", "Lorsque ", "Et ", "Mais ")
_MOTS_DE_VERIFICATION = ("Alors ", "Donc ")

# La consigne d'usage vit ICI, dans la définition de l'outil, et non dans le prompt système : elle n'est envoyée que lorsque
# l'outil est proposé — le prompt (et son empreinte) d'un projet ordinaire restent ceux d'avant le lot.
DEFINITION = {
    "name": NOM_OUTIL,
    "description": (
        "Joue une suite d'ACTIONS (steps du catalogue, « Soit / Quand / Et ») dans un vrai navigateur, sur le bac à sable du "
        "projet remis à zéro avant et après, et rend l'adresse de la page d'ARRIVÉE et ses champs, boutons et liens. Une action "
        "(clic, envoi de formulaire) peut changer de page : tu ne peux pas le savoir sans la jouer. Avant d'écrire un scénario "
        "dont une action change de page, joue ses actions, puis écris la suite pour CETTE page, avec CES libellés. Si une action "
        "échoue à l'essai, corrige-la avant d'écrire — elle échouerait pareil à l'exécution. N'y mets AUCUN « Alors » : ce que "
        "le test vérifie vient de la spécification ; ce que tu n'as vu que pendant un essai est refusé sous un « Alors »."),
    "input_schema": {
        "type": "object",
        "properties": {"etapes": {
            "type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": MAX_ETAPES,
            "description": "Les lignes Gherkin des actions, dans l'ordre, mot-clé compris (ex. « Quand je clique sur le bouton "
                           "\"Ajouter\" »). Steps du catalogue uniquement."}},
        "required": ["etapes"],
    },
}


@dataclass
class EssaiBacASable:
    """Ce qu'il faut pour jouer un essai : remettre à zéro, et fabriquer un runner sur un dossier donné."""

    remettre_a_zero: Callable[[], None]            # lève si la remise à zéro n'est pas prouvée
    fabriquer_runner: Callable[[Path, dict], object]  # (dossier du .feature, variables d'environnement en plus) -> runner
    # L'application remise à zéro (origine) : l'essai et ses exécutions réelles s'excluent (`guardrails/bac_a_sable`).
    cle: str | None = None
    # La remise à zéro ferme les sessions de l'application : le navigateur d'OBSERVATION de l'agent doit repartir d'une
    # session neuve (il se reconnecte à l'observation suivante). Best-effort.
    apres_essai: Callable[[], None] | None = None
    # Appelé quand la remise à zéro FINALE échoue : laisse la marque durable qui retient les exécutions réelles.
    marquer_non_remis: Callable[[], None] | None = None
    essais_faits: int = 0
    tentatives: int = 0
    etat_laisse: bool = False
    journal: list[dict] = field(default_factory=list)
    # Les DONNÉES vues seulement pendant un essai (ni par l'exploration, ni par une observation en lecture), chacune avec le
    # texte d'où elle vient. `vus` : les jetons porteurs d'un chiffre (montant, numéro, date, compte) ; `textes` : les textes
    # des paramètres de l'adresse. Un « Alors » ne peut pas les citer sans que la spécification les dise
    # (`valeurs_tirees_de_l_essai`). Les NOMS de champs, de boutons, de liens et de pages n'y sont pas : ils disent où agir.
    vus: dict[str, str] = field(default_factory=dict)
    textes: dict[str, str] = field(default_factory=dict)
    # Lot PT-03 : les mêmes données, comme NOMBRES (valeur -> texte d'origine) — « 129.15 EUR » vu à l'essai ne devient pas
    # l'attendu « 129,15 € » d'un step qui compare des nombres.
    nombres: dict = field(default_factory=dict)
    # Tout ce que les essais ont montré (pour ne pas prendre, à l'essai suivant, un libellé déjà montré pour un libellé connu).
    montres: set[str] = field(default_factory=set)


def _outcome(observation: str, ok: bool = True) -> "ToolOutcome":
    from testpilot.generation.tools import ToolOutcome
    return ToolOutcome(observation=observation, ok=ok)


# ── Condition 4 : des actions, et rien d'autre ────────────────────────────────────────────────────────────


def _refus_des_etapes(etapes: list[str]) -> str:
    """Refus lisibles, pour le message rendu à l'agent. La GARANTIE est `_refus_de_structure` (lecture par Behave)."""
    if not etapes or len(etapes) > MAX_ETAPES:
        return f"entre 1 et {MAX_ETAPES} actions par essai"
    for ligne in etapes:
        texte = (ligne or "").strip()
        if len(texte.splitlines()) != 1:
            return "une action par ligne (aucun retour à la ligne dans une action)"
        if texte.startswith(_MOTS_DE_VERIFICATION):
            return (f"« {texte[:60]} » est une vérification : un essai ne joue que des ACTIONS. Ce que le test vérifie vient de la "
                    "spécification, pas de ce que tu observes")
        if not texte.startswith(_MOTS_D_ACTION):
            return f"« {texte[:60]} » ne commence pas par un mot-clé d'action (Soit, Quand, Et, Mais)"
    if (etapes[0] or "").strip().startswith(("Et ", "Mais ")):
        return "la première action commence par Soit ou Quand (« Et » hérite d'un step précédent)"
    return ""


def _texte_du_scenario(etapes: list[str]) -> str:
    return ("# language: fr\nFonctionnalité: Essai sur le bac à sable\n\n  Scénario: essai\n"
            + "".join(f"    {(ligne or '').strip()}\n" for ligne in etapes))


def _refus_de_structure(texte: str, attendues: int) -> str:
    """Le fichier qui SERA joué, relu par l'analyseur de Behave : exactement une action par ligne fournie, toutes de type
    `given`/`when`, sans tableau ni texte joint. Relecture du 2026-10-11 : Behave découpe aussi sur U+2028, U+0085, `\\x0b`… —
    un « Alors » glissé derrière un tel séparateur passait un contrôle fait ligne par ligne sur `\\n` et était joué."""
    from behave.parser import ParserError, parse_feature

    try:
        feature = parse_feature(texte, language="fr")
    except ParserError:
        return "ces lignes ne forment pas un scénario lisible"
    scenarios = list(feature.walk_scenarios(with_outlines=True)) if feature else []
    if len(scenarios) != 1 or getattr(feature, "background", None) is not None:
        return "un essai est un seul scénario, sans contexte"
    steps = list(scenarios[0].steps)
    if len(steps) != attendues:
        return f"une action par ligne, rien d'autre ({len(steps)} steps lus pour {attendues} ligne(s) fournie(s))"
    for step in steps:
        if step.step_type not in ("given", "when"):
            return (f"« {step.keyword} {step.name[:60]} » est une vérification : un essai ne joue que des ACTIONS. Ce que le test "
                    "vérifie vient de la spécification, pas de ce que tu observes")
        if step.table is not None or step.text:
            return "une action d'essai ne porte ni tableau ni texte joint"
    return ""


# ── Condition 4 : ce qui revient à l'agent ────────────────────────────────────────────────────────────────

_LIGNE_D_ERREUR = re.compile(r"^\s*(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Timeout|Interrupt))\s*(?::|$)")


def _type_d_erreur(echec) -> str:
    """Le TYPE de l'exception du step en échec — signal du runtime. Jamais son message : il cite ce que la page affichait
    (« aucun champ dans la ligne contenant "129,15 €" »), et un message rendu à l'agent devient un « attendu » possible."""
    texte = f"{getattr(echec, 'traceback_summary', '') or ''}\n{getattr(echec, 'raw', '') or ''}"
    types = [m.group(1) for m in map(_LIGNE_D_ERREUR.match, texte.splitlines()) if m]
    if types:
        return types[-1]
    return "AssertionError" if "ASSERT FAILED" in texte else "erreur"


def _normaliser(texte: str) -> str:
    """Espaces de toute sorte ramenés à une espace (insécable et fine comprises : la typographie française des montants),
    accents et casse pliés. Contre-relecture du 2026-10-11, reproduit de bout en bout : la page affichait « 129,15\u00a0€ »,
    le test citait « 129,15 € » avec une espace ordinaire — une comparaison exacte laissait passer la valeur recopiée."""
    plie = unicodedata.normalize("NFKC", texte or "")
    plie = "".join(c for c in unicodedata.normalize("NFD", plie) if unicodedata.category(c) != "Mn").casefold()
    return re.sub(r"\s+", " ", plie).strip()


_BORDS_DE_JETON = " ()[]{}<>:;,.!?«»\"'’“”€$£%*#=|/"


_NOMBRE = re.compile(r"\d+(?:[.,]\d+)*")


def _jetons_a_chiffres(texte: str) -> set[str]:
    """Les mots de `texte` qui portent un chiffre, ponctuation des bords retirée : « 129,15 », « cmd-0042 », « 3 » — et le
    NOMBRE qu'un mot renferme quand il est collé à autre chose (« payer:129,15 » → « 129,15 », « 3kg » → « 3 »,
    « cmd-0042 » → « 0042 »). Troisième relecture : un bouton `Payer:129,15€` laissait écrire « 129,15 € », un lien
    « Commande CMD-0042 » laissait écrire « 0042 ». D'un mot à plusieurs nombres (une date), seuls ceux d'au moins trois
    chiffres ou à décimales sont retenus : « 10 » et « 11 » d'une date bloqueraient n'importe quel compte."""
    jetons: set[str] = set()
    for mot in _normaliser(texte).split(" "):
        jeton = mot.strip(_BORDS_DE_JETON)
        if not any(c.isdigit() for c in jeton):
            continue
        jetons.add(jeton)
        nombres = _NOMBRE.findall(jeton)
        for nombre in nombres:
            if len(nombres) == 1 or len(nombre) >= 3:
                jetons.add(nombre)
    return jetons


# Une spécification écrit souvent un compte en toutes lettres (« deux lignes », « une commande », « aucun article ») ; le step
# qui le vérifie exige un chiffre. Sans cette table, un « 2 » de pagination vu à l'essai faisait refuser « compte 2 lignes » —
# l'agent n'avait aucune issue et renonçait à la vérification la plus forte (troisième relecture, reproduit).
_NOMBRES_EN_LETTRES = {"zero": "0", "aucun": "0", "aucune": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
                       "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10", "onze": "11", "douze": "12"}


# Lot PT-03 (revue du 2026-10-13) — depuis le step « le nombre affiché … vaut … », une valeur se compare comme un NOMBRE :
# l'agent qui voit « 129.15 EUR » à l'essai peut écrire « 129,15 € », le test réussit, et une garde qui compare des écritures
# ne voit rien. La garde compare donc AUSSI les valeurs. Elle n'en retire rien : un jeton refusé hier l'est toujours.
_NOMBRE_SEUL = re.compile(r"\d+(?:[.,]\d+)*")
# « 1 234,50 », « 1'234.50 » : coupés en deux jetons sinon.
_NOMBRE_GROUPE = re.compile(r"(?<![\d.,])\d{1,3}(?:[ '’]\d{3})+(?:[.,]\d+)?(?!\d)")


def _motifs_des_steps_qui_comparent_des_nombres() -> list:
    """Les steps de la bibliothèque marqués `@compare_des_nombres`, prêts à être rapprochés d'une phrase de test. Pour eux, la
    garde par valeur vaut aussi pour les petits entiers (« 7 » y EST « 7,00 »). Lus dans la bibliothèque à chaque appel —
    jamais une liste tenue ici — et rapprochés accents PLIÉS, comme Behave apparie (`_accent_matcher.py`)."""
    import parse as parse_lib
    from testpilot.generation import steps_library

    motifs = []
    for step in steps_library.catalogue():
        if step.compare_des_nombres:
            with contextlib.suppress(ValueError, IndexError):
                motifs.append(parse_lib.compile(_normaliser(step.label)))
    return motifs


def _compare_des_nombres(phrase: str, motifs: list) -> bool:
    plie = _normaliser(phrase)
    for motif in motifs:
        with contextlib.suppress(ValueError, IndexError):
            if motif.parse(plie) is not None:
                return True
    return False


def _valeur_significative(valeur: Decimal) -> bool:
    """Une valeur à décimales, ou d'au moins quatre chiffres. Un petit entier n'en est pas une : « Quantité 1,00 » vu à
    l'essai faisait refuser « compte 1 ligne » dans n'importe quel « Alors » (revue du 2026-10-13, faux refus reproduit)."""
    return valeur != valeur.to_integral_value() or abs(valeur) >= 1000


def _lectures(ecrit: str) -> list[str]:
    """Les lectures possibles d'un nombre écrit. « 1,234 » en a DEUX (mille deux cent trente-quatre, ou un virgule deux cent
    trente-quatre) : la garde ne devine pas, elle les retient toutes les deux."""
    brut = re.sub(r"[ '’]", "", ecrit)
    points, virgules = brut.count("."), brut.count(",")
    if not points and not virgules:
        return [brut]
    if points and virgules:
        decimal = "." if brut.rfind(".") > brut.rfind(",") else ","
        return [brut.replace("," if decimal == "." else ".", "").replace(decimal, ".")]
    separateur = "." if points else ","
    if brut.count(separateur) > 1:
        return [brut.replace(separateur, "")]
    entier, _, fraction = brut.partition(separateur)
    return [f"{entier}.{fraction}"] + ([entier + fraction] if len(fraction) == 3 else [])


def _valeurs_numeriques(texte: str) -> set[Decimal]:
    """Les NOMBRES que `texte` écrit, quelle que soit leur écriture : « 129,15 », « 129.15 » et « 129,150 » sont la même
    valeur ; « 1 234,50 » et « 1234.50 » aussi. Bâti sur `_jetons_a_chiffres` (même règle pour les dates : leurs petits
    morceaux ne comptent pas), plus les nombres à groupes de milliers séparés par des espaces."""
    ecrits = {j for j in _jetons_a_chiffres(texte) if _NOMBRE_SEUL.fullmatch(j)} | set(_NOMBRE_GROUPE.findall(_normaliser(texte)))
    valeurs: set[Decimal] = set()
    for ecrit in ecrits:
        for lecture in _lectures(ecrit):
            try:
                valeurs.add(Decimal(lecture))
            except InvalidOperation:
                continue
    return valeurs


def _jetons_de_la_specification(specification: str) -> set[str]:
    mots = (mot.strip(_BORDS_DE_JETON) for mot in _normaliser(specification).split(" "))
    return _jetons_a_chiffres(specification) | {_NOMBRES_EN_LETTRES[mot] for mot in mots if mot in _NOMBRES_EN_LETTRES}


def _deja_connus(annuaire, vus_a_l_essai: set[str]) -> tuple[set[str], set[str]]:
    """(libellés, morceaux d'adresse) que l'exploration ou une observation en LECTURE a déjà montrés — donc pas des résultats
    d'une action d'essai."""
    try:
        libelles = set(annuaire.tous("champ")) | set(annuaire.tous("bouton"))
        libelles |= set(annuaire.observes_session) - vus_a_l_essai
        morceaux = {m for route in annuaire.routes for m in route.split("/") if m}
    except (AttributeError, TypeError):
        return set(), set()
    return {x.strip() for x in libelles}, morceaux


_LONGUEUR_MINIMALE_D_UN_TEXTE = 4


def _noter_les_nouveautes(essai: "EssaiBacASable", etat: dict | None, annuaire, montres: set[str]) -> None:
    """Range dans `essai.vus` / `essai.textes` les DONNÉES que cet essai vient de montrer à l'agent : les jetons à chiffres des
    libellés nouveaux et tout ce que l'adresse d'arrivée porte (segments nouveaux, valeurs des paramètres, fragment —
    l'adresse entière est rendue à l'agent). Un texte de lien sans chiffre n'en est pas : « Retour » vu à l'essai faisait
    refuser « Aucun retour possible » (troisième relecture)."""
    if not etat:
        return
    libelles, morceaux = _deja_connus(annuaire, montres)
    for element in etat.get("elements") or []:
        for cle in ("nom", "texte"):
            source = str(element.get(cle) or "").strip()
            if not source or source in libelles:
                continue
            for jeton in _jetons_a_chiffres(source):
                essai.vus.setdefault(jeton, source)
            for valeur in _valeurs_numeriques(source):
                essai.nombres.setdefault(valeur, source)
    adresse = urlparse(str(etat.get("url") or ""))
    portes = [unquote(m) for m in adresse.path.split("/") if m and m not in morceaux]
    portes += [valeur for _cle, valeur in parse_qsl(adresse.query, keep_blank_values=False)]
    portes += [unquote(adresse.fragment)] if adresse.fragment else []
    for source in portes:
        for jeton in _jetons_a_chiffres(source):
            essai.vus.setdefault(jeton, f"l'adresse {adresse.path}")
        for valeur in _valeurs_numeriques(source):
            essai.nombres.setdefault(valeur, f"l'adresse {adresse.path}")
    for source in [valeur for _cle, valeur in parse_qsl(adresse.query)] + ([unquote(adresse.fragment)] if adresse.fragment else []):
        if len(_normaliser(source)) >= _LONGUEUR_MINIMALE_D_UN_TEXTE and not _jetons_a_chiffres(source):
            essai.textes.setdefault(_normaliser(source), f"l'adresse {adresse.path}")


def _tires_de(texte: str, essai: "EssaiBacASable", exigences: dict | None, *, toutes_les_valeurs: bool = False) -> list[str]:
    """Ce que `texte` cite et qui n'a été vu QU'À l'essai, la spécification ne le disant pas — chaque fois avec son origine."""
    specification = " ".join(str(v) for v in (exigences or {}).values())
    jetons_de_la_spec, spec_normalisee = _jetons_de_la_specification(specification), _normaliser(specification)
    tires = [f"« {jeton} » (vu à l'essai dans « {essai.vus[jeton][:60]} »)"
             for jeton in sorted(_jetons_a_chiffres(texte)) if jeton in essai.vus and jeton not in jetons_de_la_spec]
    # La même règle sur les VALEURS : un nombre vu à l'essai, que la spécification ne dit pas, écrit autrement dans le test.
    deja_refusees = {v for jeton in _jetons_a_chiffres(texte) if jeton in essai.vus and jeton not in jetons_de_la_spec
                     for v in _valeurs_numeriques(jeton)}
    valeurs_de_la_spec = _valeurs_numeriques(specification) | {Decimal(j) for j in jetons_de_la_spec if j.isascii() and j.isdigit()}
    # Les valeurs des jetons vus, plus celles relevées à l'essai dans le texte entier (« 1 234,50 », coupé en deux jetons).
    nombres_vus = {v: source for jeton, source in essai.vus.items() for v in _valeurs_numeriques(jeton)}
    nombres_vus.update(getattr(essai, "nombres", None) or {})
    # Portée : toute valeur pour le step qui compare des nombres (`toutes_les_valeurs`) ; ailleurs, les seules valeurs
    # significatives. Limite assumée, comme pour les motifs déguisés : une valeur CONVERTIE (« 1,5 kg » vu, « 1500 g » écrit)
    # n'est pas reconnue — la relecture humaine reste obligatoire (D23).
    for valeur in sorted(_valeurs_numeriques(texte)):
        if not (toutes_les_valeurs or _valeur_significative(valeur)):
            continue
        if valeur in nombres_vus and valeur not in valeurs_de_la_spec and valeur not in deja_refusees:
            tires.append(f"« {valeur} » (vu à l'essai dans « {nombres_vus[valeur][:60]} », écrit autrement)")
    normalise = _normaliser(texte)
    for vu, origine in essai.textes.items():
        if vu not in spec_normalisee and re.search(rf"(?<!\w){re.escape(vu)}(?!\w)", normalise):
            tires.append(f"« {vu} » (vu à l'essai dans « {origine[:60]} »)")
    return tires


def _texte_entier(step) -> str:
    """Tout ce qu'un step dit : sa phrase (guillemets ou non), son texte joint, les cellules de son tableau."""
    morceaux = [step.name or "", step.text or ""]
    if step.table is not None:
        morceaux += [" ".join(step.table.headings)] + [" ".join(ligne.cells) for ligne in step.table.rows]
    return " ".join(morceaux)


def valeurs_tirees_de_l_essai(feature, essai: "EssaiBacASable | None", exigences: dict | None) -> list[str]:
    """Ce que les « Alors » de `feature` (objet lu par l'analyseur de Behave — scénarios, exemples développés, contexte) citent
    et qui n'a été vu QUE pendant un essai, la spécification ne le disant pas. Condition 4 de D26, tenue à l'écriture : sans
    elle, l'agent pouvait jouer une action, lire « Payer 129,15 € » sur la page d'arrivée et l'écrire comme attendu — le test
    sortait `conforme` sur ce que l'application a montré, pas sur ce que la spécification annonce.

    Portée assumée : la recopie NATURELLE d'une donnée (un jeton à chiffres, un texte de lien, une valeur de l'adresse). Une
    valeur délibérément déguisée (motif `CMD-004[2]`, morceaux concaténés) n'est pas vue : la relecture humaine reste
    obligatoire (D23), et la source de chaque attendu (`spec` / `observé`) est l'objet du lot 8."""
    if essai is None or not (essai.vus or essai.textes) or feature is None:
        return []
    steps = list(getattr(getattr(feature, "background", None), "steps", None) or [])
    for scenario in feature.walk_scenarios():
        steps += list(scenario.steps)
    tires: list[str] = []
    motifs = _motifs_des_steps_qui_comparent_des_nombres()
    for step in steps:
        if step.step_type == "then":
            tires += _tires_de(_texte_entier(step), essai, exigences,
                               toutes_les_valeurs=_compare_des_nombres(step.name or "", motifs))
    return tires


def alors_qui_citent(feature_content: str, donnees_vues) -> list[tuple[str, list[str]]]:
    """(phrase du step, jetons cités) pour chaque « Alors » de ce Gherkin qui cite une donnée vue pendant un essai — QUE LA
    SPÉCIFICATION LA DISE OU NON. Sert au point de vigilance de la relecture (D23), pas au refus.

    Troisième relecture, reproduit de bout en bout : la spécification dit « total HT 107,93 €, total TTC 129,51 € », l'application
    fautive affiche le hors taxes à la place du TTC, l'essai montre « Payer 107,93 € », et « Total TTC est 107,93 € » passait
    la garde d'écriture — le nombre est bien dans la spécification, mais pas là où cet « Alors » l'attend. Aucune liste de
    jetons ne peut le voir : il faut savoir quelle phrase fonde quel attendu (lot 8). En attendant, un humain le voit."""
    from behave.parser import ParserError, parse_feature

    vues = {str(d) for d in (donnees_vues or [])}
    if not vues or not (feature_content or "").strip():
        return []
    try:
        feature = parse_feature(feature_content, language="fr")
    except ParserError:
        return []
    if feature is None:
        return []
    steps = list(getattr(getattr(feature, "background", None), "steps", None) or [])
    for scenario in feature.walk_scenarios():
        steps += list(scenario.steps)
    cites: list[tuple[str, list[str]]] = []
    for step in steps:
        communs = sorted(_jetons_a_chiffres(_texte_entier(step)) & vues) if step.step_type == "then" else []
        if communs and (step.name, communs) not in cites:
            cites.append((step.name, communs))
    return cites


def chaines_tirees_de_l_essai(chaines, essai: "EssaiBacASable | None", exigences: dict | None) -> list[str]:
    """Même règle pour les chaînes d'un fichier de steps généré qui peuvent servir un « Alors » écrit à la main."""
    if essai is None or not (essai.vus or essai.textes):
        return []
    return [tire for chaine in chaines for tire in _tires_de(chaine, essai, exigences)]


def _rendre(etat: dict | None, echec: dict | None, etapes: list[str], *, remis: bool) -> str:
    if remis:
        lignes = ["Essai joué sur le bac à sable (remis à zéro avant et après) — rien de ce qu'il a fait ne subsiste."]
    else:
        lignes = ["ATTENTION — essai joué, mais le bac à sable n'a PAS pu être remis à zéro ensuite : ce que l'essai a créé y est "
                  "peut-être encore. Plus aucun essai ne sera joué. Les exécutions de cette application sont retenues tant "
                  "qu'elle n'est pas remise à zéro. Signale-le dans ta réponse."]
    if echec:
        lignes.append(f"ÉCHEC à l'action « {echec.get('step') or '?'} » ({echec.get('type') or 'erreur'})"
                      + (f" — page à cet instant : {echec['url']}" if echec.get("url") else ""))
        lignes.append("Les actions suivantes n'ont pas été jouées. Corrige cette action (bonne page ? bon libellé ?) avant d'écrire.")
    else:
        lignes.append(f"Les {len(etapes)} action(s) ont réussi.")
    if etat and etat.get("url"):
        lignes.append(f"Page affichée à la fin : {etat['url']}")
        elements = etat.get("elements") or []
        lignes.append(f"{len(elements)} champ(s), bouton(s) ou lien(s) visible(s) :")
        for el in elements:
            type_ = f" (type={el['type']!r})" if el.get("type") else ""
            affiche = f" — texte affiché : « {el['texte']} »" if el.get("texte") else ""
            lignes.append(f"- {el.get('role', '?')} « {el.get('nom', '')} »{type_}{affiche}")
    else:
        lignes.append("La page finale n'a pas pu être lue.")
    lignes.append("Rappel : ces éléments te disent OÙ agir ; les valeurs attendues des « Alors » viennent de la spécification.")
    return "\n".join(lignes)


# ── L'outil ───────────────────────────────────────────────────────────────────────────────────────────────


def _remettre_a_zero_apres(essai: EssaiBacASable) -> bool:
    """Remise à zéro FINALE, reprise quelques fois (une indisponibilité d'une seconde ne doit pas laisser l'essai en place).
    Rend False si elle n'a jamais abouti — l'appelant le dit et laisse la marque durable."""
    for reprise in range(REPRISES_REMISE_A_ZERO):
        try:
            essai.remettre_a_zero()
            return True
        except Exception as exc:
            logger.warning("[essai] remise à zéro impossible APRÈS l'essai (tentative %d/%d) : %s",
                           reprise + 1, REPRISES_REMISE_A_ZERO, exc)
            if reprise + 1 < REPRISES_REMISE_A_ZERO:
                time.sleep(1.0)
    return False


def essayer_les_actions(ctx: "ToolContext", etapes: list[str]) -> "ToolOutcome":
    essai: EssaiBacASable | None = getattr(ctx, "essai", None)
    if essai is None:
        return _outcome(f"[{NOM_OUTIL}] indisponible : ce projet n'est pas déclaré bac à sable (calibration en écriture "
                        "autorisée ET adresse de remise à zéro renseignée dans ses réglages).", ok=False)
    essai.tentatives += 1
    if essai.essais_faits >= MAX_ESSAIS_PAR_GENERATION or essai.tentatives > MAX_TENTATIVES:
        return _outcome(f"[{NOM_OUTIL}] ESSAIS_EPUISES : plus aucun essai pour ce cas — écris le test avec ce que tu as observé.",
                        ok=False)
    # Deux contrôles, le second seul fait foi : le premier donne un message lisible, le second relit ce que Behave jouera.
    refus = _refus_des_etapes(etapes or []) or _refus_de_structure(_texte_du_scenario(etapes), len(etapes))
    if refus:
        return _outcome(f"[{NOM_OUTIL}] ESSAI_REFUSE : {refus}.", ok=False)

    # Lot PT-02d : l'essai reçoit les valeurs du jeu « Par défaut » — jamais `{{client}}` saisi tel quel dans l'application.
    texte = _texte_du_scenario(etapes)
    noms = getattr(ctx, "variables_de_test", frozenset())
    # Lot PT-02f : aucune variable permise (dernière à la corbeille) — un `{{…}}` ne serait remplacé par rien, et saisi tel
    # quel dans l'application (revue du 2026-10-15). Refusé, comme à l'écriture.
    if not noms and getattr(ctx, "controle_du_cas", False) and "{{" in texte:
        return _outcome(f"[{NOM_OUTIL}] ESSAI_REFUSE : aucune donnée de test n'est permise pour ce cas — écris la valeur.",
                        ok=False)
    if noms:
        from testpilot.generation import variables_de_test
        texte, manques = variables_de_test.texte_de_l_essai(texte, getattr(ctx, "valeurs_de_test", {}) or {}, noms)
        if manques:
            return _outcome(f"[{NOM_OUTIL}] ESSAI_REFUSE : {' ; '.join(manques[:5])}.", ok=False)

    dossier = Path(tempfile.mkdtemp(prefix="tp_essai_"))
    module = f"essai_{uuid.uuid4().hex[:8]}"
    fichier_etat = dossier / "etat.json"
    try:
        (dossier / f"{module}.feature").write_text(texte, encoding="utf-8")
        runner = essai.fabriquer_runner(dossier, {ESSAI_ETAT_FILE_ENV: str(fichier_etat)})
        a_blanc = runner.dry_run(module)
        if not a_blanc.success:
            inconnus = "; ".join(getattr(a_blanc, "undefined_steps", None) or []) or "voir le catalogue"
            if noms:   # la marche à blanc a lu le texte aux valeurs posées : l'agent relit `{{nom}}` (lot PT-02d)
                inconnus = variables_de_test.masquer(inconnus, getattr(ctx, "valeurs_de_test", {}) or {})
            return _outcome(f"[{NOM_OUTIL}] STEP_INCONNU : ces actions ne sont pas des steps du catalogue (ou sont ambiguës) : "
                            f"{inconnus}. Recopie les libellés de <bibliotheque_de_steps>.", ok=False)
        # Une remise à zéro pendant une exécution RÉELLE de l'application fausserait son verdict (jusqu'au faux vert sur un
        # scénario négatif) : l'essai entier — les deux remises à zéro comprises — est joué sous exclusion, ou n'est pas joué.
        remis = True
        try:
            with bac_a_sable.essai(essai.cle):
                try:
                    essai.remettre_a_zero()
                except Exception as exc:
                    logger.warning("[essai] remise à zéro impossible avant l'essai : %s", exc)
                    essai.essais_faits = MAX_ESSAIS_PAR_GENERATION  # elle ne marchera pas mieux au tour suivant
                    return _outcome(f"[{NOM_OUTIL}] REMISE_A_ZERO_IMPOSSIBLE : le bac à sable n'a pas pu être remis à zéro "
                                    f"({type(exc).__name__}) — aucun essai n'est joué, ni maintenant ni ensuite. Écris le test "
                                    "sans essai.", ok=False)
                essai.essais_faits += 1
                try:
                    resultat = runner.real_run(module)
                finally:
                    remis = _remettre_a_zero_apres(essai)
                    if not remis:  # l'essai a eu lieu et son état reste : on le dit, on le marque, plus aucun essai
                        essai.etat_laisse = True
                        essai.essais_faits = MAX_ESSAIS_PAR_GENERATION
                        if essai.marquer_non_remis is not None:
                            essai.marquer_non_remis()
                    if essai.apres_essai is not None:
                        try:
                            essai.apres_essai()
                        except Exception as exc:
                            logger.warning("[essai] réouverture de la session d'observation impossible : %s", exc)
        except bac_a_sable.BacASableOccupe as exc:
            essai.essais_faits += 1  # l'attente a déjà coûté : pas de relance en boucle
            return _outcome(f"[{NOM_OUTIL}] BAC_A_SABLE_OCCUPE : {exc} — aucun essai n'est joué (une remise à zéro fausserait "
                            "son résultat). Écris le test sans essai.", ok=False)
        etat = None
        try:
            etat = json.loads(fichier_etat.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            etat = None
        echecs = list(getattr(resultat, "failures", None) or [])
        echec = None
        if echecs:
            premier = echecs[0]
            echec = {"step": getattr(premier, "step_text", ""), "url": getattr(premier, "page_url", ""),
                     "type": _type_d_erreur(premier)}
        elif not getattr(resultat, "success", False):
            logger.warning("[essai] run non abouti : %s", (getattr(resultat, "raw_stderr", "") or "").strip()[:400])
            echec = {"step": "", "url": "", "type": "le harnais n'a pas abouti"}
        essai.journal.append({"etapes": list(etapes), "reussi": echec is None, "url": (etat or {}).get("url", ""),
                              "remis_a_zero": remis})
        annuaire = getattr(ctx, "annuaire", None)
        _noter_les_nouveautes(essai, etat, annuaire, essai.montres)
        essai.montres.update(str(el.get(k) or "").strip() for el in ((etat or {}).get("elements") or []) for k in ("nom", "texte"))
        if annuaire is not None and etat:
            # Lot VH-05 : les contrôles qui viennent d'être OBSERVÉS sur la page d'arrivée sont acceptés comme cibles d'ACTION
            # par le contrôle des littéraux — pas comme attendus d'un « Alors » (`valeurs_tirees_de_l_essai`).
            annuaire.observes_session.update(
                str(el[k]).strip() for el in (etat.get("elements") or []) for k in ("nom", "texte")
                if str(el.get(k) or "").strip())
        rendu = _rendre(etat, echec, list(etapes), remis=remis)
        if noms:   # lot PT-02d : l'agent relit `{{nom}}`, jamais la valeur posée (il la recopierait en dur)
            rendu = variables_de_test.masquer(rendu, getattr(ctx, "valeurs_de_test", {}) or {})
        return _outcome(rendu)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


# ── Construction : les conditions 1 et 2 de D26, décidées par le PROJET ─────────────────────────────────────


def adresse_de_remise_a_zero(base_url: str, chemin: str) -> str:
    """L'adresse COMPLÈTE de remise à zéro — un chemin de l'application du projet, ou une adresse absolue de la MÊME origine.
    Lève `ValueError` sinon : on ne « remet pas à zéro » une autre machine que celle qu'on teste."""
    base, chemin = (base_url or "").strip(), (chemin or "").strip()
    if not base or not chemin:
        raise ValueError("adresse du projet ou chemin de remise à zéro absent")
    cible = chemin if "://" in chemin else urljoin(base.rstrip("/") + "/", chemin.lstrip("/"))
    attendue, voulue = bac_a_sable.cle_d_application(base), bac_a_sable.cle_d_application(cible)
    if attendue is None or voulue is None or attendue != voulue or "@" in urlparse(cible).netloc:
        raise ValueError(f"« {chemin} » n'est pas une adresse de l'application du projet ({base})")
    return cible


def adresse_declaree(base_url: str, declaree: str) -> str:
    """L'adresse de remise à zéro DÉCLARÉE par le porteur, si elle vaut encore pour l'adresse actuelle du projet. La déclaration
    est enregistrée complète (schéma, hôte, port) : un projet dont l'adresse a changé depuis — recette devenue production —
    n'est plus un bac à sable tant que le porteur ne l'a pas redéclaré. Lève `ValueError` sinon."""
    if "://" not in (declaree or ""):
        raise ValueError("déclaration absente ou incomplète")
    return adresse_de_remise_a_zero(base_url, declaree)


def construire(projet: dict | None, dry_runner, connector=None) -> EssaiBacASable | None:
    """Le mode « exécuter puis écrire » de CE projet, ou `None` — auquel cas l'outil n'est pas proposé à l'agent.

    Exige (D26) : calibration en écriture AUTORISÉE par le projet, adresse de remise à zéro DÉCLARÉE pour l'adresse actuelle,
    connecteur `web` (première version : Odoo n'a pas encore de remise à zéro), et un runner réel. Les essais tournent sans
    repli par le modèle de langage (D33) : ils ne coûtent aucun appel LLM."""
    from testpilot.execution.behave_result import SANS_REPLI_ENV

    projet = projet or {}
    if not ia_peut_ecrire(projet) or (projet.get("connector_type") or "").lower() != "web":
        return None
    try:
        url = adresse_declaree(str(projet.get("base_url") or ""), str(projet.get("bac_a_sable_reset") or ""))
    except ValueError:
        return None
    cle = bac_a_sable.cle_d_application(url)
    connexion = getattr(dry_runner, "connection", None)
    if cle is None or not isinstance(connexion, dict):
        return None

    def fabriquer(dossier: Path, variables: dict):
        from testpilot.execution.behave_runner import BehaveRunner

        return BehaveRunner(connection={**connexion, SANS_REPLI_ENV: "1", **variables}, generated_dir=dossier,
                            project_id=getattr(dry_runner, "project_id", None),
                            connector_type=getattr(dry_runner, "connector_type", None),
                            profil_instance=getattr(dry_runner, "profil_instance", None),
                            real_timeout=DELAI_ESSAI_S, essai=True)

    fermer = getattr(connector, "disconnect", None)
    return EssaiBacASable(remettre_a_zero=lambda: bac_a_sable.remettre_a_zero_et_demarquer(cle, url),
                          fabriquer_runner=fabriquer, cle=cle,
                          apres_essai=fermer if callable(fermer) else None,
                          marquer_non_remis=lambda: bac_a_sable.marquer_non_remis(cle, url))
