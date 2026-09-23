"""Garde-fou anti-pollution : aucun test ne doit toucher le VRAI `data/` du poste.

⚠️ **Pourquoi ce fichier existe.** Un test réel (`test_transport_refus.py`, avant correctif)
lançait un vrai `BehaveRunner(project_id=7)` sans isoler `regles_apprises.REGLES_DIR` — chaque
exécution de la suite écrivait une vraie ligne dans le vrai `data/regles-apprises/projet-7.jsonl`
du poste de développement, sur un projet qui n'existe même pas en base. Trouvé en observant le
fichier grossir pendant une suite de tests, pas par relecture.

Le correctif ponctuel (isoler CE test) ne protège pas contre le PROCHAIN oubli du même genre —
aucun `conftest.py` n'existait pour l'empêcher structurellement. Celui-ci ne connaît aucun
mécanisme précis (règles apprises, artefacts d'exécution, base…) : il fingerprint le vrai
`data/` avant/après CHAQUE test et fait échouer le test qui l'a changé, quel que soit le chemin
par lequel il l'a fait. Zéro faux positif attendu : les 30 fichiers de tests qui touchent déjà
`DATA_DIR`/`DB_PATH`/`DOMAIN_DIR`/`REGLES_DIR` isolent tous correctement (vérifié).

Échappatoire explicite pour un futur test qui aurait une vraie raison de toucher le disque réel :
`@pytest.mark.donnees_reelles` (déclaré dans `pyproject.toml`). Aucun test actuel n'en a besoin.

⚠️ **Limite assumée, découverte en construisant ce garde-fou** : il fingerprint le `data/` réel,
pas « ce que les tests ont fait ». Si l'application tourne en parallèle (un utilisateur réel sur
`localhost:8000` pendant que la suite passe) et écrit dans ce même `data/`, le test qui se trouve
être en cours à ce moment-là sera accusé à tort. Ne pas faire tourner la suite en même temps qu'on
utilise l'application sur ce poste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot import config

# Résolu UNE FOIS, avant qu'un test ne monkeypatch `config.DATA_DIR` — c'est le vrai chemin sur
# le disque du poste qu'on protège, pas le symbole (qui peut être redirigé légitimement vers
# `tmp_path` par le test lui-même).
_VRAI_DATA_DIR = Path(config.DATA_DIR).resolve()


def _empreinte() -> dict[str, int]:
    """Taille de chaque fichier sous le vrai `data/` — la TAILLE seule, pas la date.

    ⚠️ **La date de modification a été essayée et abandonnée.** Mesuré sur ce poste (Windows) :
    des faux positifs apparaissent et disparaissent d'un lancement à l'autre de la MÊME suite,
    sans aucun changement de code — l'indexeur/antivirus du système touche des `mtime` sous
    `data/` sans toucher leur contenu. La taille est un signal plus grossier mais STABLE : chaque
    fuite réellement trouvée jusqu'ici (une ligne JSONL ajoutée, un fichier créé) change une
    taille ou une existence. Limite assumée, pas cachée : une écriture qui remplacerait un
    contenu par un autre de MÊME taille resterait invisible — borne acceptée plutôt qu'un
    mécanisme plus cher (hash de contenu) sur 23 Mo de données à chaque test.

    Ne lève jamais : un fichier qui disparaît entre le `stat` et la lecture (verrou Windows,
    course avec un autre processus) doit faire échouer le TEST fautif, pas le garde-fou lui-même.
    """
    empreinte: dict[str, int] = {}
    if not _VRAI_DATA_DIR.exists():
        return empreinte
    for chemin in _VRAI_DATA_DIR.rglob("*"):
        if not chemin.is_file():
            continue
        # SQLite crée et retire ces compagnons transactionnels pendant une connexion. Leur
        # existence est transitoire et ne constitue pas une donnée applicative persistée ; la
        # vraie base (`testpilot.db`) reste, elle, fingerprintée et continue donc de faire
        # échouer tout test qui la modifie réellement.
        if chemin.name.endswith(("-journal", "-wal", "-shm")):
            continue
        try:
            empreinte[str(chemin)] = chemin.stat().st_size
        except OSError:
            continue
    return empreinte


@pytest.fixture(autouse=True)
def _garde_donnees_reelles(request):
    """Échoue si un test a écrit dans le vrai `data/` du poste — voir le docstring du module."""
    if request.node.get_closest_marker("donnees_reelles"):
        yield
        return

    avant = _empreinte()
    yield
    apres = _empreinte()

    if avant == apres:
        return

    crees = sorted(set(apres) - set(avant))
    supprimes = sorted(set(avant) - set(apres))
    modifies = sorted(p for p in avant.keys() & apres.keys() if avant[p] != apres[p])
    detail = "; ".join(
        f"{libelle}: {chemins}"
        for libelle, chemins in (("créés", crees), ("modifiés", modifies), ("supprimés", supprimes))
        if chemins
    )
    pytest.fail(
        f"[garde données réelles] {request.node.nodeid!r} a modifié le VRAI {_VRAI_DATA_DIR} "
        f"({detail}). Isoler avec monkeypatch (config.DATA_DIR/DB_PATH ou le module dérivé — "
        f"REGLES_DIR, DOMAIN_DIR…) ou marquer @pytest.mark.donnees_reelles si c'est délibéré.",
        pytrace=False,
    )


@pytest.fixture(autouse=True)
def _connecte_par_defaut(monkeypatch, request):
    """Les comptes utilisateurs (2026-08-07) rendent la connexion OBLIGATOIRE sur toute l'API —
    avant, `config.ACCESS_PASSWORD` vide (le défaut en test) désactivait le verrou entièrement.
    Sans ce bouchon, les ~250 tests qui appellent l'API via `TestClient` sans jamais se connecter
    recevraient tous un 401, pour une raison sans rapport avec ce qu'ils vérifient réellement.

    ⚠️ Ce n'est PAS un remplacement inconditionnel : dès qu'un COOKIE de session est présent (un
    test qui s'est VRAIMENT connecté — `test_la_suppression_en_lot_trace_QUI`,
    `test_comptes_utilisateurs.py`), le vrai mécanisme fait foi, y COMPRIS quand il refuse
    à raison (compte désactivé, jeton invalide) — sinon vérifier un rejet deviendrait impossible
    à tester, la complaisance masquerait exactement ce qu'on cherche à prouver. Le compte Admin
    de complaisance n'intervient que si AUCUN cookie n'est présent du tout — le cas de la grande
    majorité des tests, qui n'appellent jamais `/api/auth/login`.

    Échappatoire explicite (même patron que `@pytest.mark.donnees_reelles`) pour le seul test qui
    vérifie le comportement SANS AUCUN bouchon, cookie ou pas : `@pytest.mark.sans_bouchon_auth`.
    """
    if request.node.get_closest_marker("sans_bouchon_auth"):
        return

    from testpilot.api import access

    reelle = access.utilisateur_actuel

    def _bouchon(conn, request):
        if request.cookies.get(access.COOKIE) is not None:
            return reelle(conn, request)
        return {"id": 0, "username": "test", "role": access.ROLE_ADMIN, "is_active": 1}

    monkeypatch.setattr(access, "utilisateur_actuel", _bouchon)


@pytest.fixture(autouse=True)
def _scheduler_desactive(monkeypatch):
    """Coupe la boucle de planification (migration 43) pendant TOUTE la suite — quel que soit
    `.env`.

    ⚠️ **Bug trouvé en instrumentant l'instabilité aléatoire du sweep complet (2026-09-22).** Le
    commentaire dans `src/testpilot/api/app.py` (`lifespan`) promet que la boucle « ne démarre QUE
    si explicitement activée (jamais pendant les tests par défaut) » — mais `config.SCHEDULER_ENABLED`
    est lu depuis `.env` au chargement du module `config`, AU NIVEAU PROCESSUS : quand `.env` du
    dépôt contient `TESTPILOT_SCHEDULER_ENABLED=true` (utile pour tester la planification en
    local), ce `true` s'applique aussi au processus pytest, silencieusement, sans qu'aucun test ne
    l'ait demandé.

    Neuf fichiers de tests (`test_assignation_cas.py`, `test_deploiement_securite.py`,
    `test_notifications_email.py`, `test_pieces_jointes.py`, `test_postgres_runtime.py`,
    `test_reglages_instance.py`, `test_saisie_manuelle.py`, `test_tracabilite_declenchement.py`,
    `test_type_et_etat.py`) ont une fixture `client` qui fait `with TestClient(app) as c: ...` —
    la forme CONTEXTE, qui déclenche réellement le `lifespan` de FastAPI (vérifié dans
    `starlette/testclient.py` : un `TestClient(app)` sans `with` ne le déclenche PAS, seul
    `__enter__` le fait). Chaque test de ces fichiers qui utilise `client` démarre donc un nouveau
    thread daemon `testpilot-scheduler` ; sortir du `with` ferme le `lifespan` mais PAS ce thread
    (`_boucle_planification` tourne dans sa propre boucle `while True`, jamais annulée). Sur un
    sweep complet, ça peut accumuler jusqu'à une centaine de threads résiduels.

    Chaque thread se réveille après `time.sleep(config.SCHEDULER_TICK_SECONDS)` puis appelle
    `get_initialized_db()` **sans argument** — donc sur `config.DB_PATH` tel qu'il est au moment de
    son réveil, pas au moment de sa création. Comme `config.DB_PATH` est ré-écrit par
    `monkeypatch.setattr` à chaque nouveau test isolé (`tmp_path`), un thread résiduel qui se
    réveille au mauvais moment retombe sur la base du test EN COURS à cet instant précis, en
    parallèle de ce test qui vient de créer cette même base fraîche → course avec
    `_run_migrations` (symptôme observé : `sqlite3.OperationalError: duplicate column name: ...`
    ou `table X has no column named ...`, 1 FAILED + quelques ERROR, différents à chaque run,
    même backend réel arrêté).

    Échappatoire explicite pour un futur test qui voudrait vraiment vérifier le scheduler lui-même :
    `monkeypatch.setattr(config, "SCHEDULER_ENABLED", True)` dans CE test (cette fixture tourne
    avant le corps du test, donc un `monkeypatch` posé dans le test prend le dessus).
    """
    monkeypatch.setattr(config, "SCHEDULER_ENABLED", False)
