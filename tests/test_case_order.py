"""Ordre d'AFFICHAGE manuel des cas dans leur module (décision 0009, migration 6).

⚠️ Cette décision **amende** 0006/§2.4 (« pas de colonne `position` »). Ce que 0006 refusait :
une position **décorative**, jamais alimentée, laissant croire à un ordre d'exécution (celle de
l'ancien prototype). Celle-ci est **réellement honorée** par le tri et ne promet rien sur
l'exécution — c'est ce qui la rend honnête. Les tests ci-dessous figent les deux moitiés de cette
promesse : l'ordre EST honoré, et il n'atteint JAMAIS l'exécution.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import _SCHEMA_VERSION, _column_names, get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "o.db")
    yield c
    c.close()


@pytest.fixture
def module(conn):
    pid = ProjectRepo(conn).create(name="P")
    return ModuleRepo(conn).create(project_id=pid, name="M")


def _titres(conn, module_id):
    return [c["title"] for c in CaseRepo(conn).list_all(module_id=module_id)]


# ── Le tri honore réellement la position ──────────────────────────────────────

def test_ordre_manuel_reellement_honore(conn, module):
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a")
    b = cases.create(title="B", module_id=module, feature_slug="b")
    c = cases.create(title="C", module_id=module, feature_slug="c")

    cases.reorder(module, [c, a, b])
    assert _titres(conn, module) == ["C", "A", "B"]

    cases.reorder(module, [b, c, a])
    assert _titres(conn, module) == ["B", "C", "A"]


def test_nouveau_cas_atterrit_en_FIN_de_liste(conn, module):
    cases = CaseRepo(conn)
    cases.create(title="A", module_id=module, feature_slug="a")
    cases.create(title="B", module_id=module, feature_slug="b")
    cases.create(title="C", module_id=module, feature_slug="c")
    # Sans position à la création, tous naîtraient à 0 et s'empileraient en tête.
    assert _titres(conn, module) == ["A", "B", "C"]


def test_ordre_deterministe_malgre_des_ex_aequo(conn, module):
    """Pas de contrainte UNIQUE sur `position` (un glissement décale N voisins) : c'est `id` en
    second critère qui garantit un affichage stable d'un chargement à l'autre."""
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a")
    b = cases.create(title="B", module_id=module, feature_slug="b")
    conn.execute("UPDATE test_case SET position=0 WHERE id IN (?,?)", (a, b))
    conn.commit()
    assert _titres(conn, module) == _titres(conn, module) == ["A", "B"]   # stable, jamais aléatoire


def test_la_priorite_n_ordonne_plus_la_liste(conn, module):
    """Changement VISIBLE assumé : avant 0009 la liste se retriait sur la priorité. La priorité
    redevient une étiquette d'importance — conforme à 0006 qui la dit « étiquette assumée »."""
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a", priority="low")
    cases.create(title="B", module_id=module, feature_slug="b", priority="high")
    cases.set_priority(a, "high")
    assert _titres(conn, module) == ["A", "B"]   # l'ordre manuel tient, la priorité ne le bouscule pas


# ── Validation stricte de la liste ────────────────────────────────────────────

def test_liste_partielle_refusee(conn, module):
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a")
    cases.create(title="B", module_id=module, feature_slug="b")
    # Accepter une liste partielle laisserait B à une position périmée.
    with pytest.raises(ValueError):
        cases.reorder(module, [a])


def test_id_etranger_refuse(conn, module):
    cases = CaseRepo(conn)
    pid = ProjectRepo(conn).get(1)["id"]
    autre = ModuleRepo(conn).create(project_id=pid, name="Autre")
    a = cases.create(title="A", module_id=module, feature_slug="a")
    etranger = cases.create(title="X", module_id=autre, feature_slug="x")
    # Un endpoint qui ne parle que d'ORDRE ne doit pas pouvoir déplacer un cas entre modules.
    with pytest.raises(ValueError):
        cases.reorder(module, [a, etranger])


def test_doublon_dans_la_liste_refuse(conn, module):
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a")
    cases.create(title="B", module_id=module, feature_slug="b")
    with pytest.raises(ValueError):
        cases.reorder(module, [a, a])


