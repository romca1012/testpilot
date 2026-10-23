"""Étape 7 (A110), interrupteur `TESTPILOT_CALCULS` — l'IA qui rédige les cas dit « Calcul détecté », et propose la fiche.

Ce que ces tests gardent :
1. éteint : schéma, consigne et brouillon d'avant, et aucun appel de proposition (aucun coût de plus) ;
2. allumé : la raison du calcul arrive dans le brouillon ; une fiche est proposée pour CE seul cas, normalisée ; une
   proposition mal formée est écartée, jamais réparée ; un taux n'est jamais daté par l'IA, un exemple jamais inventé ;
3. une panne de la proposition n'arrête pas le lot : le cas reste « Calcul détecté », sans fiche.
Aucun appel au modèle de langage : des doublures.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.generation import fiche_writer, interrupteurs, metier_writer


def _plan():
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[],
                    raw_spec="Le total TTC est la quantité × le prix, plus 20 % de TVA.")


class _IA:
    def __init__(self, reponse):
        self.reponse, self.appels = reponse, []

    def call_json(self, **kw):
        self.appels.append(kw)
        return self.reponse


BASE = {"title": "Total d'une commande", "preconditions": "", "steps": ["Commander 3 articles"],
        "expected_result": "Le total TTC s'affiche", "depend_dun_autre_cas_du_groupe": False, "etat_a_creer_par_ce_cas": ""}


def test_falsifiable_eteint_tout_est_comme_avant():
    ia = _IA(dict(BASE, calcul_detecte="le total dépend de la quantité"))
    brouillon = metier_writer.propose_metier(_plan(), llm=ia)
    assert ia.appels[0]["schema"] is metier_writer._METIER_SCHEMA
    assert "VALEUR CALCULÉE" not in ia.appels[0]["cached_prefix"]
    assert brouillon.calcul_detecte == "" and "calcul_detecte" not in brouillon.as_dict()


def test_allume_la_raison_du_calcul_arrive_dans_le_brouillon():
    ia = _IA(dict(BASE, calcul_detecte="le total dépend de la quantité et du prix"))
    brouillon = metier_writer.propose_metier(_plan(), llm=ia, proposer_calculs=True)
    assert "VALEUR CALCULÉE" in ia.appels[0]["cached_prefix"]
    assert ia.appels[0]["schema"]["required"][-1] == "calcul_detecte"
    assert brouillon.as_dict()["calcul_detecte"] == "le total dépend de la quantité et du prix"


def _etape(**champs):
    vide = {"resultat": "", "operation": "multiplier", "termes": [], "valeur": "", "par": "", "de": "", "taux": "",
            "limite": "", "decimales": 0, "mode": "", "tranches": [], "gauche": "", "comparateur": "", "droite": "",
            "alors": "", "sinon": ""}
    return {**vide, **champs}


PROPOSEE = {
    "nom": "Total TTC", "resultat": "total", "unite": "EUR",
    "elements": [{"nom": "quantite", "valeur": "", "source": "« la quantité »"},
                 {"nom": "prix", "valeur": "", "source": "« le prix »"},
                 {"nom": "taux_tva", "valeur": "20", "source": "« plus 20 % de TVA »"}],
    "etapes": [_etape(resultat="ht", operation="multiplier", termes=["quantite", "prix"]),
               _etape(resultat="tva", operation="pourcentage", de="ht", taux="taux_tva"),
               _etape(resultat="ttc", operation="additionner", termes=["ht", "tva"]),
               _etape(resultat="total", operation="arrondir", valeur="ttc", decimales=2, mode="au_plus_proche")],
    "exemples": [],
    "a_confirmer": ["arrondi non précisé par la spécification", "exemple chiffré à fournir"],
}


def test_falsifiable_la_proposition_est_normalisee_sans_date_ni_exemple_invente():
    mauvaise = {**PROPOSEE, "nom": "Cassée", "etapes": [_etape(resultat="r", operation="multiplier",
                                                                termes=["quantite", "inconnu"])]}
    ia = _IA({"calculs": [PROPOSEE, mauvaise]})
    fiches = fiche_writer.proposer_les_fiches(ia, specification="spec", cas=BASE, raison="le total dépend…",
                                              variables=[{"nom": "quantite"}, {"nom": "prix"}])

    assert [f["nom"] for f in fiches] == ["Total TTC"], "la proposition mal formée est écartée"
    (fiche,) = fiches
    assert "verifie_le" not in fiche["elements"][2], "l'IA ne date jamais un taux"
    assert fiche["exemples"] == [] and "exemple chiffré à fournir" in fiche["a_confirmer"]
    assert fiche["etapes"][1] == {"operation": "pourcentage", "de": "ht", "taux": "taux_tva", "resultat": "tva"}
    consigne = ia.appels[0]["cached_prefix"]
    assert "{{quantite}}, {{prix}}" in consigne and "N'en invente aucun" in consigne and "Ne date jamais" in consigne
    from testpilot.parametres import calcul
    with pytest.raises(calcul.FicheInvalide):
        calcul.valider_fiche(fiche)   # telle quelle, elle ne peut pas être retenue : date et exemple manquent


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import GenerationJobRepo, ModuleRepo, ProjectRepo

    db = tmp_path / "db.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(db)
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    GenerationJobRepo(conn).creer("j", module_id=mid, payload={"title": "T", "spec_content": "spec", "author": "a"})
    yield conn, mid
    conn.close()


@pytest.mark.parametrize("allume, panne", [(False, False), (True, False), (True, True)])
def test_falsifiable_cablage_de_la_generation(projet, monkeypatch, allume, panne):
    from testpilot.analysis.plan import TestPlan
    from testpilot.api.services import generation_service
    from testpilot.store.repositories import GenerationJobRepo

    conn, mid = projet
    monkeypatch.setenv(interrupteurs.ENV_CALCULS, "1" if allume else "0")
    propositions = []

    class _Analyse:
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[])

    def _metier(plan, **kw):
        detecte = "le total dépend du prix" if kw.get("proposer_calculs") else ""
        return metier_writer.MetierDraft(title="Total", steps=["Commander"], expected_result="Le total s'affiche",
                                         calcul_detecte=detecte)

    def _proposer(llm, **kw):
        propositions.append(kw)
        if panne:
            raise RuntimeError("API indisponible")
        return [{"nom": "Total TTC"}]

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.generation.decoupage as decoupage
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    monkeypatch.setattr(decoupage, "propose_decoupage", lambda plan, **kw: [
        SimpleNamespace(user_story="US", cases=[SimpleNamespace(brief="b", title="Total")])])
    monkeypatch.setattr(metier_writer, "propose_metier", _metier)
    monkeypatch.setattr(fiche_writer, "proposer_les_fiches", _proposer)
    monkeypatch.setattr("testpilot.llm.adapter.LLMAdapter", lambda *a, **k: object())

    generation_service.run_generation("j", module_id=mid, title="T", spec_content="spec", author="a")

    job = GenerationJobRepo(conn).get("j")
    (cas,) = job["cases"]
    assert len(propositions) == (1 if allume else 0), "aucun appel de plus interrupteur éteint"
    assert (cas.get("calcul_detecte") == "le total dépend du prix") is allume
    assert cas.get("fiches_proposees") == ([{"nom": "Total TTC"}] if allume and not panne else None)
    assert job["status"] == "awaiting_metier", "une panne de la proposition n'arrête pas le lot"
