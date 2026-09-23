"""Mémoire de libellés de menu APPRIS par exécution réelle (Lot 2 du plan de fiabilisation de la
génération, 2026-09-23 — ferme la boucle laissée ouverte par « Chantier F »).

Constat mesuré (Sapian, 2026-09-22, cas C127) : `discover_menus` capture le libellé d'un menu
dans LA LANGUE de la session qui a fait le crawl, pas nécessairement celle de la session qui
exécute le test — « Surveys » capturé, « Sondages » affiché en run réel. La résolution adaptative
de `navigate_menu` (`_repli_adaptatif`, `behave_runtime/steps_library/_base_helpers.py`) retrouve
déjà le VRAI libellé au moment de l'exécution, mais seulement pour CE run : rien ne le renvoie vers
la génération, qui reproposera le même libellé faux à la prochaine régénération — le bug se répète
indéfiniment au lieu de s'apprendre.

Ce module persiste, par PROJET (une dérive mesurée sur une application n'apprend rien sur une
autre — même raison que `selector_memory`/`regles_apprises`), le dernier libellé RÉEL qui a permis
de franchir chaque segment de menu. `_section_modeles_backoffice` (`generation/prompt.py`) le lit
pour préférer ce libellé confirmé au libellé brut de `discover_menus`.

⚠️ **Mêmes trois arbitrages que `testpilot.execution.selector_memory` et
`testpilot.generation.regles_apprises`, pour les mêmes raisons** (lire leur en-tête pour le
détail) :

- **Un fichier JSONL par projet, pas une table SQLite** — le sous-processus Behave qui écrit le
  sidecar ne connaît pas la base.
- **`enregistrer()` best-effort, jamais fatal** — un disque plein ne doit pas faire tomber une
  exécution qui a créé de vraies données dans l'application testée.
- **Cache `(chemin, mtime, taille)`**, pas `mtime` seul.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from testpilot import config

logger = logging.getLogger(__name__)

MEMOIRE_DIR = config.DATA_DIR / "menus-appris"

FORMAT_VERSION = 1

# Même politique que `regles_apprises._MAX_REGLES_LUES` : le fichier est append-only, il grandit ;
# au-delà, les plus RÉCENTES priment.
_MAX_LIGNES_LUES = 2000


@dataclass(frozen=True)
class LibelleAppris:
    """Le dernier fait connu : CE segment cherché a été réellement atteint via CE libellé."""

    segment_original: str  # ce que `discover_menus`/le Gherkin cherchait — peut être faux.
    libelle_reel: str      # ce qui a VRAIMENT permis de cliquer, mesuré en run réel.
    menu_path: str = ""    # le chemin complet du Gherkin où le segment a été rencontré (contexte).
    mesure_le: str = ""
    execution_id: int | None = None

    def cle(self) -> str:
        return self.segment_original


def chemin(project_id: int) -> Path:
    """Un fichier PAR PROJET — un libellé appris sur une application n'apprend rien sur une
    autre (même raison que `selector_memory.chemin`)."""
    return MEMOIRE_DIR / f"projet-{int(project_id)}.jsonl"


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _texte(valeur, limite: int = 200) -> str:
    return ("" if valeur is None else str(valeur))[:limite]


def _depuis_json(brut: dict) -> LibelleAppris | None:
    segment, libelle = _texte(brut.get("segment_original")), _texte(brut.get("libelle_reel"))
    if not segment or not libelle:
        return None
    return LibelleAppris(
        segment_original=segment, libelle_reel=libelle, menu_path=_texte(brut.get("menu_path")),
        mesure_le=_texte(brut.get("mesure_le")), execution_id=brut.get("execution_id"))


@lru_cache(maxsize=8)
def _lire(chemin_str: str, mtime: float, taille: int) -> tuple[LibelleAppris, ...]:
    """Cache indexé sur (chemin, mtime, taille) — même motif que `selector_memory._lire`."""
    lignes = Path(chemin_str).read_text(encoding="utf-8").splitlines()
    par_cle: dict[str, LibelleAppris] = {}
    for numero, ligne in enumerate(lignes[-_MAX_LIGNES_LUES:], start=1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            fait = _depuis_json(json.loads(ligne))
        except (ValueError, TypeError, AttributeError):
            fait = None
        if fait is None:
            logger.warning("[menus appris] %s ligne %d illisible — sautée", chemin_str, numero)
            continue
        # La DERNIÈRE ligne pour un segment fait foi : le fichier est un journal, la carte qu'on
        # en tire n'a besoin que de l'état le plus récent par segment.
        par_cle[fait.cle()] = fait
    return tuple(par_cle.values())


def charger(project_id: int | None) -> dict[str, LibelleAppris]:
    """Le dernier libellé réel appris par segment, pour ce projet. **Ne lève jamais** — l'absence
    de fichier est l'état normal d'un projet dont aucune navigation n'a jamais eu besoin du repli
    adaptatif."""
    if project_id is None:
        return {}
    fichier = chemin(project_id)
    try:
        if not fichier.exists():
            return {}
        info = fichier.stat()  # UN seul appel : mtime et taille doivent décrire le même instant
        return {f.cle(): f for f in _lire(str(fichier), info.st_mtime, info.st_size)}
    except OSError:
        logger.exception("[menus appris] %s illisible — la génération travaillera sans", fichier)
        return {}


def enregistrer(project_id: int | None, faits, *, execution_id: int | None = None) -> int:
    """Ajoute les libellés appris de CE run au fichier du projet. Rend le nombre de lignes écrites.

    **Best-effort, jamais fatal** — même arbitrage que `selector_memory.enregistrer`.

    `faits` : les entrées consignées par `navigate_menu` dans son sidecar (`segment_original`,
    `libelle_reel`, `menu_path`), un dict ou un objet portant les mêmes champs par attribut — le
    sous-processus Behave n'importe pas ce module.
    """
    if project_id is None or not faits:
        return 0
    lignes = []
    horodatage = _maintenant()
    for brut in faits:
        lecture = brut.get if isinstance(brut, dict) else lambda nom, d=None: getattr(brut, nom, d)
        segment, libelle = _texte(lecture("segment_original")), _texte(lecture("libelle_reel"))
        if not segment or not libelle:
            continue
        lignes.append(json.dumps(
            {"segment_original": segment, "libelle_reel": libelle,
             "menu_path": _texte(lecture("menu_path")), "v": FORMAT_VERSION,
             "mesure_le": horodatage, "execution_id": execution_id},
            ensure_ascii=False, sort_keys=True))
    if not lignes:
        return 0
    fichier = chemin(project_id)
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with fichier.open("a", encoding="utf-8") as flux:
            flux.write("\n".join(lignes) + "\n")
    except OSError:
        logger.exception("[menus appris] écriture impossible dans %s — les libellés de ce run "
                         "sont perdus, le run lui-même reste valide", fichier)
        return 0
    return len(lignes)
