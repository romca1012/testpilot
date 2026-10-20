"""Revue A62 (bloquant, 2026-10-20) — une régénération après un vrai défaut de l'application ne doit jamais passer au vert
en silence.

Scénario mesuré en revue : le cas attend « Total TTC 129,51 € », l'application (fautive) affiche 107,93 € ; le test sort
`non_conforme`. On régénère : l'agent lit 107,93 € sur la capture et l'écrit dans l'« Alors ». Sans garde, la nouvelle
version était approuvée d'office (A62) et le test suivant passait au vert sur une application fausse.

Ce que ces tests gardent :
1. régénération après un défaut FONCTIONNEL, « Alors » changé, cas inchangé → point de vigilance, jamais approuvée
   d'office, et aucun appel de correction ;
2. après une erreur technique, ou si le cas lui-même a changé, ou si les vérifications n'ont pas changé → prête à lancer ;
3. le fait vient de la provenance consignée par la génération, jamais du texte de l'agent ; l'automatisation le transmet ;
4. une correction ou une réparation d'un ancien test déjà non rejouable n'est pas rendue impossible (A61).
"""

import json

import pytest

from testpilot import config
from testpilot.api.services import generation_service as service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ReviewRepo, VersionRepo, ensure_default_module
from testpilot.verdict.review_gate import evaluate_gate

ANCIEN = ('# language: fr\nFonctionnalité: Panier\n  Scénario: Total\n    Quand j\'ouvre la page "/panier"\n'
          '    Alors la page affiche le texte "129,51 €"\n')
RECOPIE = ANCIEN.replace("129,51 €", "107,93 €")   # l'agent a recopié la valeur fausse vue sur la capture


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "regeneration.db")
    c = get_initialized_db()
    yield c
    c.close()


def _version(conn, cid, feature, *, attendu="Total TTC 129,51 €", provenance=None):
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                   steps_content="", title="Total", test_steps=json.dumps(["Ouvrir le panier"]),
                                   expected_result=attendu)
    if provenance is not None:
        conn.execute("UPDATE test_case_version SET generation_provenance=? WHERE id=?", (json.dumps(provenance), vid))
        conn.commit()
    CaseRepo(conn).set_current_version(cid, vid)
    return vid


def _cas_avec_echec(conn, statut_fonctionnel="non_conforme", statut_execution="success"):
    cid = CaseRepo(conn).create(title="Total", module_id=ensure_default_module(conn, "boutique"), feature_slug="total")
    vid = _version(conn, cid, ANCIEN)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status=?, functional_status=? WHERE id=?",
                 (statut_execution, statut_fonctionnel, eid))
    conn.commit()
    return cid, vid, eid


def _avis(conn, cid):
    case = CaseRepo(conn).get(cid)
    return [w["kind"] for w in service.lint_warnings_for_version(conn, case, VersionRepo(conn).list_for_case(cid),
                                                                    case["current_version_id"])]


def test_falsifiable_regeneree_apres_un_defaut_avec_un_alors_change_n_est_jamais_approuvee(conn, monkeypatch):
    cid, vid, eid = _cas_avec_echec(conn)
    fait = service._dernier_defaut_fonctionnel(conn, cid)
    assert fait == {"execution_id": eid, "version_id": vid}
    nouvelle = _version(conn, cid, RECOPIE, provenance={"regeneration_apres_defaut": fait})

    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _avis(conn, cid)
    appels = []
    monkeypatch.setattr("testpilot.generation.correction_agent.propose_correction", lambda **kw: appels.append(kw))
    service._finaliser_version_generee(conn, cid, nouvelle, module_name="total", dry_runner=object())
    assert not evaluate_gate(ReviewRepo(conn), nouvelle).allowed, "jamais approuvée d'office"
    assert appels == [], "une correction automatique ne peut pas savoir si l'application est juste"


def test_apres_une_erreur_technique_la_regeneration_reste_prete_a_lancer(conn):
    cid, vid, _ = _cas_avec_echec(conn, statut_fonctionnel="indetermine", statut_execution="technical_error")
    assert service._dernier_defaut_fonctionnel(conn, cid) is None
    nouvelle = _version(conn, cid, RECOPIE, provenance={})
    service._finaliser_version_generee(conn, cid, nouvelle)
    assert evaluate_gate(ReviewRepo(conn), nouvelle).allowed


