"""Une génération RATÉE coûte de l'argent — et cet argent doit se voir (2026-07-22).

⚠️ **Le trou, mesuré sur le banc.** `sinistre_client` a calé au dry-run : aucun cas créé, **0,14 $
dépensés**, et le journal l'annonçait lui-même — *« hors ledger… Le budget §9 ignore cette
dépense »*. Une génération qui cale en boucle pourrait en brûler beaucoup **sans qu'aucun compteur
ne bouge** : précisément le risque que le §9 est censé borner.

⚠️ **Le piège du raisonnement d'origine**, qui vaut d'être retenu : le code refusait d'écrire pour
ne pas **imputer** la dépense à un cas au hasard. C'était juste. Mais *ne pas imputer à un cas* et
*ne rien inscrire du tout* sont deux choses différentes — on avait pris la seconde en croyant
prendre la première. `test_case_id` est nullable, et le total mensuel somme la période **sans
filtrer sur le cas** : une ligne orpheline compte au budget sans polluer aucun coût par cas.
"""

import pytest

from testpilot import config
from testpilot.api.services.generation_service import _record_generation_cost
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CostRepo, ModuleRepo, ProjectRepo, CaseRepo


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def case_id(conn):
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://x",
                                   database="d", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    return CaseRepo(conn).create_manual(module_id=mid, title="Un cas")


def _total_mois(conn) -> float:
    return CostRepo(conn).monthly_total_usd()


# ── Le cas qui manquait ──────────────────────────────────────────────────────

def test_une_generation_SANS_cas_est_quand_meme_inscrite(conn):
    """⚠️ LE test : la situation exacte de `sinistre_client` sur le banc du 2026-07-22."""
    _record_generation_cost(conn, case_id=None, analysis_usd=0.0133, generation_usd=0.13)

    assert _total_mois(conn) == pytest.approx(0.1433)


def test_la_depense_orpheline_n_est_imputee_A_AUCUN_cas(conn, case_id):
    """La prudence d'origine est PRÉSERVÉE : elle compte au budget, elle ne salit aucun cas."""
    _record_generation_cost(conn, case_id=None, analysis_usd=0.0133, generation_usd=0.13)

    assert CostRepo(conn).total_for_case_usd(case_id) == 0.0
    assert CostRepo(conn).creation_cost_usd(case_id) == 0.0
    orphelines = conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE test_case_id IS NULL").fetchone()[0]
    assert orphelines == 2, "une ligne par phase, sans propriétaire"


def test_les_deux_phases_gardent_leur_modele_meme_sans_cas(conn):
    """Fusionner les phases attribuerait la dépense au mauvais tarif et rendrait le total
    inexplicable — vrai avec un cas, vrai sans."""
    _record_generation_cost(conn, case_id=None, analysis_usd=0.01, generation_usd=0.13)

    lignes = {r["phase"]: r["model"] for r in conn.execute(
        "SELECT phase, model FROM cost_ledger WHERE test_case_id IS NULL")}

    assert lignes == {"analysis": config.MODEL_FAST, "generation": config.MODEL_GENERATION}


def test_une_generation_ratee_SANS_depense_n_ecrit_rien(conn):
    """Un échec avant tout appel LLM ne doit pas créer de lignes à zéro : le ledger doit rester
    lisible, une ligne = une dépense réelle."""
    _record_generation_cost(conn, case_id=None, analysis_usd=0.0, generation_usd=0.0)

    assert conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0] == 0


# ── Non-régression : le chemin nominal est intact ────────────────────────────

def test_une_generation_REUSSIE_reste_imputee_a_son_cas(conn, case_id):
    _record_generation_cost(conn, case_id=case_id, analysis_usd=0.01, generation_usd=0.10)

    assert CostRepo(conn).creation_cost_usd(case_id) == pytest.approx(0.11)
    assert _total_mois(conn) == pytest.approx(0.11)


def test_le_budget_mensuel_ADDITIONNE_ratees_et_reussies(conn, case_id):
    """Le chiffre qui compte pour le §9 : ce qu'on a réellement dépensé dans le mois, quel qu'en
    soit le sort. C'est tout l'objet du correctif."""
    _record_generation_cost(conn, case_id=case_id, analysis_usd=0.01, generation_usd=0.10)
    _record_generation_cost(conn, case_id=None, analysis_usd=0.0133, generation_usd=0.13)

    assert _total_mois(conn) == pytest.approx(0.2533)
