"""Le modèle du domaine — source de vérité VERSIONNÉE, jamais générée par LLM (décision `0021`).

Le fichier vit dans `data/domain/{connecteur}.json`, produit par `scripts/crawl_domaine.py`
(crawl déterministe, aucun LLM) et **relu par un humain** avant d'être adopté : un diff git dit
exactement ce qui a bougé dans l'application.

⚠️ **Pourquoi versionné et pas crawlé à chaud** — trois raisons, dans l'ordre :

1. **Un crawl à chaud rendrait le gate dépendant d'Odoo.** Ouvrir la page d'un cas déclencherait
   4 minutes de navigation ; l'application indisponible casserait l'écran. Le gate doit rester
   consultable, toujours.
2. **Un modèle qui change tout seul n'est pas une référence.** Si l'application régresse (un champ
   disparaît), un crawl à chaud enregistrerait la régression comme la nouvelle vérité — et le
   smoke-check se tairait. **C'est exactement le faux négatif que ce projet traque** : la référence
   doit être ce qu'un humain a validé, pas ce que l'application dit aujourd'hui.
3. Le diff est la revue. `git diff data/domain/odoo.json` montre les champs ajoutés/retirés.

⚠️ **Le modèle est une PHOTO, et elle vieillit.** Tout ce qui le consomme doit être **détective**
(§6 du brief + borne du principe 2), et dire la date de la mesure. Un modèle absent n'est pas une
erreur : le smoke-check se tait — mais son silence ne vaut **pas** validation (voir `smoke_check`).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from testpilot import config

logger = logging.getLogger(__name__)

DOMAIN_DIR = config.DATA_DIR / "domain"


def chemin_du_modele(connector_type: str = "odoo") -> Path:
    """Un modèle PAR CONNECTEUR : le domaine d'Odoo n'est pas celui du prochain ERP (§8)."""
    return DOMAIN_DIR / f"{(connector_type or 'odoo').lower()}.json"


@lru_cache(maxsize=4)
def _charger(chemin: str, mtime: float) -> dict:
    """Cache indexé sur (chemin, mtime) : régénérer le modèle l'invalide sans redémarrage.

    Sans le `mtime`, un `lru_cache` servirait éternellement la version d'avant le re-crawl — et on
    croirait le modèle à jour. Le motif « affiché ≠ réel » (§4.6), appliqué à un cache.
    """
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def charger_modele(connector_type: str = "odoo") -> dict | None:
    """Le modèle du connecteur, ou `None` s'il n'y en a pas.

    **`None` n'est pas une erreur** : tant qu'aucun modèle n'est mesuré ni relu, le smoke-check se
    tait. Best-effort — un modèle illisible ne doit jamais casser l'affichage d'un cas, mais il ne
    doit pas non plus disparaître en silence (§4.6) : on le journalise.
    """
    chemin = chemin_du_modele(connector_type)
    if not chemin.exists():
        return None
    try:
        return _charger(str(chemin), chemin.stat().st_mtime)
    except (OSError, json.JSONDecodeError):
        logger.exception("[domaine] modèle %s illisible — le smoke-check sera muet sur ce cas",
                         chemin)
        return None


def resume(modele: dict | None) -> str:
    """Une ligne pour un humain : ce que le modèle couvre, et de quand il date."""
    if not modele or not modele.get("pages"):
        return "aucun modèle du domaine"
    pages = modele["pages"]
    champs = sum(len(i.get("champs") or []) for i in pages.values())
    selects = sum(1 for i in pages.values() for c in (i.get("champs") or [])
                  if c.get("tag") == "select" and c.get("options"))
    return (f"{len(pages)} routes, {champs} champs, {selects} select — "
            f"mesuré le {modele.get('mesure_le', '?')}")
