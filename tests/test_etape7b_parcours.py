"""Étape 7b (A109) : le parcours enregistré d'un cas — traduction sans IA, secret jamais gardé, ordre contrôlé à l'écriture."""

from __future__ import annotations

import pytest

from testpilot.parametres import parcours

_CLIC = {"action": "clic", "role": "button", "nom": "Nouveau", "page": "/web#commandes"}
_SAISIE = {"action": "saisie", "role": "textbox", "nom": "Quantité", "champ": "product_uom_qty", "valeur": "3"}
_CHOIX = {"action": "choix", "role": "combobox", "nom": "Client", "champ": "partner_id", "valeur": "Azure"}
_VERIF = {"action": "verifier", "role": "cell", "nom": "Total", "page": "/web#commande/7"}


def _parcours(*actions):
    return parcours.pour_l_agent(parcours.normaliser(list(actions)))


def _feature(*etapes, alors='Alors le nombre affiché pour "Total" vaut "30 €"'):
    corps = "\n".join(f"    Quand {e}" for e in etapes)
    return f"# language: fr\nFonctionnalité: Commande\n  Scénario: Créer\n{corps}\n    {alors}\n"


def test_chaque_action_est_traduite_en_etape_de_la_bibliotheque():
    actions = parcours.normaliser([_CLIC, {**_CLIC, "role": "tab", "nom": "Lignes"}, _SAISIE, _CHOIX])

    assert [parcours.etape_de_test(a) for a in actions] == [
        'je clique sur le bouton "Nouveau"',
        'je clique sur l\'onglet "Lignes"',
        'je renseigne le champ "product_uom_qty" avec la valeur "3"',
        'je sélectionne "Azure" dans le champ "partner_id"',
    ]


def test_une_action_que_la_bibliotheque_ne_rejoue_pas_reste_a_ecrire_par_l_agent():
    actions = parcours.normaliser([{**_CLIC, "role": "checkbox"}, {**_CLIC, "nom": 'Dire "oui"'}, _VERIF])

    assert [parcours.etape_de_test(a) for a in actions] == [None, None, None]
    sortie = parcours.pour_l_agent(actions)
    assert [e["etape"] for e in sortie["etapes"]] == [None, None]
    assert sortie["etapes"][0]["description"] == "Cliquer sur « Nouveau » (case à cocher)"
    assert sortie["a_verifier"] == [{"role": "cell", "nom": "Total", "page": "/web#commande/7"}]


def test_falsifiable_la_valeur_d_un_mot_de_passe_n_est_jamais_gardee():
    action = parcours.normaliser([{"action": "saisie", "role": "textbox", "nom": "Mot de passe", "champ": "password",
                                   "valeur": "S3cret!", "secret": True}])[0]

    assert action["valeur"] == ""
    assert "S3cret" not in repr(action)
    assert parcours.etape_de_test(action) is None
    assert parcours.lire(action) == "Saisir le mot de passe dans « Mot de passe »"


@pytest.mark.parametrize("actions", [[], "x", [{"action": "glisser", "nom": "A"}], [{"action": "clic", "nom": ""}],
                                     [_CLIC] * (parcours.ACTIONS_MAX + 1)])
def test_falsifiable_un_parcours_mal_forme_est_refuse(actions):
    with pytest.raises(parcours.ParcoursInvalide):
        parcours.normaliser(actions)


def test_le_mode_operatoire_d_un_cas_manuel_se_lit_etape_par_etape():
    assert parcours.mode_operatoire(parcours.normaliser([_CLIC, _SAISIE, _CHOIX, _VERIF])) == [
        "1. Cliquer sur « Nouveau » (bouton)",
        "2. Saisir « 3 » dans « Quantité »",
        "3. Choisir « Azure » dans « Client »",
        "4. Vérifier le résultat attendu sur « Total » (cell)",
    ]


def test_un_test_qui_suit_le_parcours_est_accepte_meme_avec_des_actions_intercalees():
    p = _parcours(_CLIC, _SAISIE)
    feature = _feature('je clique sur le bouton "Nouveau"', 'j\'attends que la page soit chargée',
                       'je renseigne le champ "product_uom_qty" avec la valeur "3"')

    assert parcours.fautes_d_ecriture(feature, p) == []


def test_une_valeur_saisie_peut_devenir_une_donnee_de_test():
    p = _parcours(_SAISIE, _CHOIX)
    feature = _feature('je renseigne le champ "product_uom_qty" avec la valeur "{{quantite}}"',
                       'je sélectionne "{{client}}" dans le champ "partner_id"')

    assert parcours.fautes_d_ecriture(feature, p) == []


def test_falsifiable_une_action_manquante_est_dite_a_l_ecriture():
    p = _parcours(_CLIC, _SAISIE)
    fautes = parcours.fautes_d_ecriture(_feature('je clique sur le bouton "Nouveau"'), p)

    assert len(fautes) == 1 and "product_uom_qty" in fautes[0]


