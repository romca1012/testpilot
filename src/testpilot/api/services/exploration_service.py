"""Exploration d'un projet — cartographier l'application AVANT d'écrire des tests contre elle.

C'est l'étape 2 du flux produit : on crée un projet, on saisit son connecteur, **on explore
l'application**, et seulement ensuite on écrit des cas. L'exploration est **payée une fois par
projet** ; toutes les générations suivantes lisent sa cartographie au lieu de deviner.

⚠️ **Aucun LLM ici.** Le crawl est un parcours Playwright déterministe : il ouvre des pages, lit
les formulaires et les liens, et écrit ce qu'il a vu. C'est ce qui distingue un **fait mesuré**
d'une **supposition** — la décision `0022` n°2.b exige que les routes, champs et valeurs viennent
de l'annuaire, plus d'un modèle qui lit la spec.

⚠️ **La cartographie est propre au PROJET, pas au type de connecteur** (décision `0005` appliquée
à ce qui lui avait échappé). Deux projets Odoo peuvent être deux instances différentes, avec des
modules, des routes et des champs différents.

La mesure est une **photo, et elle vieillit** : tout ce qui la consomme doit rester détective et
dire sa date (cf. `domain_model`). Ré-explorer est un geste humain, jamais automatique — sinon une
régression de l'application (un champ disparu) serait enregistrée comme la nouvelle vérité, et le
smoke-check se tairait. C'est le faux négatif que ce projet traque.
"""

from __future__ import annotations

import json
import logging
import sys
import types
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

from testpilot.generation import domain_model
from testpilot.store.repositories import ProjectRepo

logger = logging.getLogger(__name__)

# job_id → {status: running|done|failed, project_id, error, resume}
_JOBS: dict[str, dict] = {}

MAX_PAGES_DEFAUT = 60


class ExplorationError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | no_connection | already_running
        self.detail = detail


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def job_en_cours(project_id: int) -> str | None:
    """Le job d'exploration en cours pour ce projet, s'il y en a un."""
    for jid, job in _JOBS.items():
        if job.get("project_id") == project_id and job.get("status") == "running":
            return jid
    return None


def etat(project_id: int, projet: dict | None = None) -> dict:
    """Ce que l'écran affiche : y a-t-il une cartographie, de quand, et combien couvre-t-elle."""
    modele = domain_model.charger_modele(projet) if projet else None
    job_id = job_en_cours(project_id)
    pages = (modele or {}).get("pages") or {}
    transitions = (modele or {}).get("transitions") or {}
    champs = [c for i in pages.values() for c in (i.get("champs") or [])]
    return {
        "explored": bool(pages),
        "running": job_id is not None,
        "job_id": job_id or "",
        "mesure_le": (modele or {}).get("mesure_le", ""),
        "pages": len(pages),
        "transitions": sum(len(v) for v in transitions.values()),
        "champs": len(champs),
        # ⚠️ Le compte des RÈGLES DE VALIDATION est affiché parce qu'il est le seul signe VISIBLE
        # qu'une cartographie est à jour. Le 2026-07-21, une ré-exploration lancée depuis
        # l'interface a réécrit l'annuaire à l'identique — code de crawl périmé chargé en mémoire —
        # en affichant « terminée » : 37 routes, 373 champs, exactement comme avant. Rien à l'écran
        # ne pouvait le trahir. Les routes et les champs bougent peu ; les règles, elles, n'existent
        # que depuis la mesure enrichie. Zéro règle sur un portail qui en a = mesure à refaire.
        "contraintes": sum(1 for c in champs if c.get("contraintes")),
        "resume": domain_model.resume(modele),
    }


