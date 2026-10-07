"""Lot Q2-d — ORCHESTRATEUR du banc d'agents web : un test GÉNÉRÉ détecte-t-il un défaut, sans accuser une appli saine ?

    python scripts/banc_agents.py --a-sec                           # défaut : valide la configuration, aucun LLM, aucun navigateur
    python scripts/banc_agents.py --reel --plafond-cout 5 --essais 3  # ⚠️ LLM + navigateur RÉELS : accord du porteur requis

Principe (article d'Anthropic « Demystifying evals for AI agents », `docs/SOURCES-DE-REFERENCE-AGENTS.md` §1) : jeu ÉQUILIBRÉ
(application saine ET défectueuse), évaluateurs DÉTERMINISTES (l'attendu est écrit par un humain AVANT tout run, jamais
déduit d'un résultat), on évalue le RÉSULTAT (le statut obtenu), pas le chemin pris par l'agent.

Pour chaque spec de `specs/banc_local/` et chaque essai t ∈ [1..k] :

1. UNE génération du test, sur l'application SAINE (le seul poste de coût LLM, une fois par essai) ;
2. le MÊME test généré (mêmes fichiers, empreinte sha256 consignée) est joué sur l'application saine PUIS sur chaque
   variante défectueuse que `attendus.yaml` liste pour ce cas, l'application étant réinitialisée avant chaque jeu ;
3. chaque couple (cas, variante) compare le statut obtenu à l'attendu et alimente `banc_stats` : pass@1, pass@k,
   pass^k, faux verts, faux rouges, non concluants à part, coût par cas (USD et EUR) ;
4. sortie : `docs/mesures/banc-agents-<date>.{md,json}` (échantillon, intervalles de Wilson, « non mesuré » si n = 0).

Ce module est PUR dans sa partie orchestration : il reçoit `generer(spec, essai) -> Artefacts` et
`jouer(artefacts, variante) -> Jeu` (et `cout`), si bien que TOUS ses tests utilisent des doublures — ni LLM, ni navigateur,
ni réseau. Les adaptateurs réels (génération par le moteur de `qualify_campaign_pilot`, jeu par `BehaveRunner` + `Executor`
+ `derive_verdict` comme `banc_mesure.executer_cas`, application locale de `banc/app_web/`) ne s'activent qu'avec `--reel`.

Code de sortie : 0 rien à signaler ; 1 au moins un FAUX VERT (variante défectueuse, attendu non_conforme, obtenu conforme) ;
2 configuration invalide (attendus incohérents, hôte refusé, arguments) ; 3 campagne INCOMPLÈTE (plafond de coût atteint)
ou porte non mesurée (aucun jeu concluant sur une variante défectueuse : « non mesuré » n'est jamais un vert).

⚠️ Une campagne réelle COÛTE de l'argent : elle n'est lancée que sur accord explicite du porteur, jamais par la CI ni par
un test. Le plafond de coût (`--plafond-cout`, en dollars) est OBLIGATOIRE en mode réel et appliqué EN AMONT : aucun essai
n'est lancé quand le cumul plus le plus cher essai déjà observé le dépasserait.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
sys.path.insert(0, str(RACINE))

import banc_stats as stats  # noqa: E402  (pur : Wilson, pass@k, faux verts…)

SPECS = RACINE / "specs" / "banc_local"
ATTENDUS = SPECS / "attendus.yaml"
APPS = SPECS / "apps.yaml"
CAMPAGNE = RACINE / "scripts" / "qualify_campaign_pilot.py"
SORTIE = RACINE / "docs" / "mesures"
NOM_DE_L_APP = "boutique_locale"
MODULE_DU_BANC = "Banc agents web"
SUFFIXE_DE_TITRE = "(banc d'agents web)"

VARIANTE_SAINE = stats.VARIANTE_SAINE
# `attendus.yaml` parle en statuts de LECTURE (comme `specs/banc/attendus.yaml`) ; `banc_stats` en verdicts fonctionnels.
STATUT_VERS_VERDICT = {"passed": "conforme", "failed": "non_conforme"}
HOTES_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})

# Coût d'une génération, pour le BUDGET affiché avant un run réel et l'arrêt en amont du tout premier essai (aucun essai
# observé = aucun maximum connu). Source : `docs/mesures/banc-*-generation*.json`, I6 = 0,100 à 0,124 $ par cas sur 7
# campagnes ODOO (15 cas chacune). AUCUNE mesure sur le connecteur web : 0,15 $ est une borne prudente, pas une mesure,
# et le rapport le dit. Le coût réel remplace cette valeur dès le premier essai (on retient le plus cher observé).
COUT_ESTIME_ESSAI_USD = 0.15


class ConfigurationInvalide(ValueError):
    """La configuration du banc est incohérente : on REFUSE de mesurer plutôt que de laisser un cas sortir du calcul."""


class AttenduIncoherent(ConfigurationInvalide):
    """Un attendu qui ne peut alimenter ni les faux verts ni les faux rouges (polarité ou valeur impossible)."""


class ArretCampagne(RuntimeError):
    """Levée par `generer` quand la campagne ne doit PAS continuer (crédits épuisés, plafond du moteur) : l'essai n'est
    pas retenu — un manque de crédits n'est pas un échec de l'agent (même règle que `qualify_campaign_pilot`)."""


# ── Attendus : écrits par un humain, validés, jamais déduits ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Attendu:
    """Ce qu'un humain a écrit AVANT tout run : sur `variante`, le cas `cas` doit être `attendu` (conforme / non_conforme).

    La polarité est vérifiée à la CONSTRUCTION. Sans cela, un attendu `conforme` sous un défaut (ou `non_conforme` sur la
    saine) ne serait ni un faux vert ni un faux rouge pour `banc_stats` : il sortirait du calcul en silence (écart relevé
    par le lot Q2-a). Ici il est refusé, jamais ignoré.
    """

    cas: str
    variante: str
    attendu: str

    def __post_init__(self) -> None:
        if self.attendu not in stats.VERDICTS_CONCLUANTS:
            raise AttenduIncoherent(
                f"{self.variante}/{self.cas} : attendu {self.attendu!r} impossible "
                f"(admis : {', '.join(stats.VERDICTS_CONCLUANTS)})"
            )
        if self.variante == VARIANTE_SAINE and self.attendu != "conforme":
            raise AttenduIncoherent(
                f"{self.cas} : sur l'application saine l'attendu ne peut être que `conforme` (reçu {self.attendu!r}) — "
                "sinon il ne compterait ni comme faux rouge ni comme succès"
            )
        if self.variante != VARIANTE_SAINE and self.attendu != "non_conforme":
            raise AttenduIncoherent(
                f"{self.variante}/{self.cas} : sous un défaut l'attendu ne peut être que `non_conforme` (reçu "
                f"{self.attendu!r}) ; un cas que le défaut ne concerne pas n'est PAS listé (« hors périmètre »)"
            )


def lire_attendus(brut: Mapping) -> tuple[list[Attendu], list[str]]:
    """Les `Attendu` de `attendus.yaml` (`sain:` et `defauts:`) et les problèmes de FORME rencontrés.

    Un statut inconnu ou une polarité impossible est un problème rapporté, jamais un attendu ignoré.
    """
    attendus: list[Attendu] = []
    problemes: list[str] = []

    def ajouter(cas: str, variante: str, statut) -> None:
        verdict = STATUT_VERS_VERDICT.get(statut)
        if verdict is None:
            problemes.append(f"{variante}/{cas} : statut attendu inconnu {statut!r} (admis : passed, failed)")
            return
        try:
            attendus.append(Attendu(cas, variante, verdict))
        except AttenduIncoherent as erreur:
            problemes.append(str(erreur))

    sain = brut.get("sain")
    if not isinstance(sain, Mapping) or not sain:
        problemes.append("section `sain:` absente ou vide (le jeu doit être ÉQUILIBRÉ : saine ET défectueuses)")
    else:
        for cas, statut in sain.items():
            ajouter(str(cas), VARIANTE_SAINE, statut)
    defauts = brut.get("defauts") or {}
    if not isinstance(defauts, Mapping):
        problemes.append("section `defauts:` illisible (un dictionnaire code -> cas attendu)")
        defauts = {}
    for code, cas_map in defauts.items():
        if not isinstance(cas_map, Mapping) or not cas_map:
            problemes.append(f"défaut {code} : aucun cas listé (un défaut sans cas n'est jamais exercé)")
            continue
        for cas, statut in cas_map.items():
            ajouter(str(cas), str(code), statut)
    return attendus, problemes


def problemes_attendus(
    specs: Iterable[str], attendus: Iterable[Attendu], defauts_connus: Iterable[str]
) -> list[str]:
    """Incohérences entre specs, attendus et défauts connus de l'application (liste vide = cohérent).

    - cas SANS attendu sur la saine : il ne pourrait ni confirmer le jeu équilibré ni mesurer un faux rouge ;
    - attendu pour un cas SANS spec ;
    - code de défaut INCONNU de l'application (faute de frappe : le défaut ne serait jamais activé, le cas « manquerait »
      le défaut à tort) ;
    - défaut connu mais listé par AUCUN cas (jamais exercé : « non mesuré » déguisé en absence de problème) ;
    - même (cas, variante) écrit deux fois.
    """
    specs = list(specs)
    attendus = list(attendus)
    connus = set(defauts_connus)
    problemes: list[str] = []
    cas_sains = {a.cas for a in attendus if a.variante == VARIANTE_SAINE}
    for cas in specs:
        if cas not in cas_sains:
            problemes.append(f"cas sans attendu sur l'application saine : {cas}")
    for a in attendus:
        if a.cas not in set(specs):
            problemes.append(f"{a.variante}/{a.cas} : attendu pour un cas qui n'a pas de spec")
        if a.variante != VARIANTE_SAINE and a.variante not in connus:
            problemes.append(
                f"{a.variante}/{a.cas} : code de défaut inconnu de l'application (connus : {', '.join(sorted(connus))})"
            )
    for code in sorted(connus - {a.variante for a in attendus}):
        problemes.append(f"défaut {code} : aucun cas ne le liste (jamais exercé)")
    doublons = Counter((a.cas, a.variante) for a in attendus)
    for (cas, variante), nombre in sorted(doublons.items()):
        if nombre > 1:
            problemes.append(f"{variante}/{cas} : attendu écrit {nombre} fois")
    return problemes


def variantes_de(cas: str, attendus: Iterable[Attendu]) -> list[str]:
    """La saine d'abord, puis les défauts que `attendus` liste pour ce cas, dans l'ordre d'écriture (déterministe)."""
    codes = [a.variante for a in attendus if a.cas == cas and a.variante != VARIANTE_SAINE]
    return [VARIANTE_SAINE, *dict.fromkeys(codes)]


