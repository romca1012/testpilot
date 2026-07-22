"""Le §9 se mesure sur le chemin que les utilisateurs empruntent — pas seulement en CLI.

LE TROU. `CostRepo.add_entry` n'était appelé que par `cli.py` (génération) et `repair_service`
(réparation). **Un cas créé par l'écran ne laissait AUCUNE trace de son coût de génération** —
le poste le plus lourd (42 % du budget cible sur le cas 1). La seule ligne `generation` du ledger
venait d'un run CLI, et on prétendait juger le §9 dessus. On ne peut pas tenir un budget qu'on ne
mesure pas là où il se dépense.

DEUX DÉFAUTS DISTINCTS, trouvés en branchant :

1. **Structurel** : `cost_ledger` ne reliait un coût à un cas qu'à travers `execution`
   (`total_for_case_usd` faisait `JOIN execution`). Or **une génération n'a pas d'exécution** —
   elle la précède, et le cas peut n'être jamais exécuté. Le coût n'avait nulle part où
   s'accrocher. La CLI masquait le défaut : elle génère et exécute dans le même pipeline.
   → migration 12 : `test_case_id` devient le lien de référence.

2. **L'analyse ne coûtait rien à personne** : `SpecAnalyzer()` était construit **sans**
   `cost_tracker` sur les DEUX chemins, donc `plan.cost_usd` valait toujours `0.0`. Un appel LLM
   invisible depuis toujours — alors que le schéma prévoyait la phase `analysis` dès l'origine.
"""

import pytest

from testpilot import config
from testpilot.api.services import generation_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, CostRepo, ExecutionRepo, VersionRepo


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "cout.db")
    yield c
    c.close()


def _cas_avec_run(conn):
    """Un cas + sa version + une exécution — `execution.version_id` est NOT NULL."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="f", steps_content="st")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


# ── Le lien de référence : le CAS, pas l'exécution ────────────────────────────

def test_un_cout_de_generation_sans_execution_compte_quand_meme(conn):
    """LE test structurel : une génération n'a pas d'exécution, son coût doit compter.

    Échoue avant la migration 12 : `total_for_case_usd` faisait `JOIN execution`, donc une
    ligne sans `execution_id` était **invisible** — le coût de génération du chemin API
    disparaissait intégralement du §9.
    """
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    CostRepo(conn).add_entry(phase="generation", model=config.MODEL_GENERATION,
                             cost_usd=0.45, source="estimated", test_case_id=cid)

    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.45), (
        "le coût d'une génération sans exécution est perdu : le §9 est aveugle sur le chemin API")


def test_le_cas_est_retrouve_depuis_l_execution_quand_seul_le_run_est_connu(conn):
    """Un appelant qui ne connaît que son run reste correct — `repair_service` est dans ce cas."""
    cid, _vid, eid = _cas_avec_run(conn)

    CostRepo(conn).add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=0.29,
                             source="estimated", execution_id=eid)

    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.29)


def test_le_9_se_mesure_sur_la_CREATION_pas_sur_le_cumul(conn):
    """🔴 L'arbitrage du porteur (2026-07-17), gardé par un test.

    Le §9 dit « **nouveau** cas de test (génération + exécution + rapport) < 1 € » : il mesure une
    **CRÉATION**, une fois. `total_for_case_usd` répond à « combien depuis toujours », réparations
    et sessions de débogage comprises — **jamais comparable à ce seuil**.

    Les confondre a produit une **alarme fausse** : le cas 1 affichait « 107 % du §9 [DEPASSE] »
    alors que sa création vaut 11 % du §9 et que le reste est du débogage de l'outil.

    On reproduit exactement cette forme : une création bon marché, un long débogage derrière.
    """
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    repo = CostRepo(conn)
    repo.add_entry(phase="analysis", model=config.MODEL_FAST, cost_usd=0.0157,
                   source="estimated", test_case_id=cid)
    repo.add_entry(phase="generation", model=config.MODEL_GENERATION, cost_usd=0.1050,
                   source="estimated", test_case_id=cid)
    for cout in (0.2895, 0.3088, 0.1041, 0.45):        # cinq sessions de débogage
        repo.add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=cout,
                       source="estimated", test_case_id=cid)

    creation = repo.creation_cost_usd(cid)
    total = repo.total_for_case_usd(cid)

    assert creation == pytest.approx(0.1207), "la création = analyse + génération, rien d'autre"
    assert creation < config.BUDGET_PER_CASE_USD, "le §9 est tenu — c'est CE chiffre qui le juge"
    assert total > config.BUDGET_PER_CASE_USD, (
        "mise en scène : le cumul DOIT dépasser le seuil, c'est ce qui rend l'alarme fausse "
        "crédible")
    assert total > creation, "le cumul inclut le débogage ; la création non"


def test_une_reparation_n_entre_jamais_dans_le_cout_de_creation(conn):
    """La frontière, en une assertion : `repair` est du coût d'exploitation, pas de création."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    CostRepo(conn).add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=0.29,
                             source="estimated", test_case_id=cid)

    assert CostRepo(conn).creation_cost_usd(cid) == 0.0
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.29)


