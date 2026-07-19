"""Le formulaire incomplet et la soumission absente, vus AVANT le run — le motif de v20.

CE QUI EST ARRIVÉ (run de confirmation du 2026-07-19, cas 9 / version 20). Le scénario généré
remplissait **2 champs sur 8 requis** puis affirmait qu'un ticket était créé, sans jamais cliquer
« Envoyer » — il se contentait de « j'attends la soumission du formulaire », qui n'envoie RIEN.
Résultat : 4 scénarios `non_conforme` (« devrait être 26216, obtenu 26215 »), diagnostiqués à la
main. Sonde HTTP/RPC : **aucun POST**, delta 0 ticket — l'application, elle, refusait correctement
un formulaire incomplet.

Les deux moitiés du défaut sont donc contrôlées ici : les champs REQUIS et la SOUMISSION.
Module pur : aucun navigateur, aucun LLM, aucune I/O.
"""
import pytest

from testpilot.generation import smoke_check

# Le modèle du domaine, réduit à ce qui compte — mais FIDÈLE au réel : les deux routes qui portent
# `types_demandes` exigent exactement les mêmes 8 champs (mesuré sur `data/domain/odoo.json`).
REQUIS = ["name", "types_demandes", "partner_name", "partner_email",
          "destinataire_name", "street", "city", "zip"]


def _page(requis=REQUIS, extra=("product", "team_id")):
    champs = [{"name": n, "required": True, "tag": "input"} for n in requis]
    champs += [{"name": n, "required": False, "tag": "input"} for n in extra]
    return {"champs": champs}


MODELE = {"mesure_le": "2026-07-17",
          "pages": {"/formulaire/{id}": _page(), "/product/{id}/accessories": _page()}}

# Le scénario RÉEL de v20, tel qu'il était en base (extrait fidèle).
V20_NOMINAL = """# language: fr
Fonctionnalité: Demande de matériel

  Scénario: [NOMINAL] Demande avec PC Portable HP
    Soit le nombre d'enregistrements dans le modèle "helpdesk.ticket" est enregistré pour comparaison
    Quand je me connecte avec mes identifiants utilisateur
    Et je navigue vers l'URL du portail "/myservices"
    Et je clique sur l'onglet "Ordinateurs"
    Et je renseigne le champ "name" avec la valeur "BDD-MAT-NOM Raison"
    Et je sélectionne "nouvel_entrant" dans le champ "types_demandes"
    Et j'attends la soumission du formulaire
    Alors le nombre total d'enregistrements dans le modèle "helpdesk.ticket" augmente de 1
"""


# ── forme_cible : identifier le formulaire visé ───────────────────────────────

def test_forme_cible_identifie_par_sous_ensemble_des_champs_remplis():
    """Le scénario arrive au formulaire par des CLICS, sans nommer sa route (cas de v20) :
    c'est l'ensemble des champs remplis qui identifie la forme."""
    cible = smoke_check.forme_cible({"name", "types_demandes"}, [], MODELE)
    assert cible is not None, "les champs remplis désignent bien un formulaire connu"
    _, requis = cible
    assert requis == set(REQUIS)


def test_forme_cible_tolere_l_ambiguite_quand_les_candidats_exigent_LA_MEME_chose():
    """⚠️ Raffinement décidé sur les données réelles. `name`+`types_demandes` désignent DEUX
    routes, qui exigent exactement les mêmes 8 champs. Se taire là serait se taire sur le cas
    qu'on veut attraper, alors qu'aucune information ne manque."""
    route, requis = smoke_check.forme_cible({"name", "types_demandes"}, [], MODELE)
    assert "/formulaire/{id}" in route and "/product/{id}/accessories" in route
    assert requis == set(REQUIS)


def test_forme_cible_se_tait_si_les_candidats_DIVERGENT():
    """Ambiguïté réelle → silence. Faux négatif acceptable, faux positif non (§4.4)."""
    modele = {"pages": {"/a": _page(requis=["name", "types_demandes"]),
                        "/b": _page(requis=["name", "types_demandes", "iban"])}}
    assert smoke_check.forme_cible({"name", "types_demandes"}, [], modele) is None


def test_forme_cible_departage_par_la_route_quand_elle_est_explicite():
    modele = {"pages": {"/a/{id}": _page(requis=["name", "types_demandes"]),
                        "/b/{id}": _page(requis=["name", "types_demandes", "iban"])}}
    route, requis = smoke_check.forme_cible(
        {"name", "types_demandes"}, ["http://odoo/b/78"], modele)
    assert route == "/b/{id}" and "iban" in requis


