"""Sauvegarde et restauration de la base PostgreSQL (`TESTPILOT_DB_URL`), pendant de
`scripts/sauvegarder.py` (SQLite) pour l'autre moteur — lis ce fichier pour ce qu'AUCUN des deux
NE sauvegarde (`data/executions/`, `data/domain/`, ...), la logique s'applique pareil ici.

    python scripts/sauvegarder_postgresql.py                                  (défaut : sauvegarde)
    python scripts/sauvegarder_postgresql.py sauvegarder --garder 30
    python scripts/sauvegarder_postgresql.py restaurer <fichier-de-sauvegarde> [--vers <url>]

**Pourquoi un script SÉPARÉ, pas une branche dans `sauvegarder.py`.** Les deux moteurs n'ont
presque rien de commun dans le GESTE : SQLite copie un FICHIER local (`sqlite3.Connection.backup`,
« à chaud », page par page) ; PostgreSQL sérialise une base potentiellement DISTANTE, ce que seul
un outil externe sait faire correctement — `pg_dump`/`pg_restore`, invoqués en sous-processus,
jamais réimplémentés ici (un format de dump maison serait un pari perdu d'avance face au format
`pg_dump`, déjà éprouvé, qui gère les types, séquences, contraintes et l'ordre de restauration).
Un seul script aurait dû brancher sur le moteur à CHAQUE fonction (nommage, garde d'entrée, forme
de la source, outil invoqué) — plus de risque de mélanger les deux que de les séparer clairement.
Seule la politique de RÉTENTION est réellement partagée : `lister_sauvegardes`/`_purger_anciennes`
de `scripts.sauvegarder` sont réutilisées telles quelles ici, sans duplication — elles ne
connaissent que des noms de fichiers horodatés, jamais le moteur qui les a produits.

**Ce que ce script sauvegarde, et ce qu'il NE sauvegarde PAS.** Le CONTENU de la base PostgreSQL
désignée par `TESTPILOT_DB_URL` — schéma ET données, via `pg_dump --format=custom` (le format
« archive » de pg_dump : compressé, et le seul que `pg_restore` sait rejouer sélectivement).
Rien d'autre : `data/executions/` (trace brute des exécutions) et `data/domain/*.json`
(cartographie mesurée, déjà sous git) restent HORS périmètre — même limite assumée, même
justification que dans `sauvegarder.py`, quel que soit le moteur de base sous les repositories.

**Le mot de passe ne transite jamais en argument de ligne de commande.** Un argument de processus
reste visible (gestionnaire des tâches, `Get-Process -Id ... -Module`, `/proc` sur Linux) tant que
le programme tourne. `pg_dump`/`pg_restore` savent lire une connexion depuis les variables
d'environnement `PG*` (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) — c'est ce canal
qu'utilise ce script, jamais `--dbname=postgresql://user:motdepasse@...`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Exécuté directement (`python scripts/sauvegarder_postgresql.py`) : le dépôt n'est pas forcément
# installé. On ajoute `src/` (pour `testpilot`) ET la racine (pour `scripts`, réutilisé ci-dessous)
# — même patron que les autres scripts opérationnels du dossier, étendu d'un cran.
_RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RACINE / "src"))
sys.path.insert(0, str(_RACINE))

from scripts.sauvegarder import (
    RETENTION_PAR_DEFAUT,
    _purger_anciennes,
    nom_sauvegarde,
)
from testpilot import (
    config,
)

# Binaires configurables : une machine peut installer les outils client PostgreSQL hors du PATH
# système par défaut (ex. `/usr/lib/postgresql/16/bin` sur Debian sans le paquet `-client` en tête
# de PATH), ou vouloir cibler une version précise si plusieurs coexistent.
PG_DUMP_BIN = os.getenv("TESTPILOT_PG_DUMP_BIN", "pg_dump")
PG_RESTORE_BIN = os.getenv("TESTPILOT_PG_RESTORE_BIN", "pg_restore")

DOSSIER_PAR_DEFAUT = config.DATA_DIR / "sauvegardes"


def _verifier_outil(binaire: str) -> str:
    """Rend le chemin résolu de `binaire`, ou lève une erreur CLAIRE — jamais le `FileNotFoundError`
    brut de `subprocess` (qui ressemble à un bug du script, pas à un outil manquant sur le poste)."""
    chemin = shutil.which(binaire)
    if chemin is None:
        raise RuntimeError(
            f"« {binaire} » introuvable sur le PATH — les outils client PostgreSQL "
            "(pg_dump/pg_restore) ne sont pas installés sur cette machine. Installez le paquet "
            "postgresql-client (Debian/Ubuntu : `apt install postgresql-client`), `postgresql` "
            "(Homebrew), ou le programme d'installation officiel PostgreSQL (Windows), puis "
            "réessayez. Si l'outil est installé ailleurs que sur le PATH, positionnez "
            "TESTPILOT_PG_DUMP_BIN / TESTPILOT_PG_RESTORE_BIN vers le binaire exact."
        )
    return chemin


def _pg_connection_env(url: str) -> tuple[dict, str]:
    """Décompose une URL `postgresql[+psycopg]://user:pass@host:port/base` en variables
    d'environnement `PG*` que `pg_dump`/`pg_restore` lisent nativement, et rend aussi le nom de
    base pour les messages et l'argument explicite de `pg_restore`. `PGDATABASE` est indispensable
    à `pg_dump` : sans lui, PostgreSQL choisit par défaut une base portant le nom de l'utilisateur.
    """
    normalisee = url.replace("postgresql+psycopg://", "postgresql://", 1)
    p = urlsplit(normalisee)
    if p.scheme != "postgresql":
        raise ValueError(f"URL PostgreSQL attendue (postgresql://...), reçu : {url!r}")
    dbname = p.path.lstrip("/")
    if not dbname:
        raise ValueError(f"URL PostgreSQL sans nom de base : {url!r}")

    env = os.environ.copy()
    if p.hostname:
        env["PGHOST"] = p.hostname
    env["PGPORT"] = str(p.port or 5432)
    if p.username:
        env["PGUSER"] = unquote(p.username)
    if p.password:
        env["PGPASSWORD"] = unquote(p.password)
    env["PGDATABASE"] = dbname
    return env, dbname


def _url_par_defaut() -> str:
    if not config.DB_URL:
        raise ValueError(
            "aucune URL PostgreSQL : TESTPILOT_DB_URL n'est pas configurée (runtime actuellement "
            "SQLite — voir scripts/sauvegarder.py)")
    return config.DB_URL


def sauvegarder(url: str | None = None, dossier: Path | None = None,
                garder: int = RETENTION_PAR_DEFAUT) -> Path:
    """Dump `url` (par défaut `config.DB_URL`) vers `dossier`, horodaté, puis applique la
    rétention. Lève si les outils client sont absents, si l'URL est invalide, ou si `pg_dump`
    échoue — jamais une sauvegarde partielle qui se ferait passer pour une bonne."""
    url = url or _url_par_defaut()
    dossier = Path(dossier) if dossier else DOSSIER_PAR_DEFAUT
    dossier.mkdir(parents=True, exist_ok=True)
    pg_dump = _verifier_outil(PG_DUMP_BIN)
    env, dbname = _pg_connection_env(url)

    # Pas un fichier réel : un `Path` synthétique, uniquement pour réutiliser le nommage et la
    # rétention EXISTANTS de `sauvegarder.py` (basés sur `Path.name`), sans les dupliquer ici.
    source_nominale = Path(f"{dbname}.dump")
    cible = dossier / nom_sauvegarde(source_nominale)

    resultat = subprocess.run(
        [pg_dump, "--format=custom", "--no-owner", "--no-privileges", "--file", str(cible)],
        env=env, capture_output=True, text=True, check=False,  # returncode inspecté ci-dessous
    )
    if resultat.returncode != 0:
        cible.unlink(missing_ok=True)
        raise RuntimeError(
            f"pg_dump a échoué (code {resultat.returncode}) : {resultat.stderr.strip()}")

    _purger_anciennes(dossier, source_nominale.name, garder)
    return cible


def restaurer(sauvegarde: Path, url: str | None = None) -> str:
    """Remplace le CONTENU de la base `url` (par défaut `config.DB_URL`) par celui de
    `sauvegarde`, via `pg_restore --clean` (dépose les objets déjà présents avant de les
    recréer — nécessaire puisque la base cible porte déjà un schéma appliqué par Alembic).

    ⚠️ **DESTRUCTIF sur la base ciblée, sans confirmation ni sauvegarde préalable de celle-ci** —
    même geste explicite que `scripts.sauvegarder.restaurer` (SQLite) : invoqué à la main, ou par
    le test de bout en bout qui accompagne ce script, jamais un clic qu'on pourrait déclencher par
    erreur en l'appelant deux fois.

    `--single-transaction` : la restauration réussit ou échoue EN BLOC — jamais une base à moitié
    reconstruite si `pg_restore` est interrompu en cours de route.
    """
    sauvegarde = Path(sauvegarde)
    if not sauvegarde.exists():
        raise FileNotFoundError(f"sauvegarde introuvable : {sauvegarde}")
    url = url or _url_par_defaut()
    pg_restore = _verifier_outil(PG_RESTORE_BIN)
    env, dbname = _pg_connection_env(url)

    resultat = subprocess.run(
        [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-privileges",
         "--single-transaction", "--dbname", dbname, str(sauvegarde)],
        env=env, capture_output=True, text=True, check=False,  # returncode inspecté ci-dessous
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"pg_restore a échoué (code {resultat.returncode}) : {resultat.stderr.strip()}")
    return dbname


def _cmd_sauvegarder(args: argparse.Namespace) -> int:
    cible = sauvegarder(args.url, args.dossier, args.garder)
    print(f"sauvegardé : {cible}  ({cible.stat().st_size // 1024} ko)")
    return 0


def _cmd_restaurer(args: argparse.Namespace) -> int:
    dbname = restaurer(args.sauvegarde, args.vers)
    print(f"restauré   : base « {dbname} » depuis {args.sauvegarde}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Toute erreur attendue (outil absent, mauvaise URL, sauvegarde introuvable...) sort ici en
    # UNE ligne lisible sur stderr, jamais en trace Python brute — même discipline que
    # scripts/migrate_sqlite_to_postgres.py. Une trace complète reste utile pour un bug RÉEL
    # (imprévu) : elle continue de sortir normalement, ce `try` ne l'avale pas.
    try:
        return _main(argv)
    except RuntimeError as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    if not config.DB_URL.lower().startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError(
            "Cette commande sauvegarde PostgreSQL uniquement (TESTPILOT_DB_URL). Le runtime "
            "actuel n'a pas cette variable positionnée sur une URL PostgreSQL — voir "
            "scripts/sauvegarder.py pour SQLite."
        )
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = parser.add_subparsers(dest="commande")

    p_sauvegarder = sous.add_parser("sauvegarder", help="pg_dump horodaté + rétention (défaut)")
    p_sauvegarder.add_argument("--url", default=None, help="par défaut TESTPILOT_DB_URL")
    p_sauvegarder.add_argument("--dossier", type=Path, default=None,
                               help="par défaut data/sauvegardes/")
    p_sauvegarder.add_argument("--garder", type=int, default=RETENTION_PAR_DEFAUT,
                               help=f"nombre de sauvegardes conservées (défaut {RETENTION_PAR_DEFAUT})")
    p_sauvegarder.set_defaults(fn=_cmd_sauvegarder)

    p_restaurer = sous.add_parser("restaurer",
                                  help="pg_restore --clean : écrase le contenu d'une base")
    p_restaurer.add_argument("sauvegarde", type=Path)
    p_restaurer.add_argument("--vers", default=None, help="URL cible, par défaut TESTPILOT_DB_URL")
    p_restaurer.set_defaults(fn=_cmd_restaurer)

    args = parser.parse_args(argv)
    if args.commande is None:
        # Aucune sous-commande : l'appel attendu depuis le planificateur système — sauvegarde
        # périodique sans argument. `restaurer` reste volontairement explicite.
        return _cmd_sauvegarder(argparse.Namespace(url=None, dossier=None,
                                                    garder=RETENTION_PAR_DEFAUT))
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
