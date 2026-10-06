"""Import de cas de test depuis un classeur Excel (cahier de test existant).

Le porteur a un existant de cahiers de test en `.xlsx` (ex. colonnes Test Case ID / Description /
Étapes du Test / Résultat Attendu / User Story / Priorité / Statut / Testeur / Date / Type /
Commentaires, entête pas forcément en ligne 1) et veut les charger plutôt que les retaper — y
compris des résultats déjà joués par un autre outil (Cypress/Jest…), à ranger comme un résultat
MANUEL/déclaré (`ResultRepo.saisir`, `testpilot.verdict.status.STATUTS_MANUELS`), jamais comme un
verdict automatique de TestPilot (`last_execution_status`/`last_functional_status` — réservés à un
run Behave réel, §4 CLAUDE.md : un faux PASSED serait le pire défaut possible).

Un Excel réel n'est pas toujours propre (ordre de colonnes différent, intitulés en anglais, lignes
de titre avant l'entête…) : ce module ne DEVINE jamais en silence — toute colonne ou ligne
ambiguë est signalée dans le résultat (`avertissements`), à confirmer ou corriger par un humain
avant toute écriture en base (voir les routes `/api/modules/{id}/cases/import-excel/*`).

Pas d'I/O ici (lecture de `bytes` déjà en mémoire, bornés par l'appelant comme `spec_extract`) :
module pur, comme `verdict/` et `taxonomie/` (§6).
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from testpilot import config

_TAILLE_MAX_LIGNES_SCAN_ENTETE = 15
_SEUIL_SIMILARITE_COLONNE = 0.6


class FichierExcelInvalide(Exception):
    """Classeur illisible, vide, ou sans feuille exploitable — traduit en HTTP 422 par la route."""


# ── Dictionnaire de synonymes (FR/EN), normalisés : minuscule, sans accent ──────────────────────
# Chaque champ cible a sa propre banque — un synonyme n'apparaît que sous UN champ, pour qu'un
# score élevé reste décisif (évite qu'une colonne corresponde "également bien" à deux champs).
_SYNONYMES: dict[str, tuple[str, ...]] = {
    "identifiant": ("test case id", "id", "tc id", "identifiant", "case id", "numero", "n"),
    "titre": ("description", "titre", "title", "summary", "resume", "nom du cas", "nom", "name"),
    "preconditions": ("preconditions", "pre-conditions", "prerequisite", "prerequis",
                       "prerequisites", "precondition"),
    "etapes": ("etapes du test", "etapes", "steps", "test steps", "procedure", "scenario"),
    "resultat_attendu": ("resultat attendu", "expected result", "resultat", "attendu",
                          "expected", "resultat espere"),
    "section": ("user story", "userstory", "us", "section", "module", "feature", "epic",
                "fonctionnalite"),
    "priorite": ("priorite", "priority"),
    "statut": ("statut", "status", "etat du test", "resultat du test"),
    "testeur": ("testeur", "tester", "executant", "auteur du test", "joue par"),
    "date": ("date", "date d'execution", "date de test", "date du test"),
    "type": ("type", "categorie", "nature"),
    "commentaires": ("commentaires", "comment", "comments", "notes", "remarque", "remarques",
                      "reference", "ref"),
}

# Champs sans lesquels une ligne ne décrit rien (même garde que `CaseRepo.create_manual` : étapes
# + résultat attendu obligatoires — le titre est dérivable, les autres sont optionnels).
_CHAMPS_REQUIS_LIGNE = ("etapes", "resultat_attendu")

# Priorité Excel (souvent 4 niveaux, type TestRail/Jira) → les 3 niveaux acceptés par le schéma
# (`CHECK test_case.priority IN ('low','medium','high')`). Clés déjà normalisées.
_PRIORITES: dict[str, str] = {
    "p1": "high", "p1 critique": "high", "p1 - critique": "high", "critique": "high",
    "critical": "high", "high": "high", "haute": "high", "urgent": "high", "bloquant": "high",
    "p2": "medium", "p2 majeur": "medium", "p2 - majeur": "medium", "majeur": "medium",
    "major": "medium", "medium": "medium", "moyenne": "medium", "normal": "medium",
    "p3": "low", "p3 mineur": "low", "p3 - mineur": "low", "mineur": "low", "minor": "low",
    "p4": "low", "p4 cosmetique": "low", "p4 - cosmetique": "low", "cosmetique": "low",
    "low": "low", "basse": "low", "faible": "low",
}
_PRIORITE_PAR_DEFAUT = "medium"

# Statut Excel → `STATUTS_MANUELS` (testpilot.verdict.status). Une valeur absente de cette table
# (vide, "No Run", "In Progress", "N/A"…) ne produit AUCUN résultat importé pour la ligne — même
# principe que `STATUTS_MANUELS` lui-même : l'absence de résultat se dit par l'absence, jamais par
# une valeur qui prétendrait quelque chose.
_STATUTS: dict[str, str] = {
    "passed": "passed", "pass": "passed", "success": "passed", "ok": "passed",
    "reussi": "passed", "succes": "passed",
    "failed": "failed", "fail": "failed", "echec": "failed", "ko": "failed",
    "blocked": "blocked", "bloque": "blocked", "bloquee": "blocked",
    "retest": "retest", "a retester": "retest", "a rejouer": "retest",
}

# Type Excel → les 2 valeurs du vocabulaire serveur (`schemas.TYPES_CAS`). Une valeur absente est
# un simple silence (pas d'avertissement) ; une valeur PRÉSENTE mais non reconnue (ex. « Smoke »,
# « Non-régression ») retombe sur le défaut déjà utilisé par le schéma (`fonctionnel`) — mais avec
# avertissement, jamais en silence (même principe que `_PRIORITES`).
_TYPES: dict[str, str] = {
    "fonctionnel": "fonctionnel", "functional": "fonctionnel", "fonctionnelle": "fonctionnel",
    "non fonctionnel": "non_fonctionnel", "non functional": "non_fonctionnel",
    "non-fonctionnel": "non_fonctionnel", "nonfunctional": "non_fonctionnel",
}
_TYPE_PAR_DEFAUT = "fonctionnel"


def normaliser(texte: str) -> str:
    """minuscule, sans accent, ponctuation réduite à des espaces — pour comparer deux libellés
    sans faux négatif sur un simple détail de frappe (« Résultat Attendu » == « resultat_attendu
    »)."""
    sans_accent = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    sans_accent = sans_accent.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", sans_accent).strip()


def _meilleur_champ(libelle_normalise: str) -> tuple[str | None, float]:
    """Le champ cible dont un synonyme ressemble le plus à `libelle_normalise`, avec le score
    (0 à 1). Égalité exacte d'abord (score 1.0, jamais mis en doute par le fuzzy), sinon le
    meilleur ratio `difflib` — en dessous de `_SEUIL_SIMILARITE_COLONNE`, aucun champ n'est retenu
    (`None`) : une colonne non reconnue reste non reconnue, jamais assignée au hasard."""
    meilleur_champ, meilleur_score = None, 0.0
    for champ, synonymes in _SYNONYMES.items():
        if libelle_normalise in synonymes:
            return champ, 1.0
        for synonyme in synonymes:
            score = SequenceMatcher(None, libelle_normalise, synonyme).ratio()
            if score > meilleur_score:
                meilleur_champ, meilleur_score = champ, score
    if meilleur_score < _SEUIL_SIMILARITE_COLONNE:
        return None, meilleur_score
    return meilleur_champ, meilleur_score


@dataclass
class EntetesDetectees:
    feuille: str
    index_ligne_entete: int  # 1-based, convention openpyxl
    mapping: dict[int, str]  # index de colonne (1-based) -> champ cible
    score: float
    # Intitulé BRUT de CHAQUE colonne non vide, y compris celles qu'aucun synonyme n'a reconnues —
    # sans ça, l'aperçu ne peut proposer à l'utilisateur de corriger QUE les colonnes déjà
    # devinées : une colonne jamais reconnue resterait invisible, donc impossible à rattacher à un
    # champ à la main (trouvé en répondant à une question du porteur sur le cas « aucune colonne
    # ne correspond », 2026-10-02 — le filet de sécurité annoncé était incomplet).
    entetes_brutes: dict[int, str] = field(default_factory=dict)


def detecter_feuille_et_entete(classeur) -> EntetesDetectees:
    """La feuille et la ligne d'entête les plus plausibles, sur TOUTES les feuilles du classeur.

    Scanne les `_TAILLE_MAX_LIGNES_SCAN_ENTETE` premières lignes de chaque feuille : une ligne de
    titre/metadata (une seule cellule remplie, ou aucun libellé reconnu) a un score quasi nul, la
    vraie ligne d'entête concentre les libellés reconnus — ni la position ni le nombre de feuilles
    n'est supposé fixe (cas réel : 2 lignes de titre au-dessus de l'entête, feuilles « Dashboard »/
    « Guide » annexes à ignorer).
    """
    meilleure: EntetesDetectees | None = None
    for feuille in classeur.worksheets:
        max_ligne = min(feuille.max_row or 1, _TAILLE_MAX_LIGNES_SCAN_ENTETE)
        for i in range(1, max_ligne + 1):
            valeurs = [str(c).strip() if c is not None else "" for c in
                       next(feuille.iter_rows(min_row=i, max_row=i, values_only=True), ())]
            if not any(valeurs):
                continue
            mapping: dict[int, str] = {}
            entetes_brutes: dict[int, str] = {}
            for col_idx, libelle in enumerate(valeurs, start=1):
                if not libelle:
                    continue
                entetes_brutes[col_idx] = libelle
                champ, score = _meilleur_champ(normaliser(libelle))
                if champ is not None and champ not in mapping.values():
                    mapping[col_idx] = champ
            score_ligne = len(mapping)
            if meilleure is None or score_ligne > meilleure.score:
                meilleure = EntetesDetectees(feuille.title, i, mapping, score_ligne, entetes_brutes)
    if meilleure is None or meilleure.score == 0:
        raise FichierExcelInvalide(
            "aucune ligne d'entête reconnaissable (Titre, Étapes, Résultat attendu…) sur aucune "
            "feuille du classeur")
    return meilleure


@dataclass
class LigneCandidate:
    numero_ligne: int  # 1-based, position réelle dans la feuille (pour pointer un avertissement)
    titre: str
    preconditions: str
    etapes: list[str]
    resultat_attendu: str
    section: str
    priorite: str
    statut_manuel: str | None  # déjà traduit en STATUTS_MANUELS, ou None
    testeur: str
    date: str
    type_cas: str
    commentaires: str
    identifiant: str  # identifiant du cahier d'origine (ex. TC-AUTH-001) → champ « Références »
    retenue: bool  # False = ignorée par défaut (ligne incomplète), modifiable par l'utilisateur
    avertissements: list[str] = field(default_factory=list)


def _texte_cellule(valeur) -> str:
    if valeur is None:
        return ""
    return str(valeur).strip()


_NUMEROTATION_ETAPE = re.compile(r"^\s*\d+[.)]\s*")


def _decouper_etapes(texte: str) -> list[str]:
    """Une cellule « 1. Ouvrir /login\\n2. Saisir… » devient une étape par ligne, sans sa
    numérotation — le format exact observé sur le cahier de test réel (une seule cellule,
    plusieurs étapes numérotées)."""
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    return [_NUMEROTATION_ETAPE.sub("", l) for l in lignes]


def extraire_lignes(feuille, entetes: EntetesDetectees) -> list[LigneCandidate]:
    """Toutes les lignes de données sous la ligne d'entête, mappées vers les champs cibles —
    jamais une ligne perdue en silence : une ligne incomplète est rendue avec `retenue=False` et
    ses `avertissements`, visible dans l'aperçu plutôt qu'absente du résultat."""
    inverse: dict[str, int] = {champ: col for col, champ in entetes.mapping.items()}
    lignes: list[LigneCandidate] = []
    for i, valeurs in enumerate(
            feuille.iter_rows(min_row=entetes.index_ligne_entete + 1, values_only=True),
            start=entetes.index_ligne_entete + 1):

        def cell(champ: str) -> str:
            col = inverse.get(champ)
            return _texte_cellule(valeurs[col - 1]) if col and col <= len(valeurs) else ""

        if not any(valeurs):
            continue  # ligne entièrement vide (fréquent en fin de feuille Excel) — pas une donnée

        titre = cell("titre") or cell("identifiant") or f"Cas importé (ligne {i})"
        etapes = _decouper_etapes(cell("etapes"))
        resultat_attendu = cell("resultat_attendu")
        avertissements: list[str] = []

        priorite_brute = cell("priorite")
        if priorite_brute:
            priorite = _PRIORITES.get(normaliser(priorite_brute))
            if priorite is None:
                priorite = _PRIORITE_PAR_DEFAUT
                avertissements.append(
                    f"priorité « {priorite_brute} » non reconnue — « {_PRIORITE_PAR_DEFAUT} » "
                    "retenue par défaut")
        else:
            priorite = _PRIORITE_PAR_DEFAUT

        statut_brut = cell("statut")
        statut_manuel = _STATUTS.get(normaliser(statut_brut)) if statut_brut else None
        if statut_brut and statut_manuel is None:
            avertissements.append(
                f"statut « {statut_brut} » non reconnu comme résultat déclarable — ignoré "
                "(seuls Passed/Failed/Blocked/Retest le sont)")

        type_brut = cell("type")
        if type_brut:
            type_cas = _TYPES.get(normaliser(type_brut))
            if type_cas is None:
                type_cas = _TYPE_PAR_DEFAUT
                avertissements.append(
                    f"type « {type_brut} » non reconnu — « {_TYPE_PAR_DEFAUT} » retenu par défaut")
        else:
            type_cas = _TYPE_PAR_DEFAUT

        valeurs_requises = {"etapes": etapes, "resultat_attendu": resultat_attendu}
        libelles_requis = {"etapes": "étapes", "resultat_attendu": "résultat attendu"}
        manquants = [libelles_requis[c] for c in _CHAMPS_REQUIS_LIGNE if not valeurs_requises[c]]
        retenue = not manquants
        if manquants:
            avertissements.append(
                f"ligne ignorée par défaut — {', '.join(manquants)} manquant(s)")

        lignes.append(LigneCandidate(
            numero_ligne=i, titre=titre, preconditions=cell("preconditions"),
            etapes=etapes, resultat_attendu=resultat_attendu, section=cell("section"),
            priorite=priorite, statut_manuel=statut_manuel, testeur=cell("testeur"),
            date=cell("date"), type_cas=type_cas, commentaires=cell("commentaires"),
            identifiant=cell("identifiant"), retenue=retenue, avertissements=avertissements))
    return lignes


def hash_fichier(data: bytes) -> str:
    """Empreinte du fichier BRUT (octets, pas texte — un classeur Excel est un zip binaire) —
    même rôle que `spec_analyzer.spec_hash`, mais sur des octets plutôt qu'une chaîne, donc une
    fonction dédiée plutôt qu'un détour par un décodage qui n'aurait pas de sens ici."""
    return hashlib.sha1(data).hexdigest()[:12]


def conserver_original(fichier_hash: str, filename: str, data: bytes) -> Path:
    """Même convention que `spec_extract.conserver_original` : dossier adressé par le hash du
    contenu, nom réduit à son dernier segment (pas de traversée de chemin depuis un nom client)."""
    dossier = Path(config.DATA_DIR) / "imports_excel" / fichier_hash
    dossier.mkdir(parents=True, exist_ok=True)
    nom = Path(filename or "").name or "cahier_de_test.xlsx"
    chemin = dossier / nom
    chemin.write_bytes(data)
    return chemin


def chemin_original(fichier_hash: str) -> Path | None:
    """Le fichier conservé pour ce hash, ou `None` s'il a été perdu/jamais écrit — l'étape confirm
    le relit plutôt que de faire confiance à un aperçu côté client qui pourrait avoir changé."""
    dossier = Path(config.DATA_DIR) / "imports_excel" / fichier_hash
    if not dossier.is_dir():
        return None
    fichiers = list(dossier.iterdir())
    return fichiers[0] if fichiers else None


def ligne_vers_dict(ligne: LigneCandidate) -> dict:
    """`LigneCandidate` → vocabulaire des schémas API (`ExcelImportLigne`) — un seul endroit pour
    ce renommage, partagé par `preview` et par les tests, plutôt que répété dans chaque route."""
    return {
        "numero_ligne": ligne.numero_ligne, "titre": ligne.titre,
        "preconditions": ligne.preconditions, "test_steps": ligne.etapes,
        "expected_result": ligne.resultat_attendu, "section": ligne.section,
        "priority": ligne.priorite, "statut_manuel": ligne.statut_manuel,
        "testeur": ligne.testeur, "date": ligne.date, "type_cas": ligne.type_cas,
        "commentaires": ligne.commentaires, "identifiant": ligne.identifiant,
        "retenue": ligne.retenue, "avertissements": ligne.avertissements,
    }


def lire_classeur(data: bytes):
    """Le classeur ouvert, ou `FichierExcelInvalide` — jamais une exception openpyxl brute qui
    remonterait jusqu'à la route."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dépendance déclarée du projet
        raise FichierExcelInvalide("lecture Excel indisponible (openpyxl manquant)") from exc
    try:
        return openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise FichierExcelInvalide(f"classeur Excel illisible ou corrompu : {exc}") from exc
