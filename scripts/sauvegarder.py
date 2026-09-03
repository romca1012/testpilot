"""Sauvegarde et restauration de `data/testpilot.db`, appelées par le PLANIFICATEUR du système.

    python scripts/sauvegarder.py                                  (défaut : sauvegarde)
    python scripts/sauvegarder.py sauvegarder --garder 30
    python scripts/sauvegarder.py restaurer <fichier-de-sauvegarde> [--vers data/testpilot.db]

**Pourquoi un script et pas un thread en tâche de fond dans le serveur.** Un scheduler en Python
dans le process `uvicorn` ajoute un état de plus à surveiller (a-t-il bien tourné ? survit-il à un
redémarrage du serveur ? à un crash ?), pour un besoin que le SYSTÈME sait déjà rendre fiable — une
tâche planifiée Windows ou un timer `cron`/`systemd` survit au serveur, se journalise à sa manière
et ne consomme pas un thread applicatif pendant l'exécution. Ce script est conçu pour être appelé
en ligne de commande, sans rien connaître de qui l'invoque — voir `docs/DEPLOIEMENT-V1-BETA.md`
§6/§7 pour la commande exacte et le test de restauration.

**Ce que ce script sauvegarde, et ce qu'il NE sauvegarde PAS.** Seule `config.DB_PATH` est
copiée ici. `data/domain/*.json` (la cartographie mesurée de chaque application) est DÉJÀ sous
contrôle de version git (décision `0021`, voir `.gitignore` : `!/data/domain/`) — le dupliquer
créerait une deuxième « source de vérité » pour la même donnée, moins fiable que git (pas de
diff humainement relisible, pas d'historique de commits). Le vrai risque non couvert par git est
la BASE : elle change à chaque clic de l'interface, jamais commitée nulle part. `data/executions/`
(la trace brute des exécutions) grandit déjà sans purge par choix documenté (§7 de
`DEPLOIEMENT-V1-BETA.md`) — ce script ne la sauvegarde pas non plus : la répéter à chaque
sauvegarde ferait grossir la rétention elle-même sans fin, exactement le problème qu'elle évite
pour son propre compte. Limite assumée : une restauration ne recrée QUE le référentiel (base), pas
les artefacts d'exécution ni les règles apprises.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Exécuté directement (`python scripts/sauvegarder.py`) : le dépôt n'est pas forcément installé,
# on ajoute `src/` explicitement — même patron que les autres scripts opérationnels du dossier.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # après l'ajustement de sys.path ci-dessus, volontairement

# Granularité alignée sur `testpilot.store.db._sauvegarder_avant_migration` (la sauvegarde
# automatique avant migration) et sur la convention déjà vue dans ce dépôt
# (`testpilot.db.avant-nettoyage-20260805-104308`).
HORODATAGE = "%Y%m%d-%H%M%S"

# Nombre de sauvegardes conservées par défaut. Une par jour pendant 30 jours à quelques dizaines de
# Mo chacune reste négligeable ; au-delà, c'est à l'exploitant d'ajuster (`--garder`), pas à ce
# script de deviner combien d'espace disque il a le droit de prendre.
RETENTION_PAR_DEFAUT = 30

DOSSIER_PAR_DEFAUT = config.DATA_DIR / "sauvegardes"


def nom_sauvegarde(source: Path, horodatage: str | None = None) -> str:
    horodatage = horodatage or datetime.now(timezone.utc).strftime(HORODATAGE)
    return f"{source.name}.sauvegarde-{horodatage}"


def lister_sauvegardes(dossier: Path, nom_source: str) -> list[Path]:
    """Les sauvegardes d'une source donnée, TRIÉES DU PLUS ANCIEN AU PLUS RÉCENT.

    Tri LEXICOGRAPHIQUE sur le nom de fichier — l'horodatage `%Y%m%d-%H%M%S` trie dans le même
    ordre que le temps qu'il décrit, donc trier les noms EST trier chronologiquement. Pas besoin de
    `stat()` chaque fichier (plus lent, et une horloge système modifiée entre deux sauvegardes
    pourrait fausser un tri par date de modification — pas le nom, qui est écrit une fois).
    """
    return sorted(dossier.glob(f"{nom_source}.sauvegarde-*"))


def _purger_anciennes(dossier: Path, nom_source: str, garder: int) -> list[Path]:
    """Retire les sauvegardes au-delà des `garder` plus RÉCENTES. Politique de RÉTENTION explicite
    — jamais une croissance sans fin (l'écart documenté et assumé de `data/executions/`, qu'on ne
    répète pas ici). `garder <= 0` retirerait TOUT : refusé explicitement, ce n'est jamais ce que
    l'appelant veut dire (un `--garder 0` par erreur ne doit pas effacer toutes les sauvegardes)."""
    if garder <= 0:
        raise ValueError(f"garder doit être positif (reçu {garder}) — 0 supprimerait tout")
    fichiers = lister_sauvegardes(dossier, nom_source)
    a_retirer = fichiers[:-garder] if len(fichiers) > garder else []
    for f in a_retirer:
        f.unlink()
    return a_retirer


