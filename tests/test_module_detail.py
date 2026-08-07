"""§7 / décision 0006 — page détail module : priorité, dépliage scénarios, ajout par SPEC.

Invariant central vérifié ici : « Ajouter un cas » ne crée JAMAIS de coquille vide. Il
déclenche le flux spec → analyse → génération → gate. Un cas sans version ni Gherkin
afficherait un cas qui ne teste rien (§3) — c'est précisément ce qu'on interdit.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import generation_service
from testpilot.generation.state import GenerationResult
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "mod.db")
    generation_service._JOBS.clear()
    return TestClient(app_mod.app)


def _seed(conn) -> tuple[int, int]:
    # Connexion complète : depuis le 2026-07-24, déclencher une génération sans elle est refusé
    # (on ne saurait pas contre quelle application le test est écrit).
    pid = ProjectRepo(conn).create(name="Portail Sapian", connector_type="odoo",
                                   base_url="http://recette:8069", database="db",
                                   username="qa", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demande matériel")
    return pid, mid


def _conn():
    return get_initialized_db(config.DB_PATH)


# ── Détail du module (fil d'Ariane) ───────────────────────────────────────────
def test_module_detail_expose_le_projet_parent(client):
    conn = _conn(); pid, mid = _seed(conn); conn.close()

    detail = client.get(f"/api/modules/{mid}").json()
    assert detail["module"]["name"] == "Demande matériel"
    assert detail["project"]["name"] == "Portail Sapian"


def test_module_inexistant(client):
    assert client.get("/api/modules/999").status_code == 404


# ── Priorité : étiquette de lecture ───────────────────────────────────────────
def test_priorite_par_defaut_et_mise_a_jour(client):
    conn = _conn(); _, mid = _seed(conn)
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    conn.close()

    assert client.get(f"/api/cases/{cid}").json()["case"]["priority"] == "medium"
    resp = client.patch(f"/api/cases/{cid}", json={"priority": "high"})
    assert resp.status_code == 200
    assert resp.json()["priority"] == "high"


def test_priorite_invalide_refusee(client):
    conn = _conn(); _, mid = _seed(conn)
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    conn.close()
    assert client.patch(f"/api/cases/{cid}", json={"priority": "urgent"}).status_code == 422


def test_tri_par_ordre_manuel_pas_par_priorite(client):
    """⚠️ Contrat CHANGÉ par la décision 0009 (ce test figeait « priorité puis titre »).

    La liste suit désormais l'ORDRE D'AFFICHAGE manuel (glisser-déposer), et la priorité
    redevient une pure étiquette d'importance qui ne bouscule plus l'ordre — conforme à
    0006/§2.4 qui la qualifiait déjà d'« étiquette de lecture assumée ». Les deux coexistent,
    indépendantes. Changement VISIBLE et assumé, pas une régression.
    """
    conn = _conn(); pid, mid = _seed(conn)
    CaseRepo(conn).create(title="Zebre", module_id=mid, feature_slug="z", priority="high")
    CaseRepo(conn).create(title="Alpha", module_id=mid, feature_slug="a", priority="low")
    CaseRepo(conn).create(title="Beta", module_id=mid, feature_slug="b", priority="high")
    conn.close()

    # Ordre par défaut = ordre de création (chaque cas naît en fin de liste), la priorité n'y
    # change rien.
    titles = [c["title"] for c in client.get(f"/api/cases?module_id={mid}").json()["items"]]
    assert titles == ["Zebre", "Alpha", "Beta"]


# ── Dépliage : scénarios du dernier run ───────────────────────────────────────
def test_scenarios_du_dernier_run(client):
    conn = _conn(); _, mid = _seed(conn)
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="", steps_content="")
    execs = ExecutionRepo(conn)
    old = execs.create(test_case_id=cid, version_id=vid)
    execs.add_scenario_result(execution_id=old, scenario_name="ANCIEN",
                              execution_status="success", functional_status="conforme")
    last = execs.create(test_case_id=cid, version_id=vid)
    execs.add_scenario_result(execution_id=last, scenario_name="[NOMINAL] récent",
                              execution_status="technical_error", functional_status="indetermine")
    conn.close()

    scenarios = client.get(f"/api/cases/{cid}/scenarios").json()
    assert [s["scenario_name"] for s in scenarios] == ["[NOMINAL] récent"]  # dernier run seulement
    assert scenarios[0]["execution_status"] == "technical_error"


def test_scenarios_vide_si_jamais_execute(client):
    conn = _conn(); _, mid = _seed(conn)
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    conn.close()
    assert client.get(f"/api/cases/{cid}/scenarios").json() == []


# ── Ajout d'un cas = spec → génération (jamais une coquille) ──────────────────
def test_ajout_sans_spec_est_refuse(client):
    """Sans spécification, pas de cas : on n'ouvre pas la porte à une coquille vide."""
    conn = _conn(); _, mid = _seed(conn); conn.close()
    resp = client.post(f"/api/modules/{mid}/cases", json={"title": "Un cas", "spec_content": ""})
    assert resp.status_code == 422
    conn = _conn()
    assert CaseRepo(conn).list_all(module_id=mid) == []   # rien créé
    conn.close()