# ── Configuration sur disque (specs, attendus, manifeste) ────────────────────────────────────────────────


def charger_yaml(chemin: Path) -> dict:
    import yaml

    return yaml.safe_load(Path(chemin).read_text(encoding="utf-8")) or {}


def charger_specs(dossier: Path = SPECS) -> dict[str, dict]:
    """`{slug: document métier}` lu DÉTERMINISTEMENT dans `specs/banc_local/*.md` (aucun LLM)."""
    from banc_generation import metier_depuis_spec

    specs: dict[str, dict] = {}
    for chemin in sorted(Path(dossier).glob("*.md")):
        metier = metier_depuis_spec(chemin.read_text(encoding="utf-8"))
        metier["title"] = metier["title"].removesuffix(SUFFIXE_DE_TITRE).strip()
        specs[chemin.stem] = metier
    return specs


def specs_contenant_un_mot_de_passe(dossier: Path, mots_de_passe: Iterable[str]) -> list[str]:
    """Specs qui écrivent un mot de passe du manifeste en clair.

    Mesuré le 2026-10-06 (banc web, phase 1) : le harnais remplace tout mot de passe du projet par `[secret]` dans ce que
    voit l'IA ; une spec qui l'écrit lui fait saisir `[secret]` dans le champ, l'application refuse à juste titre, et le
    verdict accuse une application saine. Le mot de passe vit dans la connexion du projet, jamais dans une spec.
    """
    secrets = {str(m) for m in mots_de_passe if m}
    return sorted(
        chemin.stem
        for chemin in Path(dossier).glob("*.md")
        if any(secret in chemin.read_text(encoding="utf-8") for secret in secrets)
    )


@dataclass
class Configuration:
    specs: dict[str, dict]
    attendus: list[Attendu]
    defauts_connus: list[str]
    app: dict


def defauts_du_catalogue() -> list[str]:
    """Les défauts que l'application SAIT injecter : la vérité de `banc/app_web/defauts.py`, jamais une liste recopiée."""
    from banc.app_web import defauts

    return list(defauts.CODES)


def charger_configuration(
    dossier_specs: Path = SPECS,
    chemin_attendus: Path = ATTENDUS,
    chemin_apps: Path = APPS,
    defauts_connus: Sequence[str] | None = None,
) -> Configuration:
    """Charge ET valide : lève `ConfigurationInvalide` avec TOUS les problèmes, jamais un seul à la fois."""
    problemes: list[str] = []
    for chemin in (Path(dossier_specs), Path(chemin_attendus), Path(chemin_apps)):
        if not chemin.exists():
            problemes.append(f"fichier ou dossier introuvable : {chemin}")
    if problemes:
        raise ConfigurationInvalide(" ; ".join(problemes))
    connus = list(defauts_du_catalogue() if defauts_connus is None else defauts_connus)
    specs = charger_specs(dossier_specs)
    if not specs:
        raise ConfigurationInvalide(f"aucune spec dans {dossier_specs}")
    attendus, problemes = lire_attendus(charger_yaml(chemin_attendus))
    problemes += problemes_attendus(specs, attendus, connus)
    apps = (charger_yaml(chemin_apps).get("apps") or {})
    app = apps.get(NOM_DE_L_APP)
    if not app:
        problemes.append(f"application « {NOM_DE_L_APP} » absente de {chemin_apps}")
        app = {}
    else:
        declares = set(app.get("defauts") or [])
        if declares != set(connus):
            problemes.append(
                "défauts du manifeste `apps.yaml` différents du catalogue de l'application : "
                f"{sorted(declares ^ set(connus))}"
            )
        mots = [c.get("mot_de_passe") for c in app.get("comptes") or []]
        for slug in specs_contenant_un_mot_de_passe(dossier_specs, mots):
            problemes.append(f"spec {slug} : contient un mot de passe du manifeste (il vit dans la connexion du projet)")
    if problemes:
        raise ConfigurationInvalide(" ; ".join(problemes))
    return Configuration(specs=specs, attendus=attendus, defauts_connus=connus, app=app)


# ── Verdict d'un jeu, empreintes ─────────────────────────────────────────────────────────────────────────


def verdict_du_banc(execution: str | None, fonctionnel: str | None) -> str:
    """Les deux axes du verdict de production → UN des verdicts de `banc_stats`.

    Même ordre que `statut_de_test` (le fonctionnel prime), mais PLUS STRICT sur un point : une exécution réussie sans
    verdict fonctionnel est `indetermine`, jamais `conforme` — un banc qui mesure les faux verts ne doit pas fabriquer
    lui-même un vert que le verdict n'a pas rendu. Sans signal reconnu : `technical_error`, jamais un succès.
    """
    if fonctionnel == "conforme":
        return "conforme"
    if fonctionnel == "non_conforme":
        return "non_conforme"
    if execution == "blocked":
        return "blocked"
    if execution == "technical_error":
        return "technical_error"
    if execution == "success" or fonctionnel in ("indetermine", "donnee_invalide"):
        return "indetermine"
    return "technical_error"


def empreinte(contenu: str | bytes) -> str:
    octets = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
    return hashlib.sha256(octets).hexdigest()


