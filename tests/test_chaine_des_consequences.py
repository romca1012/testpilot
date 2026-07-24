"""LA CHAÎNE DES CONSÉQUENCES — une action va jusqu'au bout, ou elle ment (audit 2026-07-24).

**Ce que ce fichier garantit.** Chaque action qui touche un conteneur emporte ce qu'il contient —
*jusqu'au dernier maillon*. Supprimer un projet doit emporter ses modules, donc leurs
spécifications, donc leurs cas, donc leurs exécutions, leurs coûts et leurs campagnes. Une chaîne
qui s'arrête au milieu laisse des orphelins **visibles** : un cas sans module dans une liste, une
campagne qui compte des cas que plus personne ne voit, un coût rattaché à rien.

**Pourquoi un fichier à part.** Ces conséquences sont dispersées dans le code — une partie dans
les dépôts, une partie dans la visibilité hiérarchique, une partie dans la sélection des
campagnes. Personne ne peut les tenir en tête. Ici, elles sont énumérées **au même endroit**, ce
qui rend visible le maillon qu'on aurait oublié.

⚠️ **Deux mécanismes différents, et il faut les distinguer** (c'est la source des erreurs) :

- **MASQUER** (`delete`) : rien n'est détruit, la visibilité est *hiérarchique* — un cas dont le
  module est à la corbeille disparaît sans être marqué lui-même. C'est ce que fait l'utilisateur.
- **DÉTRUIRE** (`purger`) : la cascade réelle, dans l'ordre des clés étrangères. Geste distinct,
  irréversible, réservé à ce qui est déjà à la corbeille.
"""

import json

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    RunRepo,
    VersionRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "chaine.db")
    yield c
    c.close()


def _monde(conn) -> dict:
    """Un projet COMPLET : tous les maillons de la chaîne, peuplés.

    C'est le point de départ de chaque test : si un maillon manquait ici, les tests passeraient
    en ne prouvant rien sur lui.
    """
    pid = ProjectRepo(conn).create(name="Recette", connector_type="odoo", base_url="http://x",
                                   database="db", username="qa", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Déclaration", spec_content="# doc")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="Un cas",
                                       test_steps=json.dumps(["a"]), expected_result="ok")
    conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    vid = CaseRepo(conn).get(cid)["current_version_id"]
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    ExecutionRepo(conn).finalize(eid, execution_status="success", functional_status="conforme",
                                 scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
                                 cost_usd=0.0, iterations=0, duration_seconds=1.0)
    ExecutionRepo(conn).add_scenario_result(execution_id=eid, scenario_name="s",
                                            execution_status="success",
                                            functional_status="conforme")
    CostRepo(conn).add_entry(phase="generation", model="claude", cost_usd=0.10,
                             source="estimated", test_case_id=cid)
    rid = RunRepo(conn).create(project_id=pid, name="Campagne", description="", refs="",
                               selection_mode="frozen", case_ids=[cid])
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    conn.commit()
    return {"pid": pid, "mid": mid, "gid": gid, "cid": cid, "vid": vid, "eid": eid, "rid": rid}


def _visible(conn, m: dict) -> dict:
    """Ce qui reste VISIBLE, maillon par maillon. Un booléen par surface d'affichage."""
    return {
        "projet": ProjectRepo(conn).get(m["pid"]) is not None,
        "module": ModuleRepo(conn).get(m["mid"]) is not None,
        "specification": CaseGroupRepo(conn).get(m["gid"]) is not None,
        "cas": CaseRepo(conn).get(m["cid"]) is not None,
        "cas_dans_liste": bool(CaseRepo(conn).list_all(project_id=m["pid"])),
        "cas_dans_campagne": bool(RunRepo(conn).case_ids(m["rid"])),
    }


# ── 1. Supprimer un PROJET emporte tout, à l'affichage ───────────────────────

def test_supprimer_un_projet_emporte_TOUTE_sa_descendance(conn):
    """L'exemple qui a motivé cet audit : supprimer un projet doit emporter ses modules, donc
    les cas de ces modules — et tout ce qui pend à ces cas."""
    m = _monde(conn)
    assert all(_visible(conn, m).values()), "le monde de départ doit être complet"

    ProjectRepo(conn).delete(m["pid"], par="Awa")

    assert _visible(conn, m) == {
        "projet": False, "module": False, "specification": False, "cas": False,
        "cas_dans_liste": False,
        # ⚠️ Le maillon qu'on oublie : une campagne qui référence encore un cas supprimé le
        # LANCERAIT contre la vraie application. C'est ce que ce test empêche de revenir.
        "cas_dans_campagne": False,
    }