def test_le_cout_de_RUN_est_suivi_distinct_de_la_creation(conn):
    """Le coût de RUN (réparations) est suivi séparément — SANS seuil (arbitrage 2026-07-19 :
    mesurer d'abord, calibrer plus tard). Distinct de la création (le §9) et du total."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    repo = CostRepo(conn)
    repo.add_entry(phase="analysis", model=config.MODEL_FAST, cost_usd=0.02,
                   source="estimated", test_case_id=cid)
    repo.add_entry(phase="generation", model=config.MODEL_GENERATION, cost_usd=0.13,
                   source="estimated", test_case_id=cid)
    repo.add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=0.21,
                   source="estimated", test_case_id=cid)
    repo.add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=0.19,
                   source="estimated", test_case_id=cid)

    assert repo.run_cost_usd(cid) == pytest.approx(0.40), "run = somme des réparations, rien d'autre"
    assert repo.creation_cost_usd(cid) == pytest.approx(0.15), "la création exclut le run"
    # création + run == total : aucune dépense n'échappe à l'une des deux catégories.
    assert repo.run_cost_usd(cid) + repo.creation_cost_usd(cid) == pytest.approx(
        repo.total_for_case_usd(cid))


def test_un_run_PROPRE_coute_zero(conn):
    """Un cas jamais réparé a un coût de run de $0 — un fait, pas un trou : le run lui-même
    (Behave/Playwright/odoorpc) et le diagnostic déterministe n'appellent aucun LLM."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    CostRepo(conn).add_entry(phase="generation", model=config.MODEL_GENERATION, cost_usd=0.13,
                             source="estimated", test_case_id=cid)

    assert CostRepo(conn).run_cost_usd(cid) == 0.0


def test_le_cout_run_est_lisible_par_execution(conn):
    """Le coût run par run (pas seulement cumulé par cas) — pour la future calibration."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="", steps_content="")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    CostRepo(conn).add_entry(phase="repair", model=config.MODEL_REPAIR, cost_usd=0.21,
                             source="estimated", execution_id=eid)

    assert CostRepo(conn).run_cost_for_execution_usd(eid) == pytest.approx(0.21)
    assert CostRepo(conn).run_cost_for_execution_usd(9999) == 0.0  # exécution sans coût


def test_le_detail_par_phase_explique_le_total(conn):
    """Le ledger doit dire CE QUI a coûté, pas seulement combien — analyse ≠ génération."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    repo = CostRepo(conn)
    repo.add_entry(phase="analysis", model=config.MODEL_FAST, cost_usd=0.01,
                   source="estimated", test_case_id=cid)
    repo.add_entry(phase="generation", model=config.MODEL_GENERATION, cost_usd=0.45,
                   source="estimated", test_case_id=cid)

    phases = {r["phase"]: r["cost_usd"] for r in repo.breakdown_for_case(cid)}
    assert phases == {"analysis": pytest.approx(0.01), "generation": pytest.approx(0.45)}
    assert repo.total_for_case_usd(cid) == pytest.approx(0.46)


# ── Le branchement du chemin écran ────────────────────────────────────────────

