"""Lot 05 (D5) — preuve sur de VRAIES instances Odoo Community du banc (16.0, 17.0, 18.0) : un champ dont le libellé change.

Lancer : `scripts/banc_init.sh <version>` puis `pytest -m banc tests/test_confiance_banc.py -v`. Ignoré si le banc ne répond
pas (`BANC_REQUIS=1` le fait échouer). Sur le formulaire d'un devis, on RENOMME le libellé du champ d'échéance côté vue :

- mode normal : la cascade déterministe échoue, la résolution adaptative retrouve le champ → le scénario est `passed` mais sa
  confiance est `auto_resolue` (« Réussi — à confirmer ») ;
- mode strict : la même cascade échoue, AUCUN appel au modèle n'est fait, le test échoue (`retest`) au lieu d'un vert de repli ;
- contrôle (falsifiabilité) : sans renommage, le même scénario reste nominal — sans lui, « auto_resolue » ne prouverait rien.

Seul le CHOIX du modèle est simulé (il désigne l'élément dont le nom accessible contient le nouveau libellé) : la page, ses
éléments interactifs et leur repérage sont ceux d'Odoo réel. Aucun appel LLM, donc aucun coût en CI.
"""

from __future__ import annotations

import json
import os
import sys
import types
import urllib.request
import xmlrpc.client
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _adaptive_resolution  # noqa: E402
import _base_helpers as H  # noqa: E402
from testpilot.execution.behave_result import (  # noqa: E402
    BehaveFailure, BehaveResult, BehaveScenario, read_selector_tiers,
)
from testpilot.execution.executor import ExecutionOutcome  # noqa: E402
from testpilot.verdict import status as st  # noqa: E402

pytestmark = pytest.mark.banc

BANC = os.environ.get("BANC_URL", "http://127.0.0.1:18069")
# Le nouveau libellé est volontairement ARTIFICIEL : sur 16.0 le libellé français natif du champ est « Échéance du devis » —
# un « renommage » vers cette même chaîne ne renommait rien et la cascade retrouvait le champ (CI du 2026-09-25).
BASE, CHAMP, NOUVEAU_LIBELLE = "banc", "validity_date", "Limite TP de validité"
SCENARIO = "Créer un devis"


def _banc_repond() -> bool:
    try:
        urllib.request.urlopen(BANC + "/web/login", timeout=5)
        return True
    except Exception:
        if os.environ.get("BANC_REQUIS") == "1":
            pytest.fail(f"BANC_REQUIS=1 mais le banc ne répond pas sur {BANC}")
        return False


@pytest.fixture(scope="module")
def _navigateur():
    if not _banc_repond():
        pytest.skip(f"le banc ne répond pas sur {BANC} (scripts/banc_init.sh)")
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True)
        yield navigateur
        navigateur.close()


@pytest.fixture
def renommage():
    """Renomme le libellé du champ d'échéance du devis par une vue héritée, et le RESTITUE en sortie de test.

    ⚠️ Pas le champ « Client » : mesuré, la cascade le retrouve encore par son PLACEHOLDER après renommage du libellé — le
    scénario ne forcerait alors pas le repli adaptatif. L'échéance n'a ni placeholder ni `name` que le libellé pourrait égaler."""
    commun = xmlrpc.client.ServerProxy(f"{BANC}/xmlrpc/2/common")
    uid = commun.authenticate(BASE, "admin", "admin", {})
    objet = xmlrpc.client.ServerProxy(f"{BANC}/xmlrpc/2/object")

    def appeler(modele, methode, *args):
        return objet.execute_kw(BASE, uid, "admin", modele, methode, list(args))

    vue = appeler("ir.ui.view", "search", [("model", "=", "sale.order"), ("type", "=", "form"),
                                            ("inherit_id", "=", False)], 0, 1)[0]
    cree = appeler("ir.ui.view", "create", {
        "name": "tp_confiance_champ_renomme", "model": "sale.order", "inherit_id": vue, "mode": "extension",
        "arch": (f'<data><xpath expr="//field[@name=\'{CHAMP}\']" position="attributes">'
                 f'<attribute name="string">{NOUVEAU_LIBELLE}</attribute></xpath></data>')})
    yield
    # ⚠️ Odoo 16.0 n'invalide PAS le cache de la vue combinée à la suppression d'une vue héritée : le libellé renommé restait
    # affiché aux tests suivants (mesuré le 2026-09-25 : la CI 16.0 lisait l'« ancien » libellé déjà renommé). Une ÉCRITURE
    # l'invalide — on neutralise donc l'héritage AVANT de le supprimer.
    appeler("ir.ui.view", "write", [cree], {"arch": "<data/>"})
    appeler("ir.ui.view", "unlink", [cree])