def test_falsifiable_un_autre_champ_ne_remplace_pas_celui_du_parcours():
    p = _parcours(_SAISIE)
    feature = _feature('je renseigne le champ "price_unit" avec la valeur "3"')

    assert parcours.fautes_d_ecriture(feature, p)


def test_falsifiable_l_ordre_du_parcours_est_respecte():
    p = _parcours(_CLIC, _SAISIE)
    feature = _feature('je renseigne le champ "product_uom_qty" avec la valeur "3"', 'je clique sur le bouton "Nouveau"')

    assert parcours.fautes_d_ecriture(feature, p)


def test_falsifiable_une_action_ecrite_en_verification_ne_compte_pas():
    p = _parcours(_CLIC)
    feature = _feature(alors='Alors je clique sur le bouton "Nouveau"')

    assert parcours.fautes_d_ecriture(feature, p)


def test_chaque_scenario_suit_le_parcours_le_contexte_compte():
    p = _parcours(_CLIC, _SAISIE)
    feature = ("# language: fr\nFonctionnalité: Commande\n  Contexte:\n    Soit je clique sur le bouton \"Nouveau\"\n"
               "  Scénario: Un\n    Quand je renseigne le champ \"product_uom_qty\" avec la valeur \"3\"\n"
               "    Alors le nombre affiché pour \"Total\" vaut \"30 €\"\n"
               "  Scénario: Deux\n    Quand je clique sur le bouton \"Annuler\"\n"
               "    Alors le nombre affiché pour \"Total\" vaut \"0 €\"\n")

    fautes = parcours.fautes_d_ecriture(feature, p)

    assert len(fautes) == 1 and "« Deux »" in fautes[0]


def test_un_parcours_sans_action_traduite_ne_contraint_rien():
    assert parcours.fautes_d_ecriture(_feature('je fais autre chose'), _parcours(_VERIF)) == []


# ── Écriture du test technique : le parcours est fixé, l'agent le recopie ──────────────────────────────────────────────

def test_falsifiable_l_agent_est_refuse_a_l_ecriture_tant_qu_il_ne_suit_pas_le_parcours(tmp_path):
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.tools.write import write_feature_file

    ctx = ToolContext(module_name="commande", generated_dir=tmp_path, parcours=_parcours(_CLIC, _SAISIE))
    refuse = write_feature_file(ctx, _feature('je clique sur le bouton "Nouveau"'))
    assert not refuse.ok and "PARCOURS" in refuse.observation and "product_uom_qty" in refuse.observation
    assert not (tmp_path / "commande.feature").exists(), "refusé : rien n'est livré"

    accepte = write_feature_file(ctx, _feature('je clique sur le bouton "Nouveau"',
                                               'je renseigne le champ "product_uom_qty" avec la valeur "3"'))
    assert accepte.ok, accepte.observation


def test_sans_parcours_l_ecriture_ne_change_pas(tmp_path):
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.tools.write import write_feature_file

    ctx = ToolContext(module_name="commande", generated_dir=tmp_path)
    assert write_feature_file(ctx, _feature('je clique sur le bouton "Autre"')).ok


def test_l_agent_recoit_les_actions_fixees_et_l_element_a_verifier_jamais_ce_que_l_ecran_montrait():
    from testpilot.generation.prompt import _section_metier

    metier = {"title": "Commande", "steps": ["Créer une commande"], "expected_result": "Le total vaut 30 €"}
    sans = _section_metier(metier)
    avec = _section_metier({**metier, "parcours": _parcours(_CLIC, {**_CLIC, "role": "menuitem", "nom": "Ventes"},
                                                            _VERIF)})

    assert "Parcours enregistré" not in sans
    assert '`je clique sur le bouton "Nouveau"`' in avec
    assert "à écrire — Cliquer sur « Ventes » (menuitem)" in avec
    assert "« Total »" in avec and "RÉSULTAT ATTENDU du cas" in avec


def test_falsifiable_automatiser_un_cas_transmet_son_dernier_parcours(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.api.services import generation_service
    from testpilot.connectors import runtime_env
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ParcoursRepo, ProjectRepo, VersionRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(runtime_env, "verifier_connexion", lambda projet: None)
    conn = get_initialized_db(tmp_path / "db.sqlite")
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="M"))
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="", steps_content="",
                                   title="Commande", test_steps='["Créer"]', expected_result="Total 30 €")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()

    _, sans = generation_service.start_automation(conn, cid)
    assert "parcours" not in sans["metier"]

    depot = ParcoursRepo(conn)
    depot.enregistrer(project_id=pid, case_id=cid, actions=parcours.normaliser([{**_CLIC, "nom": "Ancien"}]))
    dernier = depot.enregistrer(project_id=pid, case_id=cid, actions=parcours.normaliser([_CLIC, _VERIF]))
    _, avec = generation_service.start_automation(conn, cid)

    assert avec["metier"]["parcours_id"] == dernier
    assert [e["etape"] for e in avec["metier"]["parcours"]["etapes"]] == ['je clique sur le bouton "Nouveau"']
    conn.close()