def test_la_generation_par_l_ecran_ecrit_analyse_ET_generation_au_ledger(conn):
    """LE test du trou : `_record_generation_cost` écrit les deux phases, rattachées au CAS.

    Échoue sur le code d'avant : `run_generation` n'appelait **jamais** `CostRepo.add_entry`.
    """
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")

    generation_service._record_generation_cost(
        conn, case_id=cid, analysis_usd=0.0123, generation_usd=0.4529)

    lignes = {r["phase"]: r for r in CostRepo(conn).breakdown_for_case(cid)}
    assert set(lignes) == {"analysis", "generation"}, (
        "le chemin écran ne trace pas son coût : le §9 y est inmesurable")
    assert lignes["analysis"]["model"] == config.MODEL_FAST
    assert lignes["generation"]["model"] == config.MODEL_GENERATION
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.4652)


def test_une_depense_sans_cas_cree_est_INSCRITE_mais_imputee_a_personne(conn, caplog):
    """Un échec de génération a coûté. Sans cas, on le DIT — et on n'invente pas de rattachement.

    ⚠️ **Attente RÉVISÉE le 2026-07-22.** Ce test exigeait `COUNT(*) == 0` : ne rien écrire du
    tout. L'intention était bonne — ne pas imputer la dépense à un cas au hasard — mais la
    conséquence ne l'était pas : mesuré sur le banc, `sinistre_client` a brûlé 0,14 $ **invisibles
    au budget §9**, et une génération qui cale en boucle pourrait en brûler beaucoup sans qu'aucun
    compteur ne bouge.

    *Ne pas imputer à un cas* et *ne rien inscrire* sont deux choses différentes. `test_case_id`
    est nullable et le total mensuel somme la période sans filtrer sur le cas : la ligne compte au
    budget **sans polluer aucun coût par cas**. L'invariant que ce test gardait vraiment — aucun
    rattachement inventé — est ci-dessous, et il tient toujours.
    """
    cid = CaseRepo(conn).create(title="Un autre cas", feature_slug="autre")

    generation_service._record_generation_cost(
        conn, case_id=None, analysis_usd=0.01, generation_usd=0.20)

    assert CostRepo(conn).monthly_total_usd() == pytest.approx(0.21), "comptée au budget §9"
    assert CostRepo(conn).total_for_case_usd(cid) == 0.0, "imputée à AUCUN cas"
    assert conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE test_case_id IS NULL").fetchone()[0] == 2
    assert "SANS cas créé" in caplog.text


def test_un_cout_nul_n_ecrit_aucune_ligne(conn):
    """Pas de ligne à $0 : le ledger porte des dépenses, pas du bruit."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")

    generation_service._record_generation_cost(
        conn, case_id=cid, analysis_usd=0.0, generation_usd=0.0)

    assert conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0] == 0


# ── L'analyse est enfin comptée ───────────────────────────────────────────────

def test_le_spec_analyzer_recoit_un_tracker_sur_les_deux_chemins():
    """`plan.cost_usd` valait TOUJOURS 0.0 : l'analyse était gratuite sur le papier.

    On garde le câblage plutôt que le résultat : un `SpecAnalyzer` sans tracker ne peut
    structurellement rien mesurer, quel que soit le prompt.
    """
    from testpilot.analysis.spec_analyzer import SpecAnalyzer

    assert SpecAnalyzer().cost_tracker is None, (
        "le défaut du constructeur a changé — ce test garde le CÂBLAGE des appelants")

    import inspect

    from testpilot import cli
    source_cli = inspect.getsource(cli.build_default_deps)
    assert "SpecAnalyzer(cost_tracker=" in source_cli, (
        "la CLI construit un SpecAnalyzer sans tracker : le coût d'analyse retombe à 0")

    source_api = inspect.getsource(generation_service.run_generation)
    assert "SpecAnalyzer(cost_tracker=" in source_api, (
        "le chemin écran construit un SpecAnalyzer sans tracker : le coût d'analyse retombe à 0")

    # ⚠️ La génération en DEUX PASSES (`0022` n°5) a déplacé l'écriture du coût : `run_generation`
    # s'arrête à la pause métier, c'est `resume_generation` qui persiste le cas — donc le seul
    # moment où un `test_case_id` existe pour porter la dépense. Cette garde a failli être perdue
    # au découpage : elle ne surveillait qu'une des deux fonctions, et serait restée verte
    # pendant que la seconde ne comptait plus rien.
    source_resume = inspect.getsource(generation_service.resume_generation)
    assert "SpecAnalyzer(cost_tracker=" in source_resume, (
        "la passe Gherkin construit un SpecAnalyzer sans tracker : le coût d'analyse retombe à 0")
    assert "_record_generation_cost(" in source_resume, (
        "la passe Gherkin n'écrit plus au ledger : le coût de création devient invisible (§9)")


# ── La migration 12 ───────────────────────────────────────────────────────────

def test_migration_12_rattache_les_lignes_existantes_sans_rien_perdre(tmp_path):
    """La reprise inscrit ce que le JOIN déduisait : aucun total ne bouge, rien n'est perdu."""
    from testpilot.store import db as db_mod

    path = tmp_path / "ancienne.db"
    conn = db_mod.get_initialized_db(path)
    cid, _vid, eid = _cas_avec_run(conn)
    CostRepo(conn).add_entry(phase="generation", model="m", cost_usd=0.45,
                             source="estimated", execution_id=eid)
    # Simule l'état d'AVANT la migration : la ligne ne connaît que son run.
    conn.execute("UPDATE cost_ledger SET test_case_id = NULL")
    conn.execute("PRAGMA user_version = 11")
    conn.commit()
    assert CostRepo(conn).total_for_case_usd(cid) == 0.0, "mise en scène : le lien est bien coupé"
    conn.close()

    # Réouverture → la migration 12 tourne.
    conn = db_mod.get_initialized_db(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 12
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.45), (
        "la reprise a perdu une ligne : le total d'un cas a bougé")
    conn.close()