def start_exploration(conn, project_id: int) -> tuple[str, dict]:
    """Valide la demande et prépare le job. Renvoie (job_id, paramètres de la tâche de fond)."""
    projet = ProjectRepo(conn).get(project_id)
    if projet is None:
        raise ExplorationError("not_found", f"projet {project_id} introuvable")
    # On refuse AVANT de lancer un navigateur : sans connexion complète, le crawl échouerait après
    # plusieurs secondes sur une erreur réseau incompréhensible — ou pire, explorerait l'instance
    # par défaut de la machine et écrirait un annuaire qui ne décrit PAS ce projet (2026-07-24).
    # Le message dit quoi corriger.
    from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion
    try:
        verifier_connexion(projet)
    except ConnexionIncomplete as err:
        raise ExplorationError("no_connection", err.message()) from err
    if job_en_cours(project_id):
        # Deux crawls simultanés écriraient le même fichier : le dernier gagnerait, et la mesure
        # rendue serait un mélange de deux passages.
        raise ExplorationError("already_running", "une exploration est déjà en cours sur ce projet")

    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "project_id": project_id, "error": "", "resume": ""}
    return job_id, {"project_id": project_id, "connexion": {
        "base_url": projet.get("base_url") or "", "database": projet.get("database") or "",
        "username": projet.get("username") or "", "password": projet.get("password") or "",
        "connector_type": projet.get("connector_type") or "odoo",
        "nom": projet.get("name") or "",
    }}


def _crawl(connexion: dict, max_pages: int) -> dict:
    """Le parcours lui-même. Isolé pour être remplaçable en test (il exige un vrai navigateur).

    Réutilise `scripts/crawl_domaine.py` — sa logique BFS, sa normalisation de routes et sa
    tolérance au crash du navigateur sont éprouvées sur une mesure réelle (38 routes). La
    dupliquer ici en ferait deux versions à maintenir, qui divergeraient.
    """
    racine = Path(__file__).resolve().parents[4]
    for chemin in (racine / "scripts", racine / "behave_runtime" / "steps_library"):
        if str(chemin) not in sys.path:
            sys.path.insert(0, str(chemin))

    from playwright.sync_api import sync_playwright

    import _base_helpers as H
    import crawl_domaine as cd

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = types.SimpleNamespace(
            page=nav.new_page(), odoo_url=connexion["base_url"], odoo_db=connexion["database"],
            odoo_user=connexion["username"], odoo_password=connexion["password"])
        H.playwright_login(ctx)
        pages, transitions, onglets = cd.crawler(ctx, nav, connexion["base_url"], max_pages)
        try:
            nav.close()
        except Exception:
            pass  # le navigateur a pu mourir : la mesure, elle, est faite

    return {
        "pages": pages,
        "transitions": {k: sorted(v) for k, v in transitions.items()},
        "onglets_internes": {k: sorted(v) for k, v in onglets.items()},
    }


def run_exploration(job_id: str, *, project_id: int, connexion: dict,
                    max_pages: int = MAX_PAGES_DEFAUT) -> None:
    """Tâche de fond : cartographie l'application DU PROJET et range le résultat sous son id."""
    try:
        mesure = _crawl(connexion, max_pages)
        if not mesure.get("pages"):
            # Zéro page n'est pas une cartographie : l'écrire ferait passer un échec pour une
            # mesure « vide mais valide », et la génération croirait le domaine connu.
            _JOBS[job_id].update(
                status="failed",
                error="aucune page atteinte — vérifiez l'URL et les identifiants du projet")
            return

        modele = {
            "connector_type": connexion["connector_type"],
            "projet": connexion["nom"],
            "project_id": project_id,
            "base_url": connexion["base_url"],
            "mesure_le": date.today().isoformat(),
            "methode": "crawl déterministe Playwright, aucun LLM",
            **mesure,
        }
        chemin = domain_model.chemin_du_modele(project_id)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(modele, ensure_ascii=False, indent=2), encoding="utf-8")

        n_transitions = sum(len(v) for v in modele["transitions"].values())
        _JOBS[job_id].update(
            status="done",
            resume=f"{len(modele['pages'])} routes, {n_transitions} transitions")
        logger.info("[exploration] projet %s cartographié : %s → %s",
                    project_id, _JOBS[job_id]["resume"], chemin.name)
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[exploration] job %s en échec : %s", job_id, exc)
        _JOBS[job_id].update(status="failed", error=str(exc)[:300])
