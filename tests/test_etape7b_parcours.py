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