def test_migration_12_est_idempotente(tmp_path):
    """Deux ouvertures de suite ne dupliquent ni ne détruisent rien."""
    from testpilot.store import db as db_mod

    path = tmp_path / "deux.db"
    for _ in range(2):
        c = db_mod.get_initialized_db(path)
        c.close()
    c = db_mod.get_initialized_db(path)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(cost_ledger)")}
    assert "test_case_id" in cols
    c.close()


def test_une_base_SANS_la_colonne_s_ouvre_toujours(tmp_path):
    """⚠️ Le bug réellement commis le 2026-07-17 — attrapé par la VRAIE base, pas par les tests.

    J'avais mis `CREATE INDEX idx_cost_case ON cost_ledger(test_case_id)` dans `schema.sql`.
    Or **`schema.sql` s'exécute AVANT les migrations** : sur une base antérieure, la colonne
    n'existe pas encore → `sqlite3.OperationalError: no such column: test_case_id` → **toute
    ouverture de la base plante**, application comprise.

    Aucun des 416 tests ne l'a vu : ils partent tous d'un schéma **neuf**, où `CREATE TABLE` crée
    déjà la colonne. Le défaut n'existe que sur une base **existante** — exactement le cas de tous
    les utilisateurs. Le codebase documentait pourtant déjà la leçon (index d'unicité,
    `idx_case_module`) : je l'ai rejouée.

    Ce test reconstruit une `cost_ledger` d'AVANT la colonne et exige que l'ouverture tienne.
    """
    import sqlite3

    from testpilot.store import db as db_mod

    path = tmp_path / "antérieure.db"
    raw = sqlite3.connect(str(path))
    # La table telle qu'elle existait avant la migration 12 : sans `test_case_id`.
    raw.executescript("""
        CREATE TABLE cost_ledger (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            period_month TEXT    NOT NULL,
            execution_id INTEGER,
            phase        TEXT    NOT NULL DEFAULT '',
            model        TEXT    NOT NULL DEFAULT '',
            cost_usd     REAL    NOT NULL DEFAULT 0,
            source       TEXT    NOT NULL DEFAULT 'estimated',
            created_at   TEXT    NOT NULL
        );
        PRAGMA user_version = 11;
    """)
    raw.commit()
    raw.close()

    # Ne doit PAS lever. C'est tout l'objet du test.
    conn = db_mod.get_initialized_db(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(cost_ledger)")}
    assert "test_case_id" in cols, "la migration n'a pas ajouté la colonne"
    conn.close()
