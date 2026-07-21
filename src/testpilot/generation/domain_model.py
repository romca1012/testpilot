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


def chemin_du_modele(project_id: int) -> Path:
    """Un modèle PAR PROJET — décision `0005` appliquée à ce qui lui avait échappé.

    ⚠️ **C'était un modèle par TYPE DE CONNECTEUR** (`odoo.json`), et c'est le défaut exact que
    `0005` a corrigé pour le runtime : deux projets sur Odoo mais deux **instances** différentes
    (le portail d'un client, puis celui d'un autre) partageaient une seule cartographie. Les
    tests du second auraient été générés depuis les routes et les champs du premier — « affiché
    ≠ réel » (§4.6) appliqué à la connaissance du domaine, et une source d'erreurs techniques
    impossible à diagnostiquer.

    Le domaine appartient à l'**application testée**, pas à la famille de logiciel. Deux projets
    Odoo peuvent avoir des modules, des champs et des routes différents.
    """
    return DOMAIN_DIR / f"projet-{int(project_id)}.json"


def chemin_legacy(connector_type: str = "odoo") -> Path:
    """L'ancien emplacement, indexé par connecteur. Lu en REPLI, jamais écrit."""
    return DOMAIN_DIR / f"{(connector_type or 'odoo').lower()}.json"


@lru_cache(maxsize=4)
def _charger(chemin: str, mtime: float) -> dict:
    """Cache indexé sur (chemin, mtime) : régénérer le modèle l'invalide sans redémarrage.

    Sans le `mtime`, un `lru_cache` servirait éternellement la version d'avant le re-crawl — et on
    croirait le modèle à jour. Le motif « affiché ≠ réel » (§4.6), appliqué à un cache.
    """
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def charger_modele(projet: dict | None) -> dict | None:
    """Le modèle du PROJET, ou `None` s'il n'y en a pas.

    **`None` n'est pas une erreur** : tant qu'aucun modèle n'est mesuré ni relu, le smoke-check se
    tait. Best-effort — un modèle illisible ne doit jamais casser l'affichage d'un cas, mais il ne
    doit pas non plus disparaître en silence (§4.6) : on le journalise.

    **Repli sur l'ancien fichier par connecteur**, et il est STRICT : le fichier legacy porte la
    `base_url` de l'instance qu'il a mesurée, et on ne l'accepte que si elle correspond à celle du
    projet. Sans cette vérification, le repli réintroduirait exactement le bug qu'on corrige — un
    projet servi par la cartographie d'une autre instance. Mieux vaut aucun modèle qu'un faux.
    """
    if not projet:
        return None
    chemin = chemin_du_modele(projet["id"])
    if not chemin.exists():
        chemin = _legacy_utilisable(projet)
        if chemin is None:
            return None
    try:
        return _charger(str(chemin), chemin.stat().st_mtime)
    except (OSError, json.JSONDecodeError):
        logger.exception("[domaine] modèle %s illisible — le smoke-check sera muet sur ce cas",
                         chemin)
        return None


def _normalise_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def _legacy_utilisable(projet: dict) -> Path | None:
    """L'ancien `{connecteur}.json`, mais SEULEMENT s'il a mesuré la même instance."""
    chemin = chemin_legacy(projet.get("connector_type") or "odoo")
    if not chemin.exists():
        return None
    try:
        mesure = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if _normalise_url(mesure.get("base_url")) == _normalise_url(projet.get("base_url")):
        logger.info("[domaine] projet %s : repli sur l'ancien modèle %s (même instance) — "
                    "relancer l'exploration le rangera au bon endroit", projet["id"], chemin.name)
        return chemin
    logger.warning("[domaine] projet %s : l'ancien modèle %s décrit une AUTRE instance (%s ≠ %s) "
                   "— ignoré. Lancez l'exploration de ce projet.", projet["id"], chemin.name,
                   mesure.get("base_url"), projet.get("base_url"))
    return None


def _meme_route(route_modele: str, url: str) -> bool:
    """`/formulaire/{id}` correspond-il à `/formulaire/78` ou à une URL absolue ? (placeholders
    joker, comparaison par segments)."""
    a = [s for s in route_modele.strip("/").split("/") if s]
    b = [s for s in url.split("?")[0].rstrip("/").split("/") if s and "://" not in s]
    b = b[-len(a):] if len(b) >= len(a) else b
    if len(a) != len(b):
        return False
    return all(x.startswith("{") or x == y for x, y in zip(a, b))


def formulaires_requis(modele: dict | None, routes) -> list[dict]:
    """Les formulaires visés par `routes`, avec leurs champs REQUIS — la contrainte à donner au
    générateur (`[{route, requis: [{name, tag, options}]}]`).

    ⚠️ **C'est la donnée que la génération n'avait jamais.** L'annuaire porte `required` par champ
    depuis qu'il existe, mais **seul le gate le lisait** : le prompt disait à l'agent « observe le
    formulaire réel pour connaître les champs requis » — une consigne qui dépend de l'exploration,
    donc du tirage. Mesuré (2026-07-19) : sur la même spec, une génération a rempli 6 champs +
    soumission explicite, la suivante **2 champs sur 8** sans soumission — donc un test qui ne
    crée rien et 4 scénarios `non_conforme`. On donne désormais la liste au lieu de la faire
    deviner (motif `0021` : *lire plutôt que deviner*).

    Dédupliqué par ensemble de champs requis : deux routes qui exigent exactement la même chose
    (mesuré : `/formulaire/{id}` et `/product/{id}/accessories`) ne sont pas répétées.
    """
    if not modele or not modele.get("pages"):
        return []
    trouves, vus = [], set()
    for route, infos in (modele.get("pages") or {}).items():
        if not any(_meme_route(route, str(u)) for u in routes or []):
            continue
        requis = [c for c in (infos.get("champs") or []) if c.get("name") and c.get("required")]
        if not requis:
            continue
        signature = frozenset(c["name"] for c in requis)
        if signature in vus:
            continue
        vus.add(signature)
        trouves.append({
            "route": route,
            # `type` exposé depuis le 2026-07-21 : sans lui, l'agent traitait un
            # `<input type="file">` comme du texte → `InvalidStateError`, 2 échecs techniques
            # sur 3 mesurés. L'annuaire le connaissait ; personne ne le transmettait.
            "requis": [{"name": c["name"], "tag": c.get("tag", ""), "type": c.get("type", ""),
                        "options": [v for v, _ in (c.get("options") or [])]} for c in requis],
        })
    return trouves


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