def _copier_a_chaud(source: Path, cible: Path) -> None:
    """Copie SQLite « à chaud », sûre même si le serveur écrit AU MÊME MOMENT.

    ⚠️ **Pourquoi pas `shutil.copy2`.** Ce script est appelé par un planificateur système, sans
    coordination avec le serveur — contrairement à la sauvegarde AVANT MIGRATION
    (`testpilot.store.db._sauvegarder_avant_migration`), qui ne s'exécute qu'au démarrage, quand
    rien d'autre n'écrit encore. Un `shutil.copy2` pendant une écriture capturerait un état
    intermédiaire (page à moitié réécrite) — exactement le risque déjà documenté en
    `docs/DEPLOIEMENT-V1-BETA.md` §6, qui impose d'arrêter le service avant une copie brute.
    L'API `sqlite3.Connection.backup()` copie page par page sous un verrou de lecture cohérent,
    conçue précisément pour sauvegarder une base EN COURS D'UTILISATION.
    """
    source_conn = sqlite3.connect(str(source))
    dest_conn = sqlite3.connect(str(cible))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()


def sauvegarder(source: Path | None = None, dossier: Path | None = None,
                garder: int = RETENTION_PAR_DEFAUT) -> Path:
    """Copie `source` (par défaut `config.DB_PATH`) vers `dossier`, horodatée, puis applique la
    rétention. Lève `FileNotFoundError` si `source` n'existe pas — mieux vaut échouer bruyamment
    qu'écrire silencieusement une sauvegarde absente que le planificateur croirait réussie."""
    source = Path(source) if source else config.DB_PATH
    dossier = Path(dossier) if dossier else DOSSIER_PAR_DEFAUT
    if not source.exists():
        raise FileNotFoundError(f"rien à sauvegarder : {source} n'existe pas")

    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / nom_sauvegarde(source)
    _copier_a_chaud(source, cible)
    _purger_anciennes(dossier, source.name, garder)
    return cible


def restaurer(sauvegarde: Path, destination: Path | None = None) -> Path:
    """Remplace `destination` (par défaut `config.DB_PATH`) par le contenu de `sauvegarde`.

    ⚠️ **DESTRUCTIF sur `destination`, sans confirmation ni sauvegarde préalable de celle-ci** —
    c'est un geste de restauration explicite (invoqué à la main, ou par le test de bout en bout qui
    accompagne ce script), pas un clic qu'on pourrait déclencher par erreur en l'appelant deux fois.
    Le répertoire parent de `destination` est créé si besoin — restaurer vers un chemin encore
    inexistant (une instance de contrôle, §7 de `docs/DEPLOIEMENT-V1-BETA.md`) est un usage voulu.
    """
    sauvegarde = Path(sauvegarde)
    destination = Path(destination) if destination else config.DB_PATH
    if not sauvegarde.exists():
        raise FileNotFoundError(f"sauvegarde introuvable : {sauvegarde}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sauvegarde, destination)
    return destination


def _cmd_sauvegarder(args: argparse.Namespace) -> int:
    cible = sauvegarder(args.source, args.dossier, args.garder)
    print(f"sauvegardé : {cible}  ({cible.stat().st_size // 1024} ko)")
    return 0


def _cmd_restaurer(args: argparse.Namespace) -> int:
    cible = restaurer(args.sauvegarde, args.vers)
    print(f"restauré   : {cible}  ({cible.stat().st_size // 1024} ko)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if config.DB_URL.lower().startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError(
            "Cette commande sauvegarde SQLite uniquement. PostgreSQL doit être sauvegardé par "
            "le service managé (snapshots + restauration testée) ou pg_dump; voir "
            "docs/POSTGRES-MIGRATION.md."
        )
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = parser.add_subparsers(dest="commande")

    p_sauvegarder = sous.add_parser("sauvegarder", help="copie horodatée + rétention (défaut)")
    p_sauvegarder.add_argument("--source", type=Path, default=None,
                               help="par défaut config.DB_PATH")
    p_sauvegarder.add_argument("--dossier", type=Path, default=None,
                               help="par défaut data/sauvegardes/")
    p_sauvegarder.add_argument("--garder", type=int, default=RETENTION_PAR_DEFAUT,
                               help=f"nombre de sauvegardes conservées (défaut {RETENTION_PAR_DEFAUT})")
    p_sauvegarder.set_defaults(fn=_cmd_sauvegarder)

    p_restaurer = sous.add_parser("restaurer", help="écrase une destination avec une sauvegarde")
    p_restaurer.add_argument("sauvegarde", type=Path)
    p_restaurer.add_argument("--vers", type=Path, default=None, help="par défaut config.DB_PATH")
    p_restaurer.set_defaults(fn=_cmd_restaurer)

    args = parser.parse_args(argv)
    if args.commande is None:
        # Aucune sous-commande : c'est l'appel attendu depuis le planificateur système — la
        # sauvegarde périodique, sans argument. `restaurer` reste volontairement explicite.
        return _cmd_sauvegarder(argparse.Namespace(source=None, dossier=None,
                                                    garder=RETENTION_PAR_DEFAUT))
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
