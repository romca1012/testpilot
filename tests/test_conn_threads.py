"""La connexion d'une requête survit au passage d'un thread à l'autre (HTTP 500 intermittent).

Bug trouvé à l'écran (2026-07-16), pas par la suite : l'API tombait en 500 dès que deux requêtes
se chevauchaient —

    sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same
    thread. The object was created in thread id 9356 and this is thread id 26672.

Cause : FastAPI exécute une dépendance `yield` SYNCHRONE (`api.deps.get_conn`) dans un thread du
pool, et l'endpoint dans un AUTRE thread du même pool. La connexion — pourtant créée par requête
et fermée à la fin — change donc de thread en cours de route.

Pourquoi 200 tests verts ne l'avaient pas vu : `TestClient` est synchrone et sérialise tout ; sans
requêtes concurrentes, le pool réutilise le même thread et le bug ne se manifeste jamais. Il a
fallu un vrai navigateur chargeant l'arbre EN PARALLÈLE de la page pour le déclencher.
"""

import sqlite3
import threading

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


def _dans_un_autre_thread(fn):
    """Exécute `fn` dans un thread distinct et renvoie (résultat, exception)."""
    box: dict = {}

    def run():
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 — on veut l'exception telle quelle
            box["error"] = exc

    t = threading.Thread(target=run)
    t.start()
    t.join(timeout=10)
    return box.get("result"), box.get("error")


def test_connexion_utilisable_depuis_un_autre_thread(tmp_path, monkeypatch):
    """Reproduit EXACTEMENT le motif FastAPI : créer ici, utiliser là.

    Sans `check_same_thread=False`, ce test lève ProgrammingError — c'est le HTTP 500 qu'on a vu.
    """
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "t.db")   # thread « dépendance »
    try:
        result, error = _dans_un_autre_thread(lambda: ProjectRepo(conn).list_all())  # thread « endpoint »
        assert error is None, f"la connexion doit survivre au changement de thread : {error!r}"
        assert result == []
    finally:
        conn.close()


def test_connexion_fermable_depuis_un_autre_thread(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # Le `finally` de la dépendance peut lui aussi tourner ailleurs que là où la connexion est née.
    conn = get_initialized_db(tmp_path / "t.db")
    _, error = _dans_un_autre_thread(conn.close)
    assert error is None


def test_requetes_concurrentes_ne_cassent_pas(tmp_path, monkeypatch):
    """Le vrai motif serveur : une connexion PAR requête, plusieurs requêtes en même temps.

    ⚠️ `check_same_thread=False` lève le contrôle de propriété, il n'ajoute AUCUN verrou :
    l'invariant « une connexion par requête » reste ce qui rend l'ensemble correct. Ce test le
    fige — s'il devenait une connexion globale partagée, on retomberait dans des courses.
    """
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    db = tmp_path / "t.db"
    get_initialized_db(db).close()   # schéma créé une fois

    erreurs: list[BaseException] = []

    def une_requete():
        conn = get_initialized_db(db)
        try:
            ProjectRepo(conn).create(name=f"p{threading.get_ident()}", description="")
            ProjectRepo(conn).list_all()
        except BaseException as exc:  # noqa: BLE001
            erreurs.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=une_requete) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not erreurs, f"requêtes concurrentes en échec : {erreurs[:2]}"