def test_falsifiable_le_signal_est_etroit(conn):
    cid, vid, eid = _cas_avec_echec(conn)
    _version(conn, cid, ANCIEN, provenance={"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}})
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT not in _avis(conn, cid), "mêmes vérifications : rien à signaler"


def test_falsifiable_une_retouche_du_cas_n_eteint_pas_le_signal(conn):
    """Deuxième passe de revue : la personne précise une étape (attendu inchangé), régénère ; l'agent voit toujours la
    capture à 107,93 € et la recopie. L'exemption « le cas a changé » l'éteignait."""
    cid, vid, eid = _cas_avec_echec(conn)
    fait = {"execution_id": eid, "version_id": vid}
    nouvelle = VersionRepo(conn).create(
        test_case_id=cid, spec_content="", spec_hash="", feature_content=RECOPIE, steps_content="", title="Total",
        test_steps=json.dumps(["Ouvrir le panier", "Lire le total TTC"]), expected_result="Total TTC 129,51 €")
    conn.execute("UPDATE test_case_version SET generation_provenance=? WHERE id=?",
                 (json.dumps({"regeneration_apres_defaut": fait}), nouvelle))
    conn.commit()
    CaseRepo(conn).set_current_version(cid, nouvelle)
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _avis(conn, cid)


def test_falsifiable_une_correction_intercalee_ne_perd_pas_le_fait(conn, monkeypatch):
    """Deuxième passe de revue, reproduit : V2 régénérée recopie 107,93 € et porte un second avis corrigeable ; la
    correction automatique renforce l'autre point sans toucher l'« Alors » et crée V3. V3 ne doit pas être approuvée."""
    from types import SimpleNamespace

    from testpilot.generation.provenance import revision_metadata

    cid, vid, eid = _cas_avec_echec(conn)
    v2 = _version(conn, cid, RECOPIE, provenance={"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}})
    v3 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=RECOPIE,
                                  steps_content="# renforcée\n", title="Total", test_steps=json.dumps(["Ouvrir le panier"]),
                                  expected_result="Total TTC 129,51 €", created_by="correction-agent",
                                  **revision_metadata(VersionRepo(conn).get(v2)))
    CaseRepo(conn).set_current_version(cid, v3)
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _avis(conn, cid), "le fait suit la chaîne `origin`"
    service._finaliser_version_generee(conn, cid, v3, module_name="total", dry_runner=SimpleNamespace())
    assert not evaluate_gate(ReviewRepo(conn), v3).allowed


def test_falsifiable_un_echec_technique_apres_le_defaut_ne_l_efface_pas(conn):
    cid, vid, eid = _cas_avec_echec(conn)
    e2 = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='technical_error', functional_status='indetermine' WHERE id=?",
                 (e2,))
    conn.commit()
    assert service._dernier_defaut_fonctionnel(conn, cid) == {"execution_id": eid, "version_id": vid}


def test_falsifiable_un_defaut_intermittent_montre_a_l_agent_reste_consigne(conn):
    """Troisième passe de revue : E1 non_conforme puis E2 conforme. L'agent qui régénère reçoit toujours E1 (dernier échec)
    — le fait doit être consigné, sinon la valeur fausse recopiée s'approuve d'office."""
    cid, vid, eid = _cas_avec_echec(conn)
    e2 = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='success', functional_status='conforme' WHERE id=?", (e2,))
    conn.commit()
    assert service._dernier_echec(conn, cid)["id"] == eid, "l'échec montré à l'agent"
    assert service._dernier_defaut_fonctionnel(conn, cid) == {"execution_id": eid, "version_id": vid}


def test_sans_aucun_defaut_aucun_fait(conn):
    cid = CaseRepo(conn).create(title="Total", module_id=ensure_default_module(conn, "boutique"), feature_slug="total")
    vid = _version(conn, cid, ANCIEN)
    e1 = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='technical_error', functional_status='indetermine' WHERE id=?",
                 (e1,))
    conn.commit()
    assert service._dernier_defaut_fonctionnel(conn, cid) is None


def test_falsifiable_une_retouche_du_titre_apres_une_approbation_humaine_ne_ressuscite_pas_l_avis(conn):
    cid, vid, eid = _cas_avec_echec(conn)
    v2 = _version(conn, cid, RECOPIE, provenance={"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}})
    ReviewRepo(conn).create(test_case_id=cid, version_id=v2, decision="approved", reviewer="porteur")
    v3 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=RECOPIE,
                                  steps_content="", title="Total (titre retouché)",
                                  test_steps=json.dumps(["Ouvrir le panier"]), expected_result="Total TTC 129,51 €")
    CaseRepo(conn).set_current_version(cid, v3)
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT not in _avis(conn, cid)


def test_falsifiable_une_fonction_de_verification_reecrite_est_signalee(conn):
    """L'« Alors » est gardé mot pour mot, mais sa fonction `@then` ne compare plus la valeur (aligné sur D30)."""
    avant = ('from behave import then\n\n@then(\'la page affiche le texte "{t}"\')\n'
             'def step_impl(context, t):\n    assert t in context.page.content()\n')
    apres = avant.replace("    assert t in context.page.content()\n", "    context.page.content()\n")
    cid = CaseRepo(conn).create(title="Total", module_id=ensure_default_module(conn, "boutique"), feature_slug="total")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=ANCIEN,
                                   steps_content=avant, title="Total", test_steps=json.dumps(["Ouvrir le panier"]),
                                   expected_result="Total TTC 129,51 €")
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='success', functional_status='non_conforme' WHERE id=?", (eid,))
    conn.commit()
    nouvelle = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=ANCIEN,
                                        steps_content=apres, title="Total", test_steps=json.dumps(["Ouvrir le panier"]),
                                        expected_result="Total TTC 129,51 €")
    conn.execute("UPDATE test_case_version SET generation_provenance=? WHERE id=?",
                 (json.dumps({"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}}), nouvelle))
    conn.commit()
    CaseRepo(conn).set_current_version(cid, nouvelle)
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _avis(conn, cid)


def test_une_version_approuvee_par_une_personne_ne_porte_plus_le_signal(conn):
    cid, vid, eid = _cas_avec_echec(conn)
    nouvelle = _version(conn, cid, RECOPIE,
                        provenance={"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}})
    ReviewRepo(conn).create(test_case_id=cid, version_id=nouvelle, decision="approved", reviewer="validation-metier")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _avis(conn, cid), "une approbation automatique n'a rien jugé"
    ReviewRepo(conn).create(test_case_id=cid, version_id=nouvelle, decision="approved", reviewer="porteur")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT not in _avis(conn, cid)


def test_falsifiable_l_automatisation_transmet_le_fait_a_la_generation(conn, monkeypatch, tmp_path):
    """Câblage : `run_automation` donne `regeneration_apres_defaut` à `generate` (fait consigné, jamais un texte)."""
    from types import SimpleNamespace

    from testpilot.analysis.plan import TestPlan

    cid, vid, eid = _cas_avec_echec(conn)
    vus = {}

    class _Agent:
        def __init__(self, **kw):
            pass

        def generate(self, plan, **kw):
            vus.update(kw)
            raise RuntimeError("arrêt du test")

    class _Analyse:
        def __init__(self, **kw):
            pass

        def analyze_spec_content(self, slug, contenu):
            return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[])

    import testpilot.analysis.spec_analyzer as spec_analyzer
    import testpilot.connectors.factory as factory
    import testpilot.generation.agent as agent_mod
    monkeypatch.setattr(agent_mod, "GenerationAgent", _Agent)
    monkeypatch.setattr(spec_analyzer, "SpecAnalyzer", _Analyse)
    monkeypatch.setattr(factory, "build_connector", lambda projet: SimpleNamespace(connect=lambda: None,
                                                                                  disconnect=lambda: None))
    from testpilot.store.repositories import GenerationJobRepo
    GenerationJobRepo(conn).creer("j", module_id=CaseRepo(conn).get(cid)["module_id"], payload={})
    service.run_automation("j", case_id=cid, module_id=CaseRepo(conn).get(cid)["module_id"], slug="total",
                           spec_content="spec", metier={"title": "Total", "steps": ["x"], "expected_result": "y"},
                           regeneration=True)
    assert vus.get("regeneration_apres_defaut") == {"execution_id": eid, "version_id": vid}


def test_falsifiable_la_generation_consigne_le_fait_dans_la_provenance(monkeypatch, tmp_path):
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import agent as agent_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_mod.domain_model, "DOMAIN_DIR", tmp_path / "domain")
    monkeypatch.setattr(agent_mod, "run_loop", lambda **kw: None)
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[])
    resultat = agent_mod.GenerationAgent(llm=object(), connector=None, dry_runner=None).generate(
        plan, regeneration_apres_defaut={"execution_id": 7, "version_id": 3})
    assert resultat.generation_provenance["regeneration_apres_defaut"] == {"execution_id": 7, "version_id": 3}


# ── Revue A61 : une correction d'un ancien test déjà non rejouable n'est pas rendue impossible ──────────────────────────

def test_une_correction_d_un_ancien_test_non_rejouable_n_est_pas_refusee_pour_ce_motif(tmp_path):
    from testpilot.generation import variables_de_test as vdt
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.tools.write import write_feature_file

    ancien = ('# language: fr\nFonctionnalité: F\n  Plan du scénario: S\n'
              '    Quand je renseigne le champ "age" avec la valeur "{{age}}"\n\n    Exemples:\n      | age |\n      | {{age}} |\n')
    ctx = ToolContext(module_name="acces", generated_dir=tmp_path)
    ctx.references_figees = vdt.references_du_texte(ancien)
    ctx.feature_de_reference = ancien
    sortie = write_feature_file(ctx, ancien)
    assert "rejoué ligne par ligne" not in sortie.observation, sortie.observation


# ── A66 (porteur, 2026-10-20) : après une « donnée refusée », changer la seule donnée est la réparation attendue ──────────

PLAN = """# language: fr
Fonctionnalité: Clients
  Plan du scénario: Création
    Quand je renseigne le champ "email" avec la valeur "<email>"
    Alors la page affiche le texte "<message>"

    Exemples:
      | email | message |
      | jean.dupont@exemple | Client créé |
"""


def _regeneree_apres(conn, statut, feature_apres, *, avant=PLAN, attendu="Total TTC 129,51 €"):
    n = conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0]
    cid = CaseRepo(conn).create(title=f"Clients {n}", module_id=ensure_default_module(conn, "crm"),
                                feature_slug=f"clients_{n}")
    vid = _version(conn, cid, avant, attendu=attendu)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='success', functional_status=? WHERE id=?", (statut, eid))
    conn.commit()
    _version(conn, cid, feature_apres, attendu=attendu,
             provenance={"regeneration_apres_defaut": {"execution_id": eid, "version_id": vid}})
    return _avis(conn, cid)


def test_falsifiable_apres_une_donnee_refusee_changer_la_donnee_est_pret_a_lancer(conn):
    seule_donnee = PLAN.replace("jean.dupont@exemple |", "jean.dupont@exemple.fr |")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT not in _regeneree_apres(conn, "donnee_invalide", seule_donnee)


def test_falsifiable_apres_une_donnee_refusee_changer_l_attendu_reste_signale(conn):
    """Le résultat attendu passe par une colonne que l'« Alors » cite : la changer, c'est changer la vérification."""
    attendu_change = PLAN.replace("| Client créé |", "| Adresse invalide |")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", attendu_change)
    alors_change = PLAN.replace('Alors la page affiche le texte "<message>"', 'Alors la page affiche le texte "Erreur"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", alors_change)


def test_falsifiable_apres_un_non_conforme_changer_la_donnee_reste_signale(conn):
    seule_donnee = PLAN.replace("jean.dupont@exemple |", "jean.dupont@exemple.fr |")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "non_conforme", seule_donnee)


# ── Quatrième passe de revue : une donnée en dur dans un « Quand », un « Alors » à tableau ou à texte joint ─────────────

ACCES = """# language: fr
Fonctionnalité: Accès
  Scénario: Mineur
    Quand je renseigne le champ "age" avec la valeur "17"
    Alors la page affiche le texte "Accès refusé"
"""


def test_falsifiable_apres_un_non_conforme_une_donnee_en_dur_changee_est_signalee(conn):
    """Le défaut du banc `limite_age_decalee` : l'application accepte 17 ans ; l'IA voit « Accès autorisé » et passe à 16.
    L'« Alors » est intact — le test passerait au vert sur une borne fausse."""
    seize = ACCES.replace('"17"', '"16"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "non_conforme", seize, avant=ACCES)


def test_falsifiable_apres_une_donnee_refusee_une_donnee_que_le_cas_cite_reste_signalee(conn):
    """L'application pose à tort `min="19"` et refuse le 18 que le cas exige ; passer à 19 masquerait le défaut."""
    majeur = ACCES.replace('"17"', '"18"').replace("Accès refusé", "Accès autorisé")
    dix_neuf = majeur.replace('"18"', '"19"')
    avis = _regeneree_apres(conn, "donnee_invalide", dix_neuf, avant=majeur, attendu="À 18 ans, l'accès est autorisé")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in avis


def test_apres_une_donnee_refusee_une_donnee_en_dur_que_le_cas_ne_cite_pas_est_pret_a_lancer(conn):
    courriel = ACCES.replace('"age" avec la valeur "17"', '"email" avec la valeur "jean.dupont@exemple"')
    corrige = courriel.replace("jean.dupont@exemple", "jean.dupont@exemple.fr")
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT not in _regeneree_apres(conn, "donnee_invalide", corrige,
                                                                             avant=courriel)


TABLEAU = """# language: fr
Fonctionnalité: Panier
  Plan du scénario: Total
    Quand je renseigne le champ "quantite" avec la valeur "<quantite>"
    Alors le panier affiche :
      | total   |
      | <total> |

    Exemples:
      | quantite | total  |
      | 3        | 129,51 |
"""
TEXTE_JOINT = TABLEAU.replace("      | total   |\n      | <total> |\n",
                              '      """\n      Total <total>\n      """\n')


def test_falsifiable_un_alors_a_tableau_ou_a_texte_qui_cite_une_colonne_n_est_pas_une_donnee(conn):
    assert "Total <total>" in TEXTE_JOINT
    for feature in (TABLEAU, TEXTE_JOINT):
        change = feature.replace("| 3        | 129,51 |", "| 3        | 107,93 |")
        assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", change,
                                                                             avant=feature,
                                                                             attendu="Le panier affiche le bon total"), feature


# ── Cinquième passe de revue : une borne écrite autrement dans le cas, la cible d'une étape ─────────────────────────────

@pytest.mark.parametrize("ancienne, nouvelle, metier", [
    ("1000", "1001", "Saisir un montant de 1 000 € (minimum autorisé) : accepté"),
    ("2026-01-31", "2026-02-01", "Saisir le 31/01/2026 (dernier jour) : accepté"),
])
def test_falsifiable_une_borne_ecrite_autrement_dans_le_cas_reste_signalee(conn, ancienne, nouvelle, metier):
    avant = ACCES.replace('"age" avec la valeur "17"', f'"valeur" avec la valeur "{ancienne}"')
    apres = avant.replace(f'"{ancienne}"', f'"{nouvelle}"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", apres, avant=avant,
                                                                         attendu=metier)


def test_falsifiable_changer_le_champ_vise_n_est_pas_changer_une_donnee(conn):
    avant = ACCES.replace('"17"', '"18"')
    apres = avant.replace('le champ "age"', 'le champ "commentaire"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", apres, avant=avant,
                                                                         attendu="Saisir l'âge 18")



def test_falsifiable_changer_la_page_ouverte_n_est_pas_changer_une_donnee(conn):
    """Sixième passe de revue : l'IA contournerait l'écran fautif en ouvrant une autre page."""
    avant = ACCES.replace("    Quand je renseigne", '    Soit j\'ouvre la page "/acces"\n    Quand je renseigne')
    apres = avant.replace('"/acces"', '"/accueil"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", apres, avant=avant,
                                                                         attendu="Contrôle d'accès")


def test_falsifiable_une_valeur_citee_avec_un_accent_reste_signalee(conn):
    avant = ACCES.replace('"age" avec la valeur "17"', '"formule" avec la valeur "Premium"')
    apres = avant.replace('"Premium"', '"Standard"')
    assert service.VERIFICATION_CHANGEE_APRES_DEFAUT in _regeneree_apres(conn, "donnee_invalide", apres, avant=avant,
                                                                         attendu="La formule Prémium est proposée")