@dataclass
class Artefacts:
    """Ce que produit UNE génération : les fichiers du test (nom → contenu), son coût, et si elle est jouable."""

    cas: str
    essai: int
    fichiers: dict[str, str] = field(default_factory=dict)
    cout_usd: float | None = 0.0  # None = coût NON consigné (jamais compté comme 0)
    genere_ok: bool = True  # génération réussie ET essai à blanc passé
    erreur: str = ""
    module: str = ""

    @property
    def empreintes(self) -> dict[str, str]:
        return {nom: empreinte(contenu) for nom, contenu in sorted(self.fichiers.items())}


@dataclass
class Jeu:
    """Le résultat d'UN jeu du test sur une variante : le verdict du banc, et les empreintes des fichiers RÉELLEMENT joués."""

    verdict: str
    cause: str = ""
    detail: str = ""
    duree: float | None = None
    empreintes: dict[str, str] | None = None  # None = non rapportées (le rapport le dit)


@dataclass
class Observation:
    """Un couple (cas, variante) d'UN essai : l'attendu écrit par un humain contre l'obtenu."""

    cas: str
    variante: str
    essai: int
    attendu: str
    obtenu: str
    cause: str = ""
    detail: str = ""
    duree: float | None = None
    empreinte_ok: bool | None = None  # vrai/faux = vérifiée ; None = non rapportée


@dataclass
class EssaiConsigne:
    cas: str
    essai: int
    genere: bool
    erreur: str
    cout_usd: float | None
    empreintes: dict[str, str]


@dataclass
class Campagne:
    k: int
    cas: list[str]
    essais: list[EssaiConsigne] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    interrompue: str = ""
    essais_prevus: int = 0


# ── Plafond de coût, en amont ────────────────────────────────────────────────────────────────────────────


def cout_retenu_pour_le_plafond(cout: float | None, cout_max_observe: float, cout_estime: float) -> float:
    """Ce qu'un essai ajoute au cumul du plafond : son coût, ou le PIRE connu quand il n'est pas consigné.

    Revue Q2-d : un essai dont la génération plante après avoir dépensé (aucun `campagne.json` n'est écrit avant la fin du
    moteur) n'a pas de coût consigné ; le compter pour 0 laisserait la campagne dépasser le plafond sans jamais s'arrêter.
    Le rapport, lui, garde « non consigné » (jamais 0).
    """
    return max(cout_max_observe, cout_estime) if cout is None else cout


def verifier_bornes_de_cout(plafond_usd: float | None, cout_estime_essai: float) -> None:
    """Un plafond NaN/infini/négatif ou une estimation NaN/négative rendraient l'arrêt en amont inopérant (comparaisons fausses)."""
    import math

    if plafond_usd is not None and not (math.isfinite(plafond_usd) and plafond_usd >= 0):
        raise ConfigurationInvalide(f"plafond de coût invalide : {plafond_usd!r} (fini et >= 0 attendu)")
    if not (math.isfinite(cout_estime_essai) and cout_estime_essai >= 0):
        raise ConfigurationInvalide(f"coût estimé par essai invalide : {cout_estime_essai!r} (fini et >= 0 attendu)")


def raison_d_arret(
    cumul: float, cout_max_observe: float, plafond: float | None, cout_estime: float = 0.0
) -> str:
    """Pourquoi NE PAS lancer le prochain essai, ou `''`. Appliqué AVANT chaque essai, jamais après.

    Le coût du prochain essai est inconnu d'avance : on retient le PLUS CHER déjà observé (à défaut, `cout_estime`, pour
    le tout premier). Un essai encore plus cher que tous les précédents reste possible : limite documentée, et le moteur
    de génération reçoit en plus le reste du budget (`--max-cost-usd`).
    """
    if plafond is None:
        return ""
    if cumul >= plafond:
        return f"cumul {cumul:.3f} $ >= plafond {plafond:.3f} $"
    prevu = max(cout_max_observe, cout_estime)
    if cumul + prevu > plafond:
        return f"cumul {cumul:.3f} $ + essai le plus cher attendu {prevu:.3f} $ > plafond {plafond:.3f} $"
    return ""


# ── Orchestration (PURE : `generer`, `jouer`, `cout` sont injectés) ──────────────────────────────────────


def _en_jeu(valeur) -> Jeu:
    if isinstance(valeur, Jeu):
        return valeur
    if isinstance(valeur, str):
        return Jeu(verdict=valeur)
    raise TypeError(f"`jouer` doit rendre un Jeu ou un verdict, pas {type(valeur).__name__}")


def executer_campagne(
    specs: Sequence[str],
    attendus: Sequence[Attendu],
    k: int,
    generer: Callable[[str, int], Artefacts],
    jouer: Callable[[Artefacts, str], Jeu | str],
    *,
    defauts_connus: Iterable[str],
    cout: Callable[[Artefacts], float | None] | None = None,
    plafond_usd: float | None = None,
    cout_estime_essai: float = 0.0,
    reel: bool = False,
    journal: Callable[[str], None] = lambda _message: None,
) -> Campagne:
    """Joue la campagne : k essais par cas, UNE génération par (cas, essai), jouée sur la saine et chaque défaut listé.

    L'ordre est ESSAI par essai (tous les cas à l'essai 1, puis à l'essai 2…) : si le plafond de coût arrête la campagne,
    pass@1 reste mesuré sur le corpus ENTIER au lieu d'un pass@3 sur la moitié des cas.

    Ce qui n'est jamais fait en silence : un jeu qui lève, un verdict inconnu, une empreinte divergente deviennent des
    `technical_error` consignés (+ anomalie dans le rapport) ; une génération échouée consigne ses jeux en
    `technical_error` au lieu de les retirer du dénominateur ; un attendu incohérent lève `ConfigurationInvalide`.
    """
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ConfigurationInvalide(f"k doit être un entier >= 1 (reçu {k!r})")
    verifier_bornes_de_cout(plafond_usd, cout_estime_essai)
    if reel and plafond_usd is None:
        raise ConfigurationInvalide("plafond de coût OBLIGATOIRE en mode réel : une génération coûte de l'argent")
    specs = list(specs)
    attendus = list(attendus)
    problemes = problemes_attendus(specs, attendus, defauts_connus)
    if problemes:
        raise ConfigurationInvalide("attendus incohérents : " + " ; ".join(problemes))
    mesurer_cout = cout or (lambda artefacts: artefacts.cout_usd)
    attendu_de = {(a.cas, a.variante): a.attendu for a in attendus}

    campagne = Campagne(k=k, cas=specs, essais_prevus=k * len(specs))
    cumul = cout_max = 0.0
    for essai in range(1, k + 1):
        for cas in specs:
            raison = raison_d_arret(cumul, cout_max, plafond_usd, cout_estime_essai)
            if raison:
                campagne.interrompue = f"plafond de coût : {raison} (avant {cas}, essai {essai})"
                journal(f"ARRÊT avant {cas} essai {essai} : {raison}")
                return campagne
            variantes = variantes_de(cas, attendus)
            try:
                artefacts = generer(cas, essai)
            except ArretCampagne as arret:
                campagne.interrompue = f"arrêt demandé par la génération : {arret} (avant {cas}, essai {essai})"
                return campagne
            except Exception as exc:  # le harnais est tombé : essai consigné, jamais un succès ni un retrait muet
                artefacts = Artefacts(cas, essai, cout_usd=None, genere_ok=False,
                                      erreur=f"{type(exc).__name__}: {exc}")
                campagne.anomalies.append(f"{cas} essai {essai} : `generer` a levé {artefacts.erreur}")
            cout_essai = mesurer_cout(artefacts)
            cumul += cout_retenu_pour_le_plafond(cout_essai, cout_max, cout_estime_essai)
            if cout_essai is not None:
                cout_max = max(cout_max, cout_essai)
            else:
                campagne.anomalies.append(f"{cas} essai {essai} : coût de génération non consigné (compté au PIRE connu dans "
                                          "le cumul du plafond, mais « non consigné » dans le rapport — jamais 0)")
            jouable = artefacts.genere_ok and bool(artefacts.fichiers)
            campagne.essais.append(EssaiConsigne(cas, essai, jouable, artefacts.erreur, cout_essai,
                                                 artefacts.empreintes if jouable else {}))
            journal(f"{cas} essai {essai} : {'généré' if jouable else 'GÉNÉRATION ÉCHOUÉE'} "
                    f"({'coût inconnu' if cout_essai is None else f'{cout_essai:.3f} $'})")
            for variante in variantes:
                attendu = attendu_de[(cas, variante)]
                if not jouable:
                    campagne.observations.append(Observation(
                        cas, variante, essai, attendu, "technical_error",
                        cause="generation_echouee", detail=artefacts.erreur or "aucun fichier généré"))
                    continue
                campagne.observations.append(
                    _jouer_une_variante(jouer, artefacts, variante, essai, attendu, campagne.anomalies))
                derniere = campagne.observations[-1]
                journal(f"  {variante:<24} attendu {attendu:<13} obtenu {derniere.obtenu}")
    return campagne


