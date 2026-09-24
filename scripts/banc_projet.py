"""Crée (idempotent) le projet TestPilot « Banc Odoo <version> » et le fait explorer (lot 04).

    python scripts/banc_projet.py --version 17.0 [--url http://127.0.0.1:18069] [--sans-exploration]

- Le projet pointe sur l'instance LOCALE du banc (jamais une instance client : hôte refusé sinon).
- L'exploration (crawl déterministe Playwright, aucun LLM) écrit l'annuaire du projet ; il est ensuite COPIÉ,
  versionné, dans ``banc/domaine/odoo-<version>.json`` — l'annuaire d'un banc jetable doit pouvoir se relire
  sans relancer le crawl.
- Isolation : sans ``TESTPILOT_DATA_DIR``, un dossier de données JETABLE est utilisé (la base de production
  n'est jamais touchée) ; le chemin est affiché.

Rejouable : un projet du même nom est réutilisé (mis à jour), jamais dupliqué.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

RACINE = Path(__file__).resolve().parents[1]
DOMAINE_VERSIONNE = RACINE / "banc" / "domaine"
HOTES_AUTORISES = {"127.0.0.1", "localhost", "::1"}


def nom_du_projet(version: str) -> str:
    return f"Banc Odoo {version}"


def _preparer_environnement() -> Path:
    dossier = Path(os.environ.get("TESTPILOT_DATA_DIR") or tempfile.mkdtemp(prefix="banc_projet_data_"))
    os.environ["TESTPILOT_DATA_DIR"] = str(dossier)
    sys.path.insert(0, str(RACINE / "src"))
    sys.path.insert(0, str(RACINE))
    return dossier


def assurer_le_projet(conn, version: str, url: str, base: str = "banc", utilisateur: str = "admin",
                      mot_de_passe: str = "admin") -> int:
    """Le projet du banc, créé s'il n'existe pas, mis à jour sinon. Rend son identifiant."""
    from testpilot.store.repositories import ProjectRepo

    hote = urlparse(url).hostname or ""
    if hote not in HOTES_AUTORISES:
        raise SystemExit(f"Refus : le banc n'accepte qu'une instance LOCALE, pas « {hote} ».")
    repo = ProjectRepo(conn)
    nom = nom_du_projet(version)
    existant = next((p for p in repo.list_all() if p["name"] == nom), None)
    if existant:
        conn.execute("UPDATE project SET base_url=?, database=?, username=?, connector_version=? WHERE id=?",
                     (url, base, utilisateur, version, existant["id"]))
        from testpilot.store import secrets as secrets_mod
        conn.execute("UPDATE project SET password=? WHERE id=?", (secrets_mod.chiffrer(mot_de_passe), existant["id"]))
        conn.commit()
        return int(existant["id"])
    return repo.create(name=nom, description=f"Banc de mesure de la fiabilité du verdict (Odoo {version}).",
                       connector_type="odoo", connector_version=version, base_url=url, database=base,
                       username=utilisateur, password=mot_de_passe)


def explorer(conn, project_id: int) -> str:
    """Lance l'exploration SYNCHRONE du projet ; rend son résumé ou lève en cas d'échec."""
    from testpilot.api.services import exploration_service as expl

    job_id, params = expl.start_exploration(conn, project_id)
    expl.run_exploration(job_id, **params)
    job = expl.get_job(job_id) or {}
    if job.get("status") != "done":
        raise RuntimeError(f"exploration en échec : {job.get('error') or job}")
    return job.get("resume", "")


def versionner_le_domaine(project_id: int, version: str) -> Path:
    from testpilot.generation import domain_model

    source = domain_model.chemin_du_modele(project_id)
    DOMAINE_VERSIONNE.mkdir(parents=True, exist_ok=True)
    cible = DOMAINE_VERSIONNE / f"odoo-{version}.json"
    shutil.copyfile(source, cible)
    return cible


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="17.0", choices=["16.0", "17.0", "18.0"])
    parser.add_argument("--url", default=os.environ.get("BANC_URL", "http://127.0.0.1:18069"))
    parser.add_argument("--base", default="banc")
    parser.add_argument("--utilisateur", default="admin")
    parser.add_argument("--mot-de-passe", default="admin")
    parser.add_argument("--sans-exploration", action="store_true", help="crée le projet sans lancer le crawl")
    args = parser.parse_args(argv)

    dossier = _preparer_environnement()
    from testpilot import config
    from testpilot.store.db import get_initialized_db

    conn = get_initialized_db(Path(config.DB_PATH))
    project_id = assurer_le_projet(conn, args.version, args.url, args.base, args.utilisateur, args.mot_de_passe)
    print(f"Projet « {nom_du_projet(args.version)} » : id {project_id} (données : {dossier})")
    if args.sans_exploration:
        return 0
    print("Exploration :", explorer(conn, project_id))
    print("Annuaire versionné :", versionner_le_domaine(project_id, args.version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