def test_forme_cible_se_tait_si_aucun_formulaire_ne_contient_les_champs():
    assert smoke_check.forme_cible({"champ_inconnu_xyz"}, [], MODELE) is None


# ── Les champs requis manquants ───────────────────────────────────────────────

def test_v20_les_champs_requis_manquants_sont_NOMMES():
    """Le message doit nommer PRÉCISÉMENT les champs manquants — jamais un « formulaire
    incomplet » générique, qui n'apprend rien à celui qui doit corriger (§0002)."""
    ws = smoke_check.check_champs_requis_remplis(V20_NOMINAL, MODELE)

    assert len(ws) == 1
    msg = ws[0]["message"]
    for manquant in ("partner_name", "partner_email", "destinataire_name", "street", "city", "zip"):
        assert manquant in msg, f"le champ manquant {manquant} doit être nommé"
    # Ceux que le scénario remplit ne sont PAS réclamés.
    assert "types_demandes," not in msg and not msg.count(" name,")
    assert ws[0]["kind"] == "champs_requis_manquants"
    assert ws[0]["line"] > 0


def test_un_scenario_COMPLET_ne_declenche_AUCUN_avertissement():
    """Garde anti-faux-positif : le contrôle doit se taire sur un scénario bien écrit."""
    lignes = "\n".join(
        f'    Et je renseigne le champ "{n}" avec la valeur "x"' for n in REQUIS)
    complet = ("# language: fr\nFonctionnalité: F\n\n  Scénario: [NOMINAL] Complet\n"
               + lignes
               + '\n    Et je clique sur le bouton "Envoyer"\n'
                 '    Alors le nombre total d\'enregistrements dans le modèle "t" augmente de 1\n')

    assert smoke_check.check_champs_requis_remplis(complet, MODELE) == []
    assert smoke_check.check_step_soumission(complet) == []


def test_un_scenario_d_ERREUR_qui_omet_un_champ_EXPRES_n_est_pas_signale():
    """⚠️ Le faux positif trouvé sur les vraies données. « [ERREUR] Soumission sans remplir le
    champ obligatoire » omet un requis **par construction** — c'est son objet même. L'alerter
    reviendrait à crier sur le scénario le mieux écrit du lot."""
    erreur = ('# language: fr\nFonctionnalité: F\n\n'
              '  Scénario: [ERREUR] Soumission sans le champ obligatoire\n'
              '    Quand je renseigne le champ "name" avec la valeur "x"\n'
              '    Et je clique sur le bouton "Envoyer"\n'
              '    Alors le nombre total d\'enregistrements dans le modèle "t" n\'a pas augmenté\n')

    assert smoke_check.check_champs_requis_remplis(erreur, MODELE) == []


# ── La soumission absente ─────────────────────────────────────────────────────

def test_v20_la_soumission_absente_est_signalee_et_l_attente_passive_denoncee():
    """« j'attends la soumission » n'envoie rien — c'est la cause prouvée du ticket jamais créé."""
    ws = smoke_check.check_step_soumission(V20_NOMINAL)

    assert len(ws) == 1 and ws[0]["kind"] == "soumission_absente"
    assert "attend" in ws[0]["message"], "le message doit dénoncer l'attente passive"


def test_un_scenario_qui_ne_pretend_RIEN_creer_n_a_pas_a_soumettre():
    """Garde anti-faux-positif : une consultation n'a aucune soumission à faire."""
    consultation = ('# language: fr\nFonctionnalité: F\n\n'
                    '  Scénario: [NOMINAL] Consulter la liste\n'
                    '    Quand je navigue vers l\'URL du portail "/myservices"\n'
                    '    Alors la page affiche le catalogue\n')

    assert smoke_check.check_step_soumission(consultation) == []


# ── Contrat de sortie (le bandeau du gate) ────────────────────────────────────

def test_le_contrat_de_sortie_reste_celui_de_LintWarning():
    """La route du gate fait `LintWarning(**w)` : une clé en trop casserait l'affichage du CAS
    ENTIER, pour un module dont tout l'objet est d'informer sans nuire."""
    ws = smoke_check.smoke_check(V20_NOMINAL, "", modele=MODELE)

    assert ws, "le v20 réel doit produire des avertissements"
    for w in ws:
        assert set(w) == {"step", "line", "kind", "message"}


def test_sans_modele_aucun_avis_meme_pour_la_soumission():
    """Le gate doit avoir un comportement UNIQUE : pas de demi-avis selon la présence du modèle."""
    assert smoke_check.smoke_check(V20_NOMINAL, "", modele=None) == []