@pytest.fixture
def formulaire(_navigateur, monkeypatch, tmp_path):
    """Un formulaire de devis ouvert dans un navigateur neuf, le sidecar des paliers et le scénario courant posés.

    Rend `(page, sidecar, libellé d'origine du champ)`. ⚠️ Doit être demandée AVANT `renommage` : le libellé d'origine est lu
    avant que la vue héritée ne le change."""
    contexte = _navigateur.new_context(viewport={"width": 1400, "height": 900})
    page = contexte.new_page()
    pilote = types.SimpleNamespace(page=page, odoo_url=BANC, odoo_db=BASE, odoo_user="admin", odoo_password="admin")
    sidecar = tmp_path / "selector_tiers.jsonl"
    monkeypatch.setenv(H.SELECTOR_TIER_FILE_ENV, str(sidecar))
    monkeypatch.delenv(H.MODE_STRICT_ENV, raising=False)
    monkeypatch.delenv("TESTPILOT_QUALIFICATION", raising=False)
    monkeypatch.setitem(H._ETAT_CONSTAT, "scenario", SCENARIO)
    H.navigate_menu(pilote, "Ventes / Commandes / Devis")
    # `:visible` : sur 17.0 le premier `.o_list_button_add` du DOM est celui d'une vue détachée (CI du 2026-09-25).
    page.locator(".o_list_button_add:visible").first.click(timeout=15000)
    page.locator(".o_form_view").first.wait_for(state="visible", timeout=20000)
    # Le libellé d'ORIGINE se lit sur la page (il varie d'une version et d'une langue à l'autre) : c'est l'identifiant que
    # cherche le step, et celui que le renommage rendra introuvable.
    ancien = page.locator(f"label[for^='{CHAMP}']").first.inner_text().strip()
    assert ancien, f"le champ {CHAMP} n'a pas de libellé sur le formulaire de devis de cette version"
    assert ancien != NOUVEAU_LIBELLE, "le libellé natif égale le libellé de renommage : le test ne renommerait rien"
    page._tp_intention_step = f'je saisis "2026-12-31" dans le champ "{ancien}"'
    yield page, sidecar, ancien
    contexte.close()


class _ModeleDeterministe:
    """Le CHOIX du modèle, simulé : désigne l'élément réel dont le nom accessible contient `cible`."""

    def __init__(self, cible):
        self.cible, self.appels = cible.lower(), 0

    def call_json(self, *, system_prompt, user_content, schema, model=None, cost_tracker=None, label=""):
        self.appels += 1
        candidats = json.loads(user_content.split("type) :\n", 1)[1])
        for c in candidats:
            if self.cible in (c.get("nom") or "").lower():
                return {"idx": c["idx"], "menu_parent_probable": False}
        return {"idx": None}


def _brancher_modele(monkeypatch, modele):
    original = _adaptive_resolution.resoudre_champ_adaptatif
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda page, ident, intention, **kw: original(page, ident, intention, llm=modele, **kw))


def _verdict_du_scenario_reussi(sidecar):
    """Le verdict que `derive_verdict` rend d'un scénario VERT dont on a lu le vrai sidecar de paliers."""
    reel = BehaveResult(success=True, returncode=0, passed=1,
                        scenarios=[BehaveScenario(SCENARIO, "passed", constats_reussis=1)],
                        selector_tiers=read_selector_tiers(sidecar))
    return st.derive_verdict(ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=reel))


