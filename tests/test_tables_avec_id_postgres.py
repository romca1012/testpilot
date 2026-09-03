"""Garde-fou anti-dérive — `portable_connection._TABLES_AVEC_ID` doit rester EXACT.

Sous PostgreSQL, `PortableCursor.lastrowid` n'est renseigné QUE pour les tables listées dans
`_TABLES_AVEC_ID` (portable_connection.py) : c'est cette liste qui décide si `INSERT ... RETURNING
id` est ajouté. Trouvé en pratique (2026-09-03), en comparant la liste au VRAI schéma plutôt qu'en
la relisant à l'œil : deux noms fantômes (`generation_attempt`, `test_scenario_result` — aucune
table réelle ne s'appelle ainsi) et une vraie table manquante (`scenario_result`, remplie à CHAQUE
scénario Behave exécuté — `ExecutionRepo.add_scenario_result` aurait levé `TypeError` au premier
run réel contre PostgreSQL, `int(None)`).

Ce fichier ne se contente pas de corriger l'instance d'aujourd'hui : il empêche la même dérive de
revenir en silence à la prochaine table ajoutée. Ne nécessite AUCUN PostgreSQL réel — analyse
statique du code, tourne dans la suite normale.
"""

from __future__ import annotations

import re
from pathlib import Path

from testpilot.store import schema_sa
from testpilot.store.portable_connection import _TABLES_AVEC_ID

_REPOSITORIES_PATH = Path(__file__).resolve().parent.parent / "src/testpilot/store/repositories.py"

# `INSERT INTO <table>` suivi, dans les ~15 lignes suivantes, d'un `.lastrowid` — assez large pour
# couvrir le motif `cur = self.conn.execute("INSERT INTO ...", ...)` puis `return int(cur.lastrowid)`
# quelques lignes plus bas, sans capturer l'INSERT d'une autre méthode entre les deux (la fenêtre
# est bornée, pas illimitée).
_INSERT_PUIS_LASTROWID = re.compile(
    r'INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:(?!INSERT\s+INTO).){0,600}?\.lastrowid',
    re.IGNORECASE | re.DOTALL,
)


def _tables_qui_utilisent_lastrowid() -> set[str]:
    source = _REPOSITORIES_PATH.read_text(encoding="utf-8")
    return {m.group(1).lower() for m in _INSERT_PUIS_LASTROWID.finditer(source)}


def test_toutes_les_tables_de_TABLES_AVEC_ID_existent_vraiment():
    """Aucun nom fantôme : chaque entrée doit être une VRAIE table du schéma."""
    tables_reelles = set(schema_sa.metadata.tables.keys())
    fantomes = _TABLES_AVEC_ID - tables_reelles
    assert not fantomes, (
        f"_TABLES_AVEC_ID contient des noms qui ne correspondent à AUCUNE table réelle : "
        f"{sorted(fantomes)} — vérifiée contre schema_sa.metadata, pas retapée à l'œil"
    )


def test_toute_table_qui_utilise_lastrowid_est_dans_TABLES_AVEC_ID():
    """Le cœur du garde-fou : une future méthode `INSERT ... ; return int(cur.lastrowid)` sur une
    table absente de la liste échouerait en silence sous PostgreSQL (lastrowid = None) — ce test
    la repère AVANT le premier run réel, pas après."""
    utilisees = _tables_qui_utilisent_lastrowid()
    manquantes = utilisees - _TABLES_AVEC_ID
    assert not manquantes, (
        f"Table(s) utilisant `.lastrowid` dans repositories.py mais absente(s) de "
        f"_TABLES_AVEC_ID (portable_connection.py) : {sorted(manquantes)} — sous PostgreSQL, "
        f"`cur.lastrowid` y vaudrait toujours None"
    )
    # Garde-fou sur le garde-fou : si la regex ne trouve plus RIEN, elle a probablement dérivé
    # (renommage de `.lastrowid`, changement de style d'écriture) plutôt que le code n'utilisant
    # plus jamais ce motif — un test muet est pire qu'un test qui échoue.
    assert utilisees, "la détection statique n'a rien trouvé — le motif regex a probablement dérivé"