def test_reorder_est_transactionnel(conn, module):
    """Une liste invalide ne doit RIEN écrire — pas un ordre à moitié appliqué."""
    cases = CaseRepo(conn)
    a = cases.create(title="A", module_id=module, feature_slug="a")
    b = cases.create(title="B", module_id=module, feature_slug="b")
    avant = _titres(conn, module)
    with pytest.raises(ValueError):
        cases.reorder(module, [b, a, 999])
    assert _titres(conn, module) == avant


# ── Migration 6 ───────────────────────────────────────────────────────────────

def test_migration_6_backfill_par_le_tri_existant(tmp_path):
    """À la migration, rien ne doit bouger à l'écran : le backfill reprend le tri d'avant
    (priorité puis titre). Une position à 0 partout aurait resorti la liste par `id`."""
    db = tmp_path / "m.db"
    conn = get_initialized_db(db)
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cases = CaseRepo(conn)
    cases.create(title="Zebre", module_id=mid, feature_slug="z", priority="high")
    cases.create(title="Alpha", module_id=mid, feature_slug="a", priority="low")
    cases.create(title="Beta", module_id=mid, feature_slug="b", priority="high")

    # Simule une base d'AVANT 0009 : colonne absente, version ramenée à 5.
    conn.execute("ALTER TABLE test_case DROP COLUMN position")
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    conn = get_initialized_db(db)   # réouverture → migration 6
    assert "position" in _column_names(conn, "test_case")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    # Tri d'AVANT : high (Beta, Zebre par titre) puis low (Alpha).
    assert _titres(conn, mid) == ["Beta", "Zebre", "Alpha"]
    conn.close()


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _seed(module_name="M"):
    conn = get_initialized_db(config.DB_PATH)
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name=module_name)
    ids = [CaseRepo(conn).create(title=t, module_id=mid, feature_slug=t.lower())
           for t in ("A", "B", "C")]
    conn.close()
    return mid, ids


def test_api_reorder_renvoie_la_liste_dans_le_nouvel_ordre(client):
    mid, (a, b, c) = _seed()
    resp = client.put(f"/api/modules/{mid}/cases/order", json={"case_ids": [c, a, b]})
    assert resp.status_code == 200
    assert [x["title"] for x in resp.json()] == ["C", "A", "B"]
    # Et l'ordre persiste au rechargement (ce n'est pas qu'une réponse cosmétique).
    assert [x["title"] for x in client.get(f"/api/cases?module_id={mid}").json()["items"]] == ["C", "A", "B"]


def test_api_reorder_409_si_liste_invalide(client):
    mid, (a, b, _) = _seed()
    assert client.put(f"/api/modules/{mid}/cases/order", json={"case_ids": [a, b]}).status_code == 409


def test_api_reorder_404_si_module_inconnu(client):
    assert client.put("/api/modules/999/cases/order", json={"case_ids": []}).status_code == 404


def test_l_ordre_d_affichage_n_atteint_JAMAIS_l_execution(client):
    """Garde de l'invariant central de 0009 : `position` ne sort pas de l'affichage.

    Si un jour l'Exécution nommée transverse veut un ordre, ce sera SA décision — cet ordre ne
    doit pas la piloter par accident.
    """
    import subprocess
    import sys
    # Le champ ne doit être lu ni par le runtime, ni par le verdict, ni par le rapport.
    interdits = ["src/testpilot/execution", "src/testpilot/verdict", "src/testpilot/reporting",
                 "behave_runtime"]
    trouve = subprocess.run(
        [sys.executable, "-c",
         "import pathlib,sys;"
         "hits=[str(p) for d in sys.argv[1:] for p in pathlib.Path(d).rglob('*.py')"
         " if 'position' in p.read_text(encoding='utf-8')];"
         "print('\\n'.join(hits))", *interdits],
        capture_output=True, text=True)
    assert not trouve.stdout.strip(), (
        f"`position` (ordre d'AFFICHAGE) ne doit jamais être lu hors de l'affichage :\n"
        f"{trouve.stdout}")