def test_ajout_sur_module_inexistant(client):
    assert client.post("/api/modules/999/cases", json={"spec_content": "spec"}).status_code == 404


def test_ajout_declenche_la_generation_dans_le_bon_module(client, monkeypatch):
    """La spec enchaîne sur la génération, et le cas atterrit DANS le module demandé.

    `run_generation` (passe 4a, découpage + métier) est simulé directement en `done` : ce test
    porte sur le DÉCLENCHEMENT et le ROUTAGE au bon module, pas sur la mécanique de pause en deux
    passes (couverte par `test_generation_deux_passes.py`)."""
    conn = _conn(); pid, mid = _seed(conn); conn.close()
    captured = {}

    def fake_run(job_id, *, module_id, title, spec_content, author, group_id=None):
        # Simule la génération : crée le cas AVEC sa version (comme le vrai agent le ferait,
        # une fois la pause métier franchie).
        slug = generation_service.slugify(title)
        captured.update(module_id=module_id, slug=slug, title=title, spec=spec_content)
        c = _conn()
        cid = CaseRepo(c).create(title=title, module_id=module_id, feature_slug=slug)
        VersionRepo(c).create(test_case_id=cid, spec_content=spec_content, spec_hash="h",
                              feature_content="# language: fr", steps_content="")
        c.close()
        generation_service._JOBS[job_id].update(status="done", case_ids=[cid])

    monkeypatch.setattr(generation_service, "run_generation", fake_run)

    resp = client.post(f"/api/modules/{mid}/cases",
                       json={"spec_content": "# Spec\nLe portail...", "title": "Retour matériel"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    assert captured["module_id"] == mid          # module imposé, pas le projet par défaut
    assert captured["slug"] == "retour_materiel"  # slug dérivé du titre
    assert "Le portail" in captured["spec"]

    job = client.get(f"/api/modules/jobs/{job_id}").json()
    assert job["status"] == "done"
    cases = client.get(f"/api/cases?module_id={mid}").json()["items"]
    assert [c["title"] for c in cases] == ["Retour matériel"]
    assert job["case_ids"] == [c["id"] for c in cases]


def test_job_inconnu(client):
    assert client.get("/api/modules/jobs/inexistant").status_code == 404


# ── Unicité du slug (un slug = un fichier .feature sur disque) ────────────────
def test_slug_unique_entre_deux_cas_du_meme_module(client):
    conn = _conn(); _, mid = _seed(conn)
    CaseRepo(conn).create(title="Retour matériel", module_id=mid, feature_slug="retour_materiel")
    slug = generation_service.unique_feature_slug(conn, "retour_materiel")
    conn.close()
    assert slug == "retour_materiel_2"   # sinon les .feature s'écraseraient


def test_slugify_normalise_accents_et_espaces():
    assert generation_service.slugify("Retour matériel VIP !") == "retour_materiel_vip"


# ── Longueur bornée (2026-08-05) ──────────────────────────────────────────────
# Un slug apparaît DEUX FOIS dans le chemin d'exécution Behave (dossier temporaire ET fichier
# `_steps.py` à l'intérieur) : un titre-phrase généré par l'IA, non borné, dépassait la limite
# de chemin Windows — `[Errno 2] No such file or directory` sans rapport apparent avec la cause.

_TITRE_LONG = ("Le formulaire de mutation payeur refuse les codes payeur contenant des lettres "
              "ou caractères spéciaux")


def test_slugify_BORNE_un_titre_long():
    slug = generation_service.slugify(_TITRE_LONG)
    assert len(slug) <= generation_service._SLUG_MAX + 7  # + "_" + hash 6 hex


def test_slugify_reste_COURT_pour_un_titre_court():
    """Un titre déjà court ne doit RIEN gagner en tronquant : le slug doit rester lisible, pas
    systématiquement alourdi d'un hachage qui ne sert à rien en dessous de la limite."""
    assert generation_service.slugify("Retour matériel VIP !") == "retour_materiel_vip"


def test_slugify_DISTINGUE_deux_titres_au_meme_prefixe_long():
    """Deux cas dont le titre ne diffère que par la fin (fréquent : l'IA varie la fin d'un
    titre, pas son début) ne doivent PAS produire le même slug une fois tronqués — sinon
    `unique_feature_slug` ne les distinguerait que par un suffixe numérique arbitraire, qui ne
    dit rien de la différence réelle entre les deux cas."""
    a = generation_service.slugify(_TITRE_LONG + " (variante A)")
    b = generation_service.slugify(_TITRE_LONG + " (variante B)")
    assert a != b


def test_slugify_deux_appels_sur_le_MEME_titre_donnent_le_MEME_slug():
    """Le hachage doit être STABLE : `unique_feature_slug` en dépend pour reconnaître un cas
    déjà nommé, pas pour en fabriquer un nouveau à chaque appel."""
    assert generation_service.slugify(_TITRE_LONG) == generation_service.slugify(_TITRE_LONG)