def _jouer_une_variante(jouer, artefacts: Artefacts, variante: str, essai: int, attendu: str,
                        anomalies: list[str]) -> Observation:
    """UN jeu, avec toutes les protections : exception, verdict inconnu, empreinte divergente."""
    cas = artefacts.cas
    try:
        jeu = _en_jeu(jouer(artefacts, variante))
    except Exception as exc:
        return Observation(cas, variante, essai, attendu, "technical_error", cause="jeu_en_exception",
                           detail=f"{type(exc).__name__}: {exc}"[:300])
    if jeu.verdict not in stats.VERDICTS:
        anomalies.append(f"{cas} essai {essai} sur {variante} : verdict inconnu {jeu.verdict!r} (rendu en technical_error)")
        return Observation(cas, variante, essai, attendu, "technical_error", cause="verdict_inconnu",
                           detail=str(jeu.verdict)[:200], duree=jeu.duree)
    empreinte_ok = None if jeu.empreintes is None else jeu.empreintes == artefacts.empreintes
    if empreinte_ok is False:
        # Le test joué n'est PAS celui qui a été généré : la comparaison entre variantes ne vaut plus rien. Le verdict est
        # écarté (jamais compté, pas même comme vert) et la divergence est dite.
        anomalies.append(f"{cas} essai {essai} sur {variante} : empreintes jouées ≠ empreintes générées "
                         "(jeu écarté, rendu en technical_error)")
        return Observation(cas, variante, essai, attendu, "technical_error", cause="empreinte_divergente",
                           detail=f"verdict ignoré : {jeu.verdict}", duree=jeu.duree, empreinte_ok=False)
    return Observation(cas, variante, essai, attendu, jeu.verdict, cause=jeu.cause, detail=jeu.detail,
                       duree=jeu.duree, empreinte_ok=empreinte_ok)


# ── Indicateurs ──────────────────────────────────────────────────────────────────────────────────────────


def _essais_par_cas(campagne: Campagne, reussi: Callable[[list[Observation], EssaiConsigne], bool]) -> dict[str, list[bool]]:
    """`cas -> [bool par essai, dans l'ordre joué]` pour `banc_stats.pass_*`."""
    par_cas: dict[str, list[bool]] = {}
    for essai in sorted(campagne.essais, key=lambda e: (e.cas, e.essai)):
        observations = [o for o in campagne.observations if o.cas == essai.cas and o.essai == essai.essai]
        par_cas.setdefault(essai.cas, []).append(reussi(observations, essai))
    return par_cas


def _reussi_execution(observations: list[Observation], essai: EssaiConsigne) -> bool:
    """Le test généré s'exécute SANS ERREUR TECHNIQUE sur l'application saine (le sens de pass@1 du brief).

    `blocked` et `technical_error` ne sont pas un succès ; `indetermine` n'est pas une erreur technique (il est compté à
    part dans les non concluants). Génération échouée = échec.
    """
    if not essai.genere:
        return False
    sain = next((o for o in observations if o.variante == VARIANTE_SAINE), None)
    return sain is not None and sain.obtenu not in ("technical_error", "blocked")


def _reussi_resultat(observations: list[Observation], essai: EssaiConsigne) -> bool:
    """Le RÉSULTAT est juste partout : chaque variante jouée donne EXACTEMENT l'attendu (non concluant = échec)."""
    return essai.genere and bool(observations) and all(o.obtenu == o.attendu for o in observations)


def calculer_indicateurs(campagne: Campagne, taux_eur_usd: float | None = None) -> dict:
    """Tous les chiffres du rapport, via `banc_stats` (jamais recalculés ici). Rien mesuré → `None`, pas 0."""
    k = campagne.k
    enregistrements = [
        {"cas": o.cas, "variante": o.variante, "attendu": o.attendu, "obtenu": o.obtenu}
        for o in campagne.observations
    ]
    exec_par_cas = _essais_par_cas(campagne, _reussi_execution)
    res_par_cas = _essais_par_cas(campagne, _reussi_resultat)

    non_concluants = Counter(o.obtenu for o in campagne.observations if o.obtenu in stats.VERDICTS_NON_CONCLUANTS)
    par_defaut: dict[str, dict] = {}
    for code in sorted({o.variante for o in campagne.observations if o.variante != VARIANTE_SAINE}):
        obs = [o for o in campagne.observations if o.variante == code]
        concluantes = [o for o in obs if o.obtenu in stats.VERDICTS_CONCLUANTS]
        detectes = sum(1 for o in concluantes if o.obtenu == "non_conforme")
        par_defaut[code] = {
            "jeux": len(obs), "concluants": len(concluantes), "detectes": detectes,
            "faux_verts": sum(1 for o in concluantes if o.obtenu == "conforme"),
            "non_concluants": len(obs) - len(concluantes),
            "ic95_detection": stats.intervalle_wilson(detectes, len(concluantes)),
        }
    couts = [e.cout_usd for e in campagne.essais if e.cout_usd is not None]
    cout_total = round(sum(couts), 6)
    inconnus = sum(1 for e in campagne.essais if e.cout_usd is None)
    par_cas: dict[str, float | None] = {}
    for cas in campagne.cas:
        valeurs = [e.cout_usd for e in campagne.essais if e.cas == cas and e.cout_usd is not None]
        par_cas[cas] = round(sum(valeurs) / len(valeurs), 6) if valeurs else None
    cout = {
        "total_usd": cout_total,
        "total_eur": None if not taux_eur_usd else round(cout_total / taux_eur_usd, 6),
        "taux_eur_usd": taux_eur_usd,
        "generations": len(campagne.essais),
        "generations_sans_cout_consigne": inconnus,
        "par_generation_usd": round(cout_total / len(couts), 6) if couts else None,
        "par_generation_eur": (round(cout_total / len(couts) / taux_eur_usd, 6) if couts and taux_eur_usd else None),
        "par_cas_usd": par_cas,
    }
    return {
        "faux_verts": stats.faux_verts(enregistrements),
        "faux_rouges": stats.faux_rouges(enregistrements),
        "pass_execution": {"pass_at_1": stats.pass_at_1(exec_par_cas), "pass_at_k": stats.pass_at_k(exec_par_cas, k),
                           "pass_hat_k": stats.pass_hat_k(exec_par_cas, k)},
        "pass_resultat": {"pass_at_1": stats.pass_at_1(res_par_cas), "pass_at_k": stats.pass_at_k(res_par_cas, k),
                          "pass_hat_k": stats.pass_hat_k(res_par_cas, k)},
        "non_concluants": dict(non_concluants),
        "part_non_concluants_sous_defaut": (
            sum(d["non_concluants"] for d in par_defaut.values()) / sum(d["jeux"] for d in par_defaut.values())
            if par_defaut else 0.0),
        "par_defaut": par_defaut,
        "cout": cout,
        "integrite": {
            "verifiees": sum(1 for o in campagne.observations if o.empreinte_ok is True),
            "divergentes": sum(1 for o in campagne.observations if o.empreinte_ok is False),
            "non_rapportees": sum(1 for o in campagne.observations if o.empreinte_ok is None
                                  and o.cause not in ("generation_echouee",)),
        },
        "echantillon": {
            "cas": len(campagne.cas), "k": k, "essais_prevus": campagne.essais_prevus,
            "essais_lances": len(campagne.essais), "jeux": len(campagne.observations),
        },
        "ecarts": [
            {"cas": o.cas, "variante": o.variante, "essai": o.essai, "attendu": o.attendu, "obtenu": o.obtenu,
             "cause": o.cause}
            for o in campagne.observations if o.obtenu != o.attendu
        ],
    }


