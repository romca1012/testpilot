"""Migration de données du lot 06 (D6, F6) — assigne `profil_instance` aux projets dont un cas
courant utilise déjà les steps déplacés vers un profil (`employee_front_role_ids`, « je force le
nom du ticket à … », « … avec accessoires »).

⚠️ **Pourquoi ce script, pas une migration `db.py`.** Les migrations `db.py`/Alembic ne touchent
QUE le schéma (colonnes, contraintes) — jamais les DONNÉES d'un projet réel. Décider QUELS projets
reçoivent QUEL profil est un jugement métier sur le contenu de CETTE base, à faire une fois, par le
porteur, sur SA base réelle (absente de ce cloud, cf. rapport du lot).

Usage (dry-run PAR DÉFAUT — ne modifie rien tant que `--appliquer` n'est pas passé) ::

    python scripts/migration_lot06_profil_instance.py
    python scripts/migration_lot06_profil_instance.py --db chemin/vers/testpilot.db
    python scripts/migration_lot06_profil_instance.py --appliquer

Idempotent : un projet qui a DÉJÀ un `profil_instance` non vide n'est JAMAIS touché (ni recalculé,
ni écrasé) — relancer ce script après une première application ne fait rien de plus.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

# Marqueurs → profil suggéré. Le volet ODOO (`employee_front_role_ids`) et le volet GÉNÉRIQUE
# (« je force le nom du ticket ») du profil « sapian » sont réunis sous UN SEUL nom de profil,
# comme le lit `BehaveRunner._profil_files` (un `profil_instance` désigne les DEUX volets, chacun
# inclus s'il existe un fichier pour lui).
_MARQUEURS = {
    "sapian": ("employee_front_role_ids", "je force le nom du ticket à"),
    "demo_saucedemo": ("avec accessoires",),
}


def _detecter(texte: str) -> set[str]:
    texte_lower = texte.lower()
    return {profil for profil, marqueurs in _MARQUEURS.items()
            if any(m.lower() in texte_lower for m in marqueurs)}


def _projets_a_migrer(conn: sqlite3.Connection) -> list[dict]:
    """Un projet par ligne : `{id, name, profil_instance_actuel, profil_suggere, preuve}` — SEULS
    les projets sans `profil_instance` actuel ET dont au moins un cas COURANT matche un marqueur."""
    lignes = conn.execute(
        "SELECT p.id AS project_id, p.name AS project_name, p.profil_instance,"
        "       tc.id AS case_id, tc.title AS case_title,"
        "       v.feature_content, v.steps_content"
        "   FROM project p"
        "   JOIN module m ON m.project_id = p.id AND m.deleted_at = ''"
        "   JOIN test_case tc ON tc.module_id = m.id AND tc.deleted_at = ''"
        "   JOIN test_case_version v ON v.id = tc.current_version_id"
        "  WHERE p.deleted_at = ''"
    ).fetchall()
    par_projet: dict[int, dict] = {}
    for ligne in lignes:
        if ligne["profil_instance"]:
            continue  # déjà réglé explicitement — jamais recalculé (idempotence)
        trouve = _detecter((ligne["feature_content"] or "") + "\n" + (ligne["steps_content"] or ""))
        if not trouve:
            continue
        entree = par_projet.setdefault(ligne["project_id"], {
            "project_id": ligne["project_id"], "project_name": ligne["project_name"],
            "profils_suggeres": set(), "preuves": [],
        })
        entree["profils_suggeres"] |= trouve
        entree["preuves"].append(f"cas #{ligne['case_id']} « {ligne['case_title']} »"
                                 f" ({', '.join(sorted(trouve))})")
    return list(par_projet.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=None, help="Chemin de la base (défaut : TESTPILOT_DATA_DIR/testpilot.db, "
                                                    "ou data/testpilot.db à la racine du dépôt)")
    parser.add_argument("--appliquer", action="store_true",
                        help="Écrit réellement `profil_instance` — sans cette option, dry-run seul (rien n'est modifié)")
    args = parser.parse_args()

    if args.db:
        chemin = Path(args.db)
    else:
        from testpilot import config
        chemin = Path(config.DATA_DIR) / "testpilot.db"
    if not chemin.is_file():
        print(f"Base introuvable : {chemin} — rien à migrer.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    try:
        candidats = _projets_a_migrer(conn)
        if not candidats:
            print("Aucun projet à migrer (aucun cas courant ne référence les steps déplacés, "
                 "ou tous les projets concernés ont déjà un `profil_instance`).")
            return 0

        print(f"{len(candidats)} projet(s) candidat(s) — base : {chemin}\n")
        ambigus = []
        for c in candidats:
            profils = sorted(c["profils_suggeres"])
            marque = " (AMBIGU — deux profils suggérés, ignoré)" if len(profils) > 1 else ""
            if len(profils) > 1:
                ambigus.append(c)
            print(f"  projet #{c['project_id']} « {c['project_name']} » → "
                 f"profil suggéré : {', '.join(profils)}{marque}")
            for preuve in c["preuves"]:
                print(f"      - {preuve}")
        print()

        a_appliquer = [c for c in candidats if len(c["profils_suggeres"]) == 1]
        if not args.appliquer:
            print(f"Dry-run (par défaut) : rien n'a été écrit. Relancer avec --appliquer pour "
                 f"régler `profil_instance` sur les {len(a_appliquer)} projet(s) NON ambigu(s) "
                 f"ci-dessus ({len(ambigus)} ambigu(s) resteraient à trancher à la main).")
            return 0

        for c in a_appliquer:
            (profil,) = c["profils_suggeres"]
            conn.execute("UPDATE project SET profil_instance=? WHERE id=? AND profil_instance=''",
                        (profil, c["project_id"]))
        conn.commit()
        print(f"{len(a_appliquer)} projet(s) mis à jour. {len(ambigus)} ambigu(s) laissé(s) "
             f"tel(s) quel(s) — à trancher manuellement dans l'écran Projets.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
