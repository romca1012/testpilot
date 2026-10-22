"""Étape 5 du plan unique (AV-9) — sur une application web, les outils de données disent à l'IA ce qu'elle PEUT relever
(interrupteur `TESTPILOT_IA_INFORMEE`, éteint).

Avant : « [erreur tool query_data : … (inspect_form/discover_route + steps génériques)] » — une erreur technique qui nommait
des outils inexistants ; l'IA supposait ou s'arrêtait (registre AV-9). Gardé ici : éteint, la réponse d'avant ; allumé, les
moyens réels du projet (pages, essai s'il existe, NOMS des requêtes d'oracle), jamais une réponse de l'oracle.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testpilot.generation import interrupteurs
from testpilot.generation.tools import ToolContext, dispatch, essai as essai_tools


class _ConnecteurWeb:
    def get_schema(self, model):
        raise NotImplementedError("Ce connecteur n'a pas de modèle de données (inspect_form/discover_route)")

    def search(self, model, filters, limit=0):
        raise NotImplementedError("Ce connecteur n'a pas de modèle de données (inspect_form/discover_route)")

    def attempt_form_submission(self, page_url, field_values, model=""):
        raise NotImplementedError("réservée à un connecteur qui expose create/delete")


def _ctx(tmp_path, **kw):
    return ToolContext(module_name="m", generated_dir=tmp_path, connector=_ConnecteurWeb(), **kw)


@pytest.mark.parametrize("outil, entree", [("inspect_schema", {"model": "client"}), ("query_data", {"model": "client"}),
                                           ("attempt_form_submission", {"page_url": "/x", "field_values": {}})])
def test_falsifiable_eteint_l_erreur_d_avant_allume_les_moyens_du_projet(tmp_path, outil, entree):
    avant = dispatch(outil, entree, _ctx(tmp_path))
    # Avant : une erreur technique, ou (soumission) « active-la dans ses réglages » — faux sur le web, même activée.
    assert not avant.ok and "indisponible sur une application web" not in avant.observation

    apres = dispatch(outil, entree, _ctx(tmp_path, outils_web_informes=True,
                                         requetes_oracle_declarees=frozenset({"etat_panier", "commandes"})))
    assert not apres.ok
    assert apres.observation.startswith(f"[{outil}] indisponible sur une application web")
    assert "`inspect_page_snapshot`" in apres.observation and "requêtes déclarées : « commandes », « etat_panier »" in apres.observation
    assert essai_tools.NOM_OUTIL not in apres.observation, "pas de bac à sable : l'essai n'est pas proposé"
    assert "jamais une valeur attendue" in apres.observation


def test_l_essai_est_propose_quand_le_projet_en_a_un(tmp_path):
    sortie = dispatch("query_data", {"model": "client"},
                      _ctx(tmp_path, outils_web_informes=True, essai=SimpleNamespace()))
    assert f"`{essai_tools.NOM_OUTIL}`" in sortie.observation and "requêtes déclarées" not in sortie.observation


def test_l_agent_n_informe_les_outils_que_sur_le_web_et_interrupteur_allume(monkeypatch):
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation.agent import GenerationAgent

    vus = []
    monkeypatch.setattr("testpilot.generation.agent.run_loop",
                        lambda **kw: vus.append((kw["ctx"].outils_web_informes, kw["ctx"].requetes_oracle_declarees)))
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[], raw_spec="spec")
    web = {"id": 1, "connector_type": "web", "oracle_requetes_disponibles": ["etat"]}
    monkeypatch.delenv(interrupteurs.ENV_IA_INFORMEE, raising=False)
    GenerationAgent().generate(plan, projet=web)
    monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    GenerationAgent().generate(plan, projet=web)
    GenerationAgent().generate(plan, projet={**web, "connector_type": "odoo"})
    assert vus == [(False, frozenset()), (True, frozenset({"etat"})), (False, frozenset({"etat"}))]