# Au-delà de cette part de jeux sous défaut qui ne tranchent pas (technical_error, blocked, indetermine), la porte « faux verts »
# est jugée non mesurée : « 0 faux vert sur 1 jeu concluant, 29 en erreur » ne prouve rien (revue Q2-d).
SEUIL_NON_CONCLUANTS = 0.2


def code_de_sortie(indicateurs: dict, campagne: Campagne) -> int:
    """1 faux vert ; 3 campagne incomplète, porte « faux verts » non (assez) mesurée ou test joué non prouvé identique ; 0 sinon.

    Le faux vert PRIME : une campagne arrêtée par le plafond qui a déjà vu un faux vert reste un échec (1). Une porte non
    mesurée (aucun jeu concluant sur une variante défectueuse) est 3, jamais 0 : « non mesuré » n'est pas un vert.
    """
    if indicateurs["faux_verts"]["k"] > 0:
        return 1
    if (campagne.interrompue or indicateurs["faux_verts"]["n"] == 0 or indicateurs["integrite"]["divergentes"]
            or indicateurs["integrite"]["non_rapportees"]
            or indicateurs["part_non_concluants_sous_defaut"] > SEUIL_NON_CONCLUANTS):
        return 3
    return 0


# ── Rendu ────────────────────────────────────────────────────────────────────────────────────────────────


def _taux(d: dict) -> str:
    return stats.formater_taux(d["k"], d["n"], d.get("non_concluants", 0))


def _pass(d: dict) -> str:
    texte = stats.formater_taux(d["k"], d["n"])
    return f"{texte} ; {d['non_mesures']} cas sans assez d'essais" if d["non_mesures"] else texte


def rendre_markdown(campagne: Campagne, indicateurs: dict, contexte: dict) -> str:
    i = indicateurs
    e = i["echantillon"]
    lignes = [
        f"# Banc d'agents web — {contexte.get('date', '?')}" + (f" — {contexte['etiquette']}" if contexte.get("etiquette") else ""),
        "",
        f"Échantillon : **{e['cas']} cas × k = {e['k']} essais** → {e['essais_lances']}/{e['essais_prevus']} essais lancés, "
        f"{e['jeux']} jeux (couples cas/variante). Commit `{contexte.get('commit', '?')}` · modèle de génération "
        f"`{contexte.get('modele_generation', '?')}` · testpilot `{contexte.get('versions', {}).get('testpilot', '?')}` · "
        f"behave `{contexte.get('versions', {}).get('behave', '?')}` · playwright `{contexte.get('versions', {}).get('playwright', '?')}`.",
        "",
    ]
    if contexte.get("sous_ensemble_de_cas"):
        lignes += ["## ⚠️ Sous-ensemble de cas (mise au point)", "",
                   "Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.", ""]
    if campagne.interrompue:
        lignes += [f"## ⚠️ Campagne INCOMPLÈTE : {campagne.interrompue}", "",
                   "Les indicateurs portent sur les essais lancés seulement, jamais sur le corpus entier.", ""]
    lignes += [
        "## Indicateurs", "",
        "| Indicateur | Valeur |", "|---|---|",
        f"| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | {_taux(i['faux_verts'])} |",
        f"| Faux rouges (saine, attendu conforme, obtenu non_conforme) | {_taux(i['faux_rouges'])} |",
        f"| pass@1 — le test généré s'exécute sans erreur technique | {_pass(i['pass_execution']['pass_at_1'])} |",
        f"| pass@{e['k']} — au moins un essai sur {e['k']} | {_pass(i['pass_execution']['pass_at_k'])} |",
        f"| pass^{e['k']} — tous les essais | {_pass(i['pass_execution']['pass_hat_k'])} |",
        f"| pass@1 — résultat juste partout (saine ET défauts) | {_pass(i['pass_resultat']['pass_at_1'])} |",
        f"| pass@{e['k']} — résultat juste partout | {_pass(i['pass_resultat']['pass_at_k'])} |",
        f"| pass^{e['k']} — résultat juste partout, à chaque essai | {_pass(i['pass_resultat']['pass_hat_k'])} |",
        "",
        "« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts "
        "faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).",
        "",
        "## Résultats non concluants (comptés, jamais retirés)", "",
    ]
    if i["non_concluants"]:
        lignes += ["| Verdict | Jeux |", "|---|---|"] + [f"| {v} | {n} |" for v, n in sorted(i["non_concluants"].items())] + [""]
    else:
        lignes += ["Aucun jeu non concluant.", ""]
    lignes += ["## Détection par défaut", "", "| Défaut | Jeux | Concluants | Détectés (non_conforme) | Faux verts | Non concluants |",
               "|---|---|---|---|---|---|"]
    for code, d in i["par_defaut"].items():
        lignes.append(f"| `{code}` | {d['jeux']} | {d['concluants']} | "
                      f"{stats.formater_taux(d['detectes'], d['concluants'])} | {d['faux_verts']} | {d['non_concluants']} |")
    if not i["par_defaut"]:
        lignes.append("| (aucun jeu sur un défaut) | 0 | 0 | non mesuré | 0 | 0 |")
    c = i["cout"]
    lignes += ["", "## Coût", "",
               f"Total : **{c['total_usd']:.3f} $**"
               + (f" = {c['total_eur']:.3f} € (1 € = {c['taux_eur_usd']} $)" if c["total_eur"] is not None else " (taux EUR/USD non fourni)")
               + f" pour {c['generations']} génération(s) ; par génération : "
               + (f"{c['par_generation_usd']:.3f} $ / {c['par_generation_eur']:.3f} €" if c["par_generation_eur"] is not None
                  else ("non mesuré" if c["par_generation_usd"] is None else f"{c['par_generation_usd']:.3f} $")) + ".",
               "Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations."]
    if c["generations_sans_cout_consigne"]:
        lignes.append(f"⚠️ {c['generations_sans_cout_consigne']} génération(s) sans coût consigné (non comptées comme 0).")
    lignes += ["", "| Cas | Coût moyen par génération ($) |", "|---|---|"]
    lignes += [f"| {cas} | {'non mesuré' if v is None else f'{v:.3f}'} |" for cas, v in c["par_cas_usd"].items()]
    g = i["integrite"]
    lignes += ["", "## Intégrité : le MÊME test est joué partout", "",
               f"Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **{g['verifiees']}** ; "
               f"divergentes : **{g['divergentes']}** ; non rapportées : {g['non_rapportees']}."]
    if campagne.anomalies:
        lignes += ["", "## Anomalies du harnais", ""] + [f"- {a}" for a in campagne.anomalies]
    if i["ecarts"]:
        lignes += ["", "## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)", "",
                   "| Cas | Variante | Essai | Attendu | Obtenu | Cause |", "|---|---|---|---|---|---|"]
        lignes += [f"| {x['cas']} | {x['variante']} | {x['essai']} | {x['attendu']} | {x['obtenu']} | {x['cause'] or '—'} |"
                   for x in i["ecarts"]]
    lignes += ["", "## Génération par essai", "", "| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |", "|---|---|---|---|---|"]
    for t in campagne.essais:
        empreinte_globale = empreinte("".join(f"{n}:{h}" for n, h in sorted(t.empreintes.items()))) if t.empreintes else "—"
        lignes.append(f"| {t.cas} | {t.essai} | {'oui' if t.genere else 'NON : ' + (t.erreur[:80] or '?')} | "
                      f"{'non consigné' if t.cout_usd is None else f'{t.cout_usd:.3f}'} | `{empreinte_globale[:16]}` |")
    return "\n".join(lignes) + "\n"