def test_supprimer_un_MODULE_emporte_ses_specifications_et_ses_cas(conn):
    m = _monde(conn)
    ModuleRepo(conn).delete(m["mid"], par="Awa")

    etat = _visible(conn, m)
    assert etat["projet"] is True          # le parent survit, évidemment
    assert etat["module"] is False
    assert etat["specification"] is False
    assert etat["cas"] is False
    assert etat["cas_dans_liste"] is False
    assert etat["cas_dans_campagne"] is False


def test_supprimer_un_CAS_ne_remonte_PAS_la_chaine(conn):
    """La chaîne descend, elle ne remonte jamais : supprimer un cas ne doit pas emporter son
    module ni son projet. Une conséquence qui remonte détruirait plus que ce qui a été demandé."""
    m = _monde(conn)
    CaseRepo(conn).delete(m["cid"], par="Awa")

    etat = _visible(conn, m)
    assert etat["projet"] is True and etat["module"] is True
    assert etat["cas"] is False and etat["cas_dans_campagne"] is False
    # La spécification survit : elle porte un DOCUMENT, c'est un actif indépendant de ses cas.
    assert etat["specification"] is True


# ── 2. Ce qui NE doit pas être détruit ───────────────────────────────────────

def test_supprimer_ne_DETRUIT_aucune_ligne_de_la_chaine(conn):
    """§7 : « nettoyer » signifie archiver. Rien ne quitte la base tant qu'on n'a pas purgé."""
    m = _monde(conn)
    avant = {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
             for t in ("project", "module", "case_group", "test_case", "test_case_version",
                       "execution", "scenario_result", "cost_ledger", "test_run",
                       "test_run_case")}

    ProjectRepo(conn).delete(m["pid"], par="Awa")

    apres = {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in avant}
    assert apres == avant, "une suppression ne doit détruire AUCUNE ligne"


# ── 3. La purge, elle, va au bout — et ne laisse pas d'orphelin ──────────────

def test_purger_un_projet_ne_laisse_AUCUN_orphelin(conn):
    """L'inverse du test précédent : quand on détruit vraiment, il ne doit rien rester derrière.

    ⚠️ Les lignes de coût et de résultat sont les plus faciles à oublier : elles ne référencent
    pas le projet, mais un cas ou une exécution. Une cascade incomplète les laisse orphelines,
    et elles faussent alors le suivi du §9 sans que rien ne le signale (défaut réel, migration 12).
    """
    m = _monde(conn)
    ProjectRepo(conn).delete(m["pid"], par="Awa")

    ProjectRepo(conn).purger(m["pid"])

    restes = {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
              for t in ("project", "module", "case_group", "test_case", "test_case_version",
                        "execution", "scenario_result", "cost_ledger", "review_decision",
                        "repair_attempt", "test_run_case")}
    assert restes == {t: 0 for t in restes}, f"orphelins après purge : {restes}"


# ── 4. Restaurer rend la chaîne entière ─────────────────────────────────────

def test_restaurer_un_projet_rend_TOUTE_sa_descendance(conn):
    """Sinon la corbeille ne serait qu'une destruction différée : on récupérerait un projet vide."""
    m = _monde(conn)
    ProjectRepo(conn).delete(m["pid"], par="Awa")

    ProjectRepo(conn).restaurer(m["pid"])

    assert all(_visible(conn, m).values()), "la restauration doit tout rendre, pas seulement le projet"


# ── 5. Les conséquences d'une ARCHIVE de campagne ───────────────────────────

def test_archiver_une_campagne_ne_touche_A_RIEN_d_autre(conn):
    """Clore une campagne la met en lecture seule. Ce n'est pas une suppression : ses cas, ses
    exécutions et ses résultats restent pleinement visibles ailleurs dans le référentiel."""
    m = _monde(conn)
    RunRepo(conn).archive(m["rid"], True)

    assert all(_visible(conn, m).values())
    assert RunRepo(conn).get(m["rid"])["is_archived"] == 1
