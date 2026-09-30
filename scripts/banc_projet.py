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


# ⚠️ **Trouvé le 2026-09-30 (mesure de clôture du lot 09)** : 14 des 16 fichiers `specs/banc/*.md`
# déclarent des personas secondaires (« Comptes de test : banc_commercial (Ventes / Utilisateur),
# banc_manager (Ventes / Administrateur, Stock, Facturation) ») — mais ce script ne les a JAMAIS
# enregistrés comme comptes secondaires du projet (`project_account`, D8). Les utilisateurs Odoo
# EUX-MÊMES existaient déjà sur l'instance (`res.users`, ids 8 et 9) — seul le lien TestPilot
# manquait. Conséquence mesurée : `PreconditionNonRemplieError` sur 9 des 15 cas du corpus,
# systématiquement, rendant I3/I4 incalculables sur ce corpus (le blocage survient avant que la
# génération/le verdict n'entrent en jeu). Mots de passe posés ici par l'admin de l'instance LOCALE
# de test (jamais une instance cliente — même garde `HOTES_AUTORISES` que le reste du script).
_COMPTES_SECONDAIRES = (
    {"label": "banc_commercial", "mot_de_passe": "banc_commercial_test_2026",
     "business_role": "Ventes / Utilisateur"},
    {"label": "banc_manager", "mot_de_passe": "banc_manager_test_2026",
     "business_role": "Ventes / Administrateur, Stock, Facturation"},
)


def _assurer_comptes_secondaires(conn, project_id: int, client) -> None:
    """Réinitialise le mot de passe Odoo de chaque compte de test (admin sur l'instance LOCALE —
    HOTES_AUTORISES l'a déjà vérifié avant cet appel) puis l'enregistre comme compte secondaire
    du projet (D8). Idempotent : un compte déjà enregistré est mis à jour, jamais dupliqué."""
    from testpilot.store.repositories import ProjectAccountRepo

    repo = ProjectAccountRepo(conn)
    existants = {c["label"]: c["id"] for c in repo.liste(project_id)}
    for compte in _COMPTES_SECONDAIRES:
        utilisateurs = client.env["res.users"].search([("login", "=", compte["label"])], limit=1)
        if not utilisateurs:
            continue  # cet utilisateur Odoo n'existe pas sur cette instance — rien à lier
        client.env["res.users"].browse(utilisateurs[0]).write({"password": compte["mot_de_passe"]})
        if compte["label"] in existants:
            repo.modifier(project_id, existants[compte["label"]],
                          username=compte["label"], password=compte["mot_de_passe"],
                          business_role=compte["business_role"])
        else:
            repo.create(project_id, label=compte["label"], username=compte["label"],
                       password=compte["mot_de_passe"], business_role=compte["business_role"])


def assurer_le_projet(conn, version: str, url: str, base: str = "banc", utilisateur: str = "admin",
                      mot_de_passe: str = "admin", *, synchroniser_comptes: bool = True) -> int:
    """Le projet du banc, créé s'il n'existe pas, mis à jour sinon. Rend son identifiant.

    `synchroniser_comptes=True` (défaut, usage réel — CLI, `banc_generation.py`) : enregistre
    aussi les comptes secondaires de test (`banc_commercial`/`banc_manager`) via un VRAI appel RPC
    quand l'utilisateur Odoo correspondant existe sur l'instance — best-effort, jamais bloquant.

    ⚠️ **`synchroniser_comptes=False` dans les tests unitaires** (`tests/test_banc_generation.py`,
    docstring du fichier : « les parties SANS LLM ni Odoo ») : sans ce paramètre, l'appel RPC
    ajouté ici rendrait ces tests DÉPENDANTS d'un vrai serveur accessible sur le port testé —
    passant silencieusement quand le banc du porteur tourne par coïncidence (mesuré : c'est le cas
    sur ce poste), échouant ou traînant ailleurs. Comportement non déterministe trouvé en ajoutant
    ce correctif (2026-09-30), corrigé avant qu'il ne s'installe."""
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
        project_id = int(existant["id"])
    else:
        project_id = repo.create(
            name=nom, description=f"Banc de mesure de la fiabilité du verdict (Odoo {version}).",
            connector_type="odoo", connector_version=version, base_url=url, database=base,
            username=utilisateur, password=mot_de_passe)

    if synchroniser_comptes:
        try:
            import odoorpc
            client = odoorpc.ODOO(urlparse(url).hostname, protocol="jsonrpc", port=urlparse(url).port or 8069)
            client.login(base, utilisateur, mot_de_passe)
            _assurer_comptes_secondaires(conn, project_id, client)
        except Exception as exc:  # best-effort : une instance sans ces comptes reste utilisable
            print(f"[banc_projet] comptes secondaires non synchronisés ({type(exc).__name__}: {exc})")

    return project_id


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
