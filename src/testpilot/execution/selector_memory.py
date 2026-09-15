"""Mémoire de DÉRIVE des sélecteurs entre deux exécutions (plan de consolidation, §1.2 — audit
« Le pari Mabl/Testim », 2026-09-15).

Le constat de l'audit : `locate_field` (`behave_runtime/steps_library/_base_helpers.py`) recalcule
sa cascade à chaque appel, sans jamais comparer au palier qui avait résolu le même champ la
DERNIÈRE fois. La robustesse de la cascade est réelle, mais invisible — impossible de distinguer
« ce champ s'adapte » de « ce champ a eu de la chance », et impossible de PROUVER à un porteur ou
un client que le système s'adapte, faute du moindre signal quand un champ change de palier.

Ce module ne CHANGE rien à la résolution elle-même : il se contente d'enregistrer, projet par
projet, le dernier palier connu pour chaque (module, identifiant), et de signaler un changement —
une DÉRIVE — quand le palier d'aujourd'hui diffère de celui d'hier. Jamais bloquant : une dérive
est un fait à surveiller, pas un échec.

⚠️ **Mêmes trois arbitrages que `testpilot.generation.regles_apprises`, pour les mêmes raisons**
(lire son en-tête pour le détail) :

- **Un fichier JSONL par projet, pas une table SQLite.** Le lecteur (`locate_field`, via son
  sidecar) tourne dans le sous-processus Behave, qui ne connaît pas la base — la comparaison et la
  persistance se font ICI, côté outil, jamais côté sous-processus.
- **`enregistrer()` best-effort, jamais fatal.** Un disque plein ne doit pas faire tomber une
  exécution qui a créé de vraies données dans l'application testée.
- **Cache `(chemin, mtime, taille)`**, pas `mtime` seul — deux écritures rapprochées peuvent
  partager la même résolution de mtime sur certains systèmes de fichiers.
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

MEMOIRE_DIR = config.DATA_DIR / "selecteurs"

FORMAT_VERSION = 1

# Plafond de lecture : le fichier est append-only, il grandit. Au-delà, les plus RÉCENTES priment
# (même politique que `regles_apprises._MAX_REGLES_LUES`).
_MAX_LIGNES_LUES = 5000


@dataclass(frozen=True)
class ResolutionSelecteur:
    """Le dernier fait connu : CE champ, dans CE module, a été résolu par CE palier."""

    module: str
    ident: str
    tier: str
    mesure_le: str = ""
    execution_id: int | None = None

    def cle(self) -> tuple[str, str]:
        return (self.module, self.ident)


@dataclass(frozen=True)
class Derive:
    """Un changement de palier détecté pour un champ, entre son dernier palier connu et celui-ci."""

    module: str
    ident: str
    ancien_tier: str
    nouveau_tier: str


def chemin(project_id: int) -> Path:
    """Un fichier PAR PROJET — même raison que l'annuaire (0005) et les règles apprises : une
    dérive mesurée sur une application n'apprend rien sur une autre."""
    return MEMOIRE_DIR / f"projet-{int(project_id)}.jsonl"


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _texte(valeur, limite: int = 200) -> str:
    return ("" if valeur is None else str(valeur))[:limite]


def _depuis_json(brut: dict) -> ResolutionSelecteur | None:
    ident, tier = _texte(brut.get("ident")), _texte(brut.get("tier"))
    if not ident or not tier:
        return None
    return ResolutionSelecteur(
        module=_texte(brut.get("module")), ident=ident, tier=tier,
        mesure_le=_texte(brut.get("mesure_le")), execution_id=brut.get("execution_id"))


@lru_cache(maxsize=8)
def _lire(chemin_str: str, mtime: float, taille: int) -> tuple[ResolutionSelecteur, ...]:
    """Cache indexé sur (chemin, mtime, taille) — même motif que `domain_model._charger` et
    `regles_apprises._lire`, pour la même raison (mtime seul est trop grossier)."""
    lignes = Path(chemin_str).read_text(encoding="utf-8").splitlines()
    par_cle: dict[tuple[str, str], ResolutionSelecteur] = {}
    for numero, ligne in enumerate(lignes[-_MAX_LIGNES_LUES:], start=1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            resolution = _depuis_json(json.loads(ligne))
        except (ValueError, TypeError, AttributeError):
            resolution = None
        if resolution is None:
            logger.warning("[mémoire sélecteurs] %s ligne %d illisible — sautée",
                           chemin_str, numero)
            continue
        # La DERNIÈRE ligne pour une clé donnée fait foi : le fichier est un journal, la carte
        # qu'on en tire n'a besoin que de l'état le plus récent par (module, ident).
        par_cle[resolution.cle()] = resolution
    return tuple(par_cle.values())


def charger(project_id: int | None) -> dict[tuple[str, str], ResolutionSelecteur]:
    """Le dernier palier connu par (module, ident). **Ne lève jamais** — absence de fichier =
    aucune résolution jamais mesurée pour ce projet, l'état nominal d'un projet neuf."""
    if project_id is None:
        return {}
    fichier = chemin(project_id)
    try:
        if not fichier.exists():
            return {}
        info = fichier.stat()  # UN seul appel : mtime et taille doivent décrire le même instant
        return {r.cle(): r for r in _lire(str(fichier), info.st_mtime, info.st_size)}
    except OSError:
        logger.exception("[mémoire sélecteurs] %s illisible — la dérive ne sera pas détectée",
                         fichier)
        return {}


def enregistrer(project_id: int | None, module: str, resolutions,
                *, execution_id: int | None = None) -> list[Derive]:
    """Persiste les résolutions de CE run et rend les dérives détectées par rapport au run
    précédent. **Best-effort, jamais fatal** — même arbitrage que `regles_apprises.enregistrer`.

    `resolutions` : les faits consignés par `locate_field` dans son sidecar, un dict (ou objet)
    par champ résolu, portant `ident` et `tier`. Le sous-processus Behave n'importe pas ce module.

    ⚠️ **La comparaison se fait AVANT l'écriture**, contre l'état persisté au début de CET appel —
    deux champs résolus au même run ne se comparent jamais entre eux, seulement contre l'historique.
    """
    if project_id is None or not resolutions:
        return []
    connues = charger(project_id)
    derives: list[Derive] = []
    lignes = []
    horodatage = _maintenant()
    for brut in resolutions:
        lecture = brut.get if isinstance(brut, dict) else lambda nom, d=None: getattr(brut, nom, d)
        ident, tier = _texte(lecture("ident")), _texte(lecture("tier"))
        if not ident or not tier:
            continue
        precedente = connues.get((module, ident))
        if precedente is not None and precedente.tier != tier:
            derives.append(Derive(module=module, ident=ident,
                                   ancien_tier=precedente.tier, nouveau_tier=tier))
        lignes.append(json.dumps(
            {"module": module, "ident": ident, "tier": tier, "v": FORMAT_VERSION,
             "mesure_le": horodatage, "execution_id": execution_id},
            ensure_ascii=False, sort_keys=True))
    if not lignes:
        return derives
    fichier = chemin(project_id)
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with fichier.open("a", encoding="utf-8") as flux:
            flux.write("\n".join(lignes) + "\n")
    except OSError:
        logger.exception("[mémoire sélecteurs] écriture impossible dans %s — la dérive de ce run "
                         "n'est pas persistée, le run lui-même reste valide", fichier)
        return derives
    return derives