def _est_le_champ_cible(champ) -> bool:
    return champ.first.evaluate(f"e => !!e.closest('[name=\"{CHAMP}\"]')")


def test_controle_sans_renommage_le_meme_scenario_est_nominal(formulaire, monkeypatch):
    """Falsifiabilité : sans le renommage, la cascade trouve le champ et rien ne qualifie le vert."""
    page, sidecar, ancien = formulaire
    modele = _ModeleDeterministe(NOUVEAU_LIBELLE)
    _brancher_modele(monkeypatch, modele)

    champ = H.locate_field(page, ancien, timeout=5000)

    assert champ.count() > 0 and _est_le_champ_cible(champ)
    assert modele.appels == 0
    verdict = _verdict_du_scenario_reussi(sidecar)
    assert (verdict.confiance, verdict.functional_status) == (st.CONFIANCE_NOMINALE, st.FUNC_CONFORME)


def test_champ_renomme_en_mode_normal_passed_mais_auto_resolue(formulaire, renommage, monkeypatch):
    page, sidecar, ancien = formulaire
    page.reload()
    page.locator(".o_form_view").first.wait_for(state="visible", timeout=20000)
    page._tp_intention_step = f'je saisis "2026-12-31" dans le champ "{ancien}"'
    modele = _ModeleDeterministe(NOUVEAU_LIBELLE)
    _brancher_modele(monkeypatch, modele)

    champ = H.locate_field(page, ancien, timeout=3000)

    assert modele.appels == 1, "la cascade déterministe échoue sur le libellé renommé : le repli adaptatif est tenté"
    assert champ.count() > 0 and _est_le_champ_cible(champ), "le repli retrouve BIEN le champ d'échéance"
    lignes = [ligne for ligne in read_selector_tiers(sidecar) if ligne["tier"] == H.PALIER_ADAPTATIF]
    assert lignes and lignes[0]["scenario"] == SCENARIO
    verdict = _verdict_du_scenario_reussi(sidecar)
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
    assert st.statut_de_test(verdict.execution_status, verdict.functional_status) == st.STATUT_PASSED
    assert verdict.confiance == st.CONFIANCE_AUTO_RESOLUE
    assert st.a_confirmer(st.STATUT_PASSED, verdict.confiance) is True


def test_champ_renomme_en_mode_strict_retest_sans_aucun_appel_au_modele(formulaire, renommage, monkeypatch):
    page, sidecar, ancien = formulaire
    page.reload()
    page.locator(".o_form_view").first.wait_for(state="visible", timeout=20000)
    page._tp_intention_step = f'je saisis "2026-12-31" dans le champ "{ancien}"'
    modele = _ModeleDeterministe(NOUVEAU_LIBELLE)
    _brancher_modele(monkeypatch, modele)
    monkeypatch.setenv(H.MODE_STRICT_ENV, "1")

    with pytest.raises(H.ElementIntrouvableError) as erreur:
        H.fill_field(page, ancien, "2026-12-31")

    assert modele.appels == 0, "en mode strict, AUCUN appel au modèle : coût d'exécution nul"
    assert not [ligne for ligne in read_selector_tiers(sidecar) if ligne["tier"] == H.PALIER_ADAPTATIF]
    echec = BehaveFailure(SCENARIO, "Quand je saisis", "unknown", f"ElementIntrouvableError: {erreur.value}",
                          raw=f"ElementIntrouvableError: {erreur.value}", step_type="when")
    reel = BehaveResult(success=False, returncode=1, failed=1, failures=[echec],
                        scenarios=[BehaveScenario(SCENARIO, "failed", constats_reussis=0)],
                        selector_tiers=read_selector_tiers(sidecar))
    verdict = st.derive_verdict(ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=reel))
    assert st.statut_de_test(verdict.execution_status, verdict.functional_status) == st.STATUT_RETEST