def _versions() -> dict[str, str]:
    from importlib import metadata

    sortie = {"python": sys.version.split()[0]}
    for nom in ("testpilot", "behave", "playwright"):
        try:
            sortie[nom] = metadata.version(nom)
        except Exception:
            sortie[nom] = "inconnue"
    return sortie


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=RACINE,
                              check=True).stdout.strip()
    except Exception:
        return "?"


def empreinte_de_la_configuration(dossier_specs: Path = SPECS) -> str:
    """Empreinte des specs et des attendus au moment de la mesure : prouve après coup qu'ils n'ont pas bougé."""
    morceaux = [f"{p.name}:{empreinte(p.read_bytes())}" for p in sorted(Path(dossier_specs).glob("*.md"))]
    morceaux += [f"{p.name}:{empreinte(p.read_bytes())}" for p in sorted(Path(dossier_specs).glob("*.yaml"))]
    return empreinte("\n".join(morceaux))


def ecrire_sortie(campagne: Campagne, indicateurs: dict, contexte: dict, dossier: Path = SORTIE) -> tuple[Path, Path]:
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    base = dossier / (f"banc-agents-{contexte['date']}" + (f"-{contexte['etiquette']}" if contexte.get("etiquette") else ""))
    md, js = Path(f"{base}.md"), Path(f"{base}.json")
    md.write_text(rendre_markdown(campagne, indicateurs, contexte), encoding="utf-8")
    js.write_text(json.dumps({
        "contexte": contexte, "indicateurs": indicateurs, "interrompue": campagne.interrompue,
        "essais": [vars(t) for t in campagne.essais], "observations": [vars(o) for o in campagne.observations],
        "anomalies": campagne.anomalies,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return md, js


# ── Budget et validation à sec ───────────────────────────────────────────────────────────────────────────


def estimer_budget(n_cas: int, k: int, cout_essai_usd: float, taux_eur_usd: float | None) -> dict:
    generations = n_cas * k
    usd = round(generations * cout_essai_usd, 4)
    return {"generations": generations, "cout_par_generation_usd": cout_essai_usd, "total_usd": usd,
            "total_eur": None if not taux_eur_usd else round(usd / taux_eur_usd, 4)}


def valider_a_sec(k: int) -> tuple[Configuration, list[str]]:
    """Mode `--a-sec` : ne valide QUE la configuration ; n'appelle ni LLM, ni navigateur, ni application."""
    configuration = charger_configuration()
    lignes = [f"Configuration valide : {len(configuration.specs)} specs, {len(configuration.attendus)} attendus, "
              f"{len(configuration.defauts_connus)} défauts ({', '.join(configuration.defauts_connus)})."]
    jeux = 0
    for cas in configuration.specs:
        variantes = variantes_de(cas, configuration.attendus)
        jeux += len(variantes) * k
        lignes.append(f"  {cas:<32} 1 génération + {len(variantes)} jeux : {', '.join(variantes)}")
    lignes.append(f"Pour k = {k} : {len(configuration.specs) * k} générations, {jeux} jeux au total.")
    return configuration, lignes


# ── Adaptateurs RÉELS (activés par --reel seulement ; jamais appelés par les tests) ──────────────────────


def exiger_loopback(hote: str) -> str:
    """Refuse tout hôte qui n'est pas de bouclage : le banc contient des défauts faits pour se tromper."""
    if (hote or "").strip().strip("[]").lower() not in HOTES_LOOPBACK:
        raise ConfigurationInvalide(f"hôte « {hote} » refusé : le banc d'agents n'accepte que le bouclage (127.0.0.1)")
    return "127.0.0.1" if hote.strip().lower() == "localhost" else hote.strip().strip("[]")


class ApplicationLocale:
    """L'application de `banc/app_web/` sur un port libre en bouclage, pilotée par ses routes `/__*`.

    `reinitialiser(defauts)` : bascule des défauts (`POST /__defauts`), remise à zéro (`POST /__reset`), puis RELECTURE de
    ce qui est effectivement actif (`GET /__defauts`) et de l'état (`GET /__etat`) — on ne croit jamais qu'une bascule a eu
    lieu, on le vérifie : un jeu sur la mauvaise variante serait un faux vert ou un faux rouge fabriqué par le harnais.
    """

    def __init__(self, hote: str = "127.0.0.1") -> None:
        self.hote = exiger_loopback(hote)
        self._serveur = None
        self._fil: threading.Thread | None = None

    def demarrer(self) -> str:
        from banc.app_web import serveur

        self._serveur = serveur.creer_serveur(self.hote, 0, "")
        self._fil = threading.Thread(target=self._serveur.serve_forever, daemon=True)
        self._fil.start()
        return self.url

    @property
    def url(self) -> str:
        if self._serveur is None:
            raise RuntimeError("application non démarrée")
        return self._serveur.url

    def arreter(self) -> None:
        if self._serveur is not None:
            self._serveur.shutdown()
            self._serveur.server_close()
            if self._fil is not None:
                self._fil.join(timeout=5)
            self._serveur = None

    def __enter__(self) -> "ApplicationLocale":
        self.demarrer()
        return self

    def __exit__(self, *_exc) -> None:
        self.arreter()

    def _appeler(self, methode: str, chemin: str, corps: dict | None = None) -> dict:
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        requete = urllib.request.Request(self.url + chemin, data=donnees, method=methode,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(requete, timeout=10) as reponse:
                return json.loads(reponse.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as erreur:
            raise RuntimeError(f"{methode} {chemin} : HTTP {erreur.code}") from erreur

    def reinitialiser(self, defauts: Sequence[str]) -> None:
        voulus = sorted(defauts)
        self._appeler("POST", "/__defauts", {"defauts": voulus})
        self._appeler("POST", "/__reset", {})
        actifs = sorted(self._appeler("GET", "/__defauts").get("defauts") or [])
        if actifs != voulus:
            raise RuntimeError(f"défauts actifs {actifs} ≠ défauts demandés {voulus} : jeu refusé")
        etat = self._appeler("GET", "/__etat")
        if etat.get("commandes") or etat.get("enregistrements") or (etat.get("panier") or {}).get("lignes"):
            raise RuntimeError("l'application n'est pas revenue à son état initial après /__reset : jeu refusé")


def executer_behave(dossier: Path, module: str, connexion: dict[str, str], project_id: int | None,
                    connector_type: str, traces: Path | None) -> dict:
    """Le chemin de PRODUCTION d'un jeu : `BehaveRunner` + `Executor(max_retries=0)` + `derive_verdict`.

    Même chaîne que `banc_mesure.executer_cas`. Aucun rejeu (un rejeu masquerait un test instable) ni réparation : un
    jeu = une exécution. Les imports ont lieu ICI parce que le dossier de données jetable doit être posé avant
    (`_isoler_donnees`) ; ce module reste importable, et testable, sans `testpilot`.
    """
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.verdict.status import derive_verdict

    debut = time.time()
    runner = BehaveRunner(connection=connexion, connector_type=connector_type, generated_dir=dossier,
                          project_id=project_id)
    if traces is not None:
        traces.mkdir(parents=True, exist_ok=True)
        runner.cibler_artefacts(traces)
    resultat = Executor(runner, max_retries=0).execute(module)
    verdict = derive_verdict(resultat, connector_type=connector_type)
    causes = sorted({s.cause_category for s in verdict.scenarios if s.cause_category})
    echecs = (resultat.real_run.failures if resultat.real_run else []) or []
    detail = (echecs[0].raw or "").strip()[-300:] if echecs else (resultat.error or "")
    return {"execution": verdict.execution_status, "fonctionnel": verdict.functional_status,
            "cause": ", ".join(causes), "detail": detail, "duree": round(time.time() - debut, 1)}


class JoueurReel:
    """`jouer(artefacts, variante)` réel : écrit les fichiers GÉNÉRÉS, règle l'application, exécute, restaure la saine."""

    def __init__(self, application, executer: Callable[..., dict], dossier_de_travail: Path, connexion: dict[str, str],
                 project_id: int | None = None, connector_type: str = "web") -> None:
        self.application = application
        self.executer = executer
        self.dossier_de_travail = Path(dossier_de_travail)
        self.connexion = connexion
        self.project_id = project_id
        self.connector_type = connector_type

    def __call__(self, artefacts: Artefacts, variante: str) -> Jeu:
        defauts = [] if variante == VARIANTE_SAINE else [variante]
        dossier = Path(tempfile.mkdtemp(prefix="jeu_", dir=self.dossier_de_travail))
        try:
            for nom, contenu in artefacts.fichiers.items():
                (dossier / nom).write_bytes(contenu.encode("utf-8"))  # octets exacts : l'empreinte doit survivre
            self.application.reinitialiser(defauts)
            retour = self.executer(dossier, artefacts.module, self.connexion, self.project_id, self.connector_type,
                                   self.dossier_de_travail / "traces" / f"{artefacts.cas}-t{artefacts.essai}-{variante}")
            joues = {nom: empreinte((dossier / nom).read_bytes()) for nom in sorted(artefacts.fichiers)}
            return Jeu(verdict=verdict_du_banc(retour.get("execution"), retour.get("fonctionnel")),
                       cause=retour.get("cause", ""), detail=retour.get("detail", ""), duree=retour.get("duree"),
                       empreintes=joues)
        finally:
            try:
                self.application.reinitialiser([])  # jamais laisser un défaut actif derrière soi
            finally:
                shutil.rmtree(dossier, ignore_errors=True)


class GenerateurReel:
    """`generer(spec, essai)` réel : le moteur de `qualify_campaign_pilot.py`, en sous-processus, sur l'application SAINE.

    Un sous-processus par (cas, essai) : le script isole ses données à l'import et porte déjà le plafond de coût du moteur ;
    on lui transmet le RESTE du budget (`--max-cost-usd`) en plus de l'arrêt en amont de l'orchestrateur. L'exécution
    physique qu'il fait à la fin est ignorée : le jeu sur la saine est rejoué par `JoueurReel`, comme sur les défauts.
    """

    def __init__(self, application, ids_de_cas: Mapping[str, int], project_id: int, url: str, data_dir: Path,
                 cle_secrete: str, reste_usd: Callable[[], float | None], lancer=subprocess.run,
                 racine: Path = RACINE, delai_s: int = 1800) -> None:
        self.delai_s = delai_s
        self.application = application
        self.ids_de_cas = dict(ids_de_cas)
        self.project_id = project_id
        self.url = url
        self.data_dir = Path(data_dir)
        self.cle_secrete = cle_secrete
        self.reste_usd = reste_usd
        self.lancer = lancer
        self.racine = Path(racine)

    def commande(self, cas: str, essai: int) -> tuple[list[str], str]:
        sortie = f"banc-agents-{cas}-t{essai}"
        commande = [sys.executable, str(CAMPAGNE), "--out", sortie, "--project-id", str(self.project_id),
                    "--cases", str(self.ids_de_cas[cas]), "--iterations", str(essai), "--expected-base-url", self.url]
        reste = self.reste_usd()
        if reste is not None:
            commande += ["--max-cost-usd", f"{max(reste, 0.0):.4f}"]
        return commande, sortie

    def __call__(self, cas: str, essai: int) -> Artefacts:
        self.application.reinitialiser([])  # génération et essai à blanc sur l'application SAINE, état vierge
        commande, sortie = self.commande(cas, essai)
        env = {**os.environ, "TESTPILOT_CAMPAIGN_SOURCE_DATA": str(self.data_dir),
               "TESTPILOT_SECRET_KEY": self.cle_secrete}
        env.pop("TESTPILOT_DATA_DIR", None)
        dossier = self.racine / ".local-preview" / "qualification" / sortie
        campagne_json, arret_json = dossier / "campagne.json", dossier / "arret_plafond.json"
        for reste in (campagne_json, arret_json):  # un résultat périmé ne doit jamais passer pour celui de CE run
            reste.unlink(missing_ok=True)
        try:
            processus = self.lancer(commande, cwd=self.racine, env=env, timeout=self.delai_s)
        except subprocess.TimeoutExpired as exc:  # un moteur bloqué ne suspend pas la campagne sans limite
            raise RuntimeError(f"le moteur de génération n'a pas rendu la main en {self.delai_s} s") from exc
        rapports = json.loads(campagne_json.read_text(encoding="utf-8")) if campagne_json.exists() else []
        arret = json.loads(arret_json.read_text(encoding="utf-8")) if arret_json.exists() else None
        if arret and not rapports:
            raise ArretCampagne(arret.get("raison", "plafond du moteur de génération"))
        if processus.returncode not in (0, 3) or not rapports:
            raise RuntimeError(f"le moteur de génération a échoué (code {processus.returncode}, aucun rapport)")
        return artefacts_depuis_rapport(cas, essai, rapports[0])


def artefacts_depuis_rapport(cas: str, essai: int, rapport: Mapping) -> Artefacts:
    """Un rapport d'essai de `campagne.json` → `Artefacts` (pur : testé sur des rapports simulés)."""
    gen = rapport.get("generation") or {}
    module = gen.get("module_name") or ""
    fichiers = {}
    if module and gen.get("feature_content"):
        fichiers[f"{module}.feature"] = gen["feature_content"]
    if module and gen.get("steps_content"):
        fichiers[f"{module}_steps.py"] = gen["steps_content"]
    jouable = bool(gen.get("success")) and bool(gen.get("dry_run_passed")) and len(fichiers) == 2
    erreur = "" if jouable else str(rapport.get("generation_error") or gen.get("error") or
                                    "génération sans essai à blanc passé")[:300]
    return Artefacts(cas=cas, essai=essai, fichiers=fichiers if jouable else {},
                     cout_usd=(float(gen["cost_usd"]) if gen.get("cost_usd") is not None else None),
                     genere_ok=jouable, erreur=erreur, module=module)


def preparer_projet_web(url: str, compte: Mapping, specs: Mapping[str, dict], data_dir: Path,
                        cle_secrete: str) -> tuple[int, dict[str, int]]:
    """Projet `web` jetable + annuaire (exploration déterministe, navigateur réel) + un cas par spec. Mode réel seulement."""
    os.environ["TESTPILOT_DATA_DIR"] = str(data_dir)
    os.environ["TESTPILOT_SECRET_KEY"] = cle_secrete
    sys.path.insert(0, str(RACINE / "src"))
    import banc_projet
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

    conn = get_initialized_db(Path(config.DB_PATH))
    project_id = ProjectRepo(conn).create(
        name="Banc agents web — boutique locale", description="Banc d'agents web (Q2-d) : application locale à défauts.",
        connector_type="web", base_url=url, username=compte["identifiant"], password=compte["mot_de_passe"])
    banc_projet.explorer(conn, project_id)
    module_id = ModuleRepo(conn).create(project_id=project_id, name=MODULE_DU_BANC)
    cas = CaseRepo(conn)
    ids: dict[str, int] = {}
    for slug, metier in specs.items():
        ids[slug] = cas.create_manual(
            module_id=module_id, title=metier["title"], preconditions=metier["preconditions"],
            test_steps=json.dumps(metier["steps"], ensure_ascii=False),
            expected_result=metier["expected_result"], author="banc-agents")
    return project_id, ids


def connexion_du_projet(project_id: int) -> dict[str, str]:
    """La connexion d'exécution du projet (lue par `runtime_env`, jamais par ce script : règle D8)."""
    import sqlite3

    from testpilot import config
    from testpilot.connectors.runtime_env import verifier_connexion_du_projet
    from testpilot.store.repositories import ProjectRepo

    with sqlite3.connect(config.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return verifier_connexion_du_projet(conn, ProjectRepo(conn).get(project_id))


# ── Point d'entrée ───────────────────────────────────────────────────────────────────────────────────────


def _isoler_donnees() -> Path:
    """Une mesure ne modifie JAMAIS `data/` : dossier de données jetable, posé AVANT tout import de `testpilot`."""
    if os.environ.get("ODOO_ENV") == "prod":  # jamais contourné (CLAUDE.md §4) : on REFUSE
        raise ConfigurationInvalide("ODOO_ENV=prod : le banc ne tourne jamais dans un environnement de production")
    dossier = Path(os.environ.get("BANC_DATA_DIR") or tempfile.mkdtemp(prefix="banc_agents_data_"))
    os.environ["TESTPILOT_DATA_DIR"] = str(dossier)
    sys.path.insert(0, str(RACINE / "src"))
    return dossier


def _lire_taux_eur_usd() -> float | None:
    try:
        sys.path.insert(0, str(RACINE / "src"))
        from testpilot import config

        return float(config.EUR_USD_RATE)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parseur = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--a-sec", action="store_true", help="valide la configuration seulement (défaut) : aucun LLM, aucun navigateur")
    parseur.add_argument("--reel", action="store_true", help="LLM + navigateur RÉELS (coût) : exige --plafond-cout")
    parseur.add_argument("--essais", type=int, default=3, help="k : générations indépendantes par cas (défaut 3)")
    parseur.add_argument("--plafond-cout", type=float, default=None, help="plafond de coût en dollars (OBLIGATOIRE avec --reel)")
    parseur.add_argument("--cout-estime-essai", type=float, default=COUT_ESTIME_ESSAI_USD,
                         help="coût présumé d'une génération avant d'en avoir observé une (dollars)")
    parseur.add_argument("--hote", default="127.0.0.1", help="hôte de l'application locale : bouclage uniquement")
    parseur.add_argument("--cas", default=None, help="mise au point : cas séparés par des virgules (le rapport l'indique)")
    parseur.add_argument("--etiquette", default="")
    parseur.add_argument("--sortie", type=Path, default=SORTIE)
    args = parseur.parse_args(argv)
    if args.reel and args.a_sec:
        parseur.error("--reel et --a-sec s'excluent")
    if args.reel and args.plafond_cout is None:
        parseur.error("--plafond-cout est obligatoire avec --reel (une génération coûte de l'argent)")
    if args.essais < 1:
        parseur.error("--essais doit être >= 1")

    try:
        exiger_loopback(args.hote)
        verifier_bornes_de_cout(args.plafond_cout, args.cout_estime_essai)
        if args.reel and args.plafond_cout <= 0:
            raise ConfigurationInvalide("plafond de coût nul : aucune génération ne pourrait être lancée")
        configuration, lignes = valider_a_sec(args.essais)
        if args.cas:
            voulus = list(dict.fromkeys(c.strip() for c in args.cas.split(",") if c.strip()))
            if not voulus:
                raise ConfigurationInvalide("--cas ne désigne aucun cas")
            inconnus = [c for c in voulus if c not in configuration.specs]
            if inconnus:
                raise ConfigurationInvalide(f"cas inconnu(s) : {', '.join(inconnus)}")
    except ConfigurationInvalide as erreur:
        print(f"Configuration INVALIDE : {erreur}", file=sys.stderr)
        return 2
    taux = _lire_taux_eur_usd()
    cas_joues = voulus if args.cas else list(configuration.specs)
    budget = estimer_budget(len(cas_joues), args.essais, args.cout_estime_essai, taux)
    print("\n".join(lignes))
    if not args.reel:
        print("Mode à sec : rien n'a été généré ni joué (aucun LLM, aucun navigateur, aucune application).")
        print(f"Budget d'une campagne RÉELLE (estimation, non mesuré sur le web) : {budget['generations']} générations "
              f"× {budget['cout_par_generation_usd']} $ = {budget['total_usd']} $"
              + (f" ≈ {budget['total_eur']} €" if budget["total_eur"] is not None else "") + ".")
        return 0

    print(f"\nBUDGET AVANT DÉPART : {budget['generations']} générations × {budget['cout_par_generation_usd']} $ (estimation) = "
          f"{budget['total_usd']} $" + (f" ≈ {budget['total_eur']} €" if budget["total_eur"] is not None else "")
          + f" ; plafond appliqué : {args.plafond_cout} $ (arrêt AVANT l'essai qui le dépasserait).", flush=True)
    return _lancer_reel(args, configuration, cas_joues, taux)


def _lancer_reel(args, configuration: Configuration, cas_joues: list[str], taux: float | None) -> int:
    from cryptography.fernet import Fernet

    try:
        data_dir = _isoler_donnees()
    except ConfigurationInvalide as erreur:
        print(f"Refus : {erreur}", file=sys.stderr)
        return 2
    cle = os.environ.get("TESTPILOT_SECRET_KEY") or Fernet.generate_key().decode()
    os.environ["TESTPILOT_SECRET_KEY"] = cle
    compte = configuration.app["comptes"][0]
    specs = {c: configuration.specs[c] for c in cas_joues}
    attendus = [a for a in configuration.attendus if a.cas in specs]
    defauts_codes = {a.variante for a in attendus if a.variante != VARIANTE_SAINE}
    traces = Path(tempfile.mkdtemp(prefix="banc_agents_jeux_"))
    with ApplicationLocale(args.hote) as application:
        application.reinitialiser([])
        project_id, ids = preparer_projet_web(application.url, compte, specs, data_dir, cle)
        suivi = {"usd": 0.0, "max": 0.0}
        reste = (lambda: None if args.plafond_cout is None else args.plafond_cout - suivi["usd"])

        def cout(artefacts: Artefacts) -> float | None:
            # Même règle que l'orchestrateur : un coût non consigné est compté au pire pour le reste transmis au moteur.
            suivi["usd"] += cout_retenu_pour_le_plafond(artefacts.cout_usd, suivi["max"], args.cout_estime_essai)
            suivi["max"] = max(suivi["max"], artefacts.cout_usd or 0.0)
            return artefacts.cout_usd

        generer = GenerateurReel(application, ids, project_id, application.url, data_dir, cle, reste)
        jouer = JoueurReel(application, executer_behave, traces, connexion_du_projet(project_id), project_id, "web")
        campagne = executer_campagne(
            list(specs), attendus, args.essais, generer, jouer, defauts_connus=defauts_codes, cout=cout,
            plafond_usd=args.plafond_cout, cout_estime_essai=args.cout_estime_essai, reel=True,
            journal=lambda m: print(m, flush=True))
    indicateurs = calculer_indicateurs(campagne, taux)
    contexte = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "etiquette": args.etiquette,
                "commit": _commit(), "versions": _versions(), "modele_generation": _modele(),
                "mode": "reel", "plafond_usd": args.plafond_cout, "app": NOM_DE_L_APP,
                "configuration_sha256": empreinte_de_la_configuration(),
                "sous_ensemble_de_cas": bool(args.cas), "donnees_jetables": str(data_dir)}
    md, js = ecrire_sortie(campagne, indicateurs, contexte, args.sortie)
    code = code_de_sortie(indicateurs, campagne)
    print(f"\nRapport : {md}\nJSON    : {js}\nFaux verts {_taux(indicateurs['faux_verts'])} → code de sortie {code}")
    return code


def _modele() -> str:
    try:
        sys.path.insert(0, str(RACINE / "src"))
        from testpilot import config

        return str(config.MODEL_GENERATION)
    except Exception:
        return "inconnu"


if __name__ == "__main__":
    sys.exit(main())
