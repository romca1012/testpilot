"""Étape 4 — le smoke-check aurait-il vu venir les bugs qu'on a payés en runs réels ?

Le contrat est prouvé sur le **modèle réel** mesuré par `scripts/crawl_domaine.py` (aucun LLM,
aucun run) et sur le **Gherkin réel** du cas 1 tel qu'il était en base avant `0019`.

Ce que ça vaut : `types_demandes = "new"` a coûté **deux runs réels** (~30 s de timeout × 2
scénarios) puis des tentatives de réparation à ~$0,21 — pour une erreur qu'une lecture du DOM
tranche en 3 secondes. Ici, elle est vue **avant le premier run**.
"""

import pytest

from testpilot.generation.smoke_check import (
    MESSAGE_SOURCE_PREFIX,
    check_champs_existants,
    check_messages_observes,
    smoke_check,
)

# Extrait du modèle RÉEL, mesuré le 2026-07-17 sur « Portail Sapian »
# (`scripts/crawl_domaine.py`). Les options sont celles de l'application, pas des valeurs
# inventées pour le test — c'est tout l'intérêt.
MODELE = {
    "mesure_le": "2026-07-17",
    "pages": {
        "/formulaire/{id}": {"champs": [
            {"name": "name", "tag": "input", "type": "text"},
            {"name": "partner_name", "tag": "input", "type": "text"},
            # Présents sur l'application réelle (crawl du 2026-07-17). Les omettre ferait crier
            # le smoke-check sur des champs valides — un faux positif de la MISE EN SCÈNE, pas
            # du code. C'est ce qu'a montré le premier jet de ce fichier.
            {"name": "destinataire_name", "tag": "input", "type": "text"},
            {"name": "street", "tag": "input", "type": "text"},
            {"name": "city", "tag": "input", "type": "text"},
            {"name": "zip", "tag": "input", "type": "text"},
            {"name": "types_demandes", "tag": "select", "options": [
                ["nouvel_entrant", "Demande de nouvel entrant"],
                ["remplacement_materiel", "Remplacement de matériel existant"]]},
            {"name": "fonction_materiel", "tag": "select", "options": [
                ["technicien_polyvalent", "Technicien polyvalent"],
                ["technicien_interimaire", "Technicien intérimaire"],
                ["structure", "Structure"]]},
        ]},
        "/achat_vehicule/{id}": {"champs": [
            {"name": "name", "tag": "input", "type": "text"},
            {"name": "type_investissement", "tag": "select", "options": [
                ["new_aquisition", "Nouvelle acquisition"], ["remplacement", "Remplacement"]]},
        ]},
    },
}


# ── LE test : 0019 aurait été vu avant le premier run ─────────────────────────

def test_la_valeur_inventee_de_0019_est_vue_AVANT_le_run():
    """🔴 Le Gherkin RÉEL du cas 1, tel qu'il était en base — `types_demandes = "new"`.

    Cette ligne a coûté : 2 scénarios × 30 s de timeout Playwright, un diagnostic faux
    (`wrong_field_name` — « sélecteur introuvable », alors que le select est là), une réparation
    à côté, et du budget brûlé. Le smoke-check la voit sans rien exécuter.
    """
    feature = (
        'Scénario: [NOMINAL] Demande avec PC Portable HP\n'
        '  Et le champ demande "name" est rempli avec "Demande test BDD"\n'
        '  Et le champ demande "types_demandes" est rempli avec "new"\n')

    avis = smoke_check(feature, modele=MODELE)

    assert len(avis) == 1, f"attendu 1 avertissement, obtenu {avis}"
    a = avis[0]
    assert a["kind"] == "valeur_option_inexistante"
    assert a["step"] == "types_demandes"
    assert a["line"] == 3
    # Il doit donner DE QUOI CORRIGER — sinon on remplace un timeout obscur par un avis obscur.
    assert "nouvel_entrant" in a["message"] and "remplacement_materiel" in a["message"]
    # Et dire d'où il tient son information : le modèle est une photo, elle vieillit.
    assert "2026-07-17" in a["message"]


def test_la_bonne_valeur_ne_declenche_rien():
    """Anti-faux-positif : le Gherkin corrigé par `0019` D doit passer sans un mot."""
    feature = '  Et le champ demande "types_demandes" est rempli avec "nouvel_entrant"\n'
    assert smoke_check(feature, modele=MODELE) == []


def test_le_LIBELLE_affiche_est_accepte_sans_avertissement():
    """`select_option_strict` résout le libellé (repli tracé de `0007`) : le signaler serait faux.

    Le smoke-check ne doit pas contredire le helper qui va exécuter — sinon il crie sur un test
    qui marche.
    """
    feature = '  Et le champ demande "types_demandes" est rempli avec "Demande de nouvel entrant"\n'
    assert smoke_check(feature, modele=MODELE) == []


def test_un_champ_invente_est_signale_avec_le_contrat_0007():
    feature = '  Et le champ demande "Raison de la demande" est rempli avec "x"\n'
    avis = smoke_check(feature, modele=MODELE)
    assert len(avis) == 1
    assert avis[0]["kind"] == "champ_inconnu"
    assert "nom technique" in avis[0]["message"]      # le contrat A1 de 0007


def test_un_champ_connu_ailleurs_ne_declenche_rien():
    """Union sur tout le domaine (choix documenté) : `type_investissement` vit sur une AUTRE page.

    On ne signale que l'introuvable PARTOUT. Dire « mauvaise page » exigerait de suivre la
    navigation — ce module ne le fait pas, et ne prétend pas le faire.
    """
    feature = '  Et le champ demande "type_investissement" est rempli avec "remplacement"\n'
    assert smoke_check(feature, modele=MODELE) == []


# ── Les TROIS tournures Gherkin réelles ───────────────────────────────────────

def test_les_trois_tournures_reelles_sont_toutes_reconnues():
    """🔴 Le trou trouvé en branchant : le smoke-check était MUET sur 2 cas sur 3.

    Mon premier jet ne couvrait que la tournure du cas 1. Mesuré sur la vraie base : **12 lignes
    reconnues sur le cas 1, 0 sur les cas 2 et 6** — et son silence ressemblait à une validation.
    C'est le motif « l'absence de signal prise pour un signal positif », dans le module même qui
    existe pour l'éviter.

    L'agent n'a aucune raison d'écrire toujours la même phrase : le §6 lui laisse composer. Les
    trois tournures ci-dessous sont **relevées sur les cas réels**, pas imaginées.
    """
    tournures = [
        # cas 1
        '    Et le champ demande "types_demandes" est rempli avec "new"',
        # cas 2 et 6
        '    Et je renseigne le champ "types_demandes" avec la valeur "new"',
        # cas 6
        '    Et je sélectionne "new" dans le champ "types_demandes"',
    ]
    for ligne in tournures:
        avis = smoke_check(ligne, modele=MODELE)
        assert len(avis) == 1, f"tournure non reconnue → smoke-check muet : {ligne!r}"
        assert avis[0]["kind"] == "valeur_option_inexistante"
        assert avis[0]["step"] == "types_demandes"


def test_les_tournures_de_VERIFICATION_ne_sont_PAS_matchees():
    """Anti-faux-positif : « le dernier ticket créé a le champ … » affirme un état APRÈS coup.

    Ces lignes portent des noms de champs du **modèle Odoo** (RPC), pas des attributs HTML d'un
    formulaire. Les matcher ferait crier `champ_inconnu` sur des assertions valides — un faux
    positif systématique, que la borne du principe 2 interdit.
    """
    verifications = [
        '    Et le dernier ticket créé a le champ "team_id" pointant vers "Demandes Matériel"',
        '    Et le dernier ticket créé a le champ "denomination" égal à "Citroën Berlingo"',
        '    Et un enregistrement avec le champ "name" égal à "x" existe dans "helpdesk.ticket"',
    ]
    for ligne in verifications:
        assert smoke_check(ligne, modele=MODELE) == [], f"faux positif sur une vérification : {ligne!r}"


# ── Ce que le smoke-check NE PEUT PAS faire — dit, pas caché ──────────────────

def test_sans_modele_il_se_tait_et_ne_valide_RIEN():
    """⚠️ Le piège : « aucun avertissement » sans modèle ≠ « le test est bon ».

    C'est le motif que ce projet traque — l'absence de signal prise pour un signal positif.
    L'appelant doit savoir si un modèle existe ; il ne peut pas le déduire d'une liste vide.
    """
    feature = '  Et le champ demande "types_demandes" est rempli avec "new"\n'
    assert smoke_check(feature, modele=None) == []
    assert smoke_check(feature, modele={}) == []
    assert smoke_check(feature, modele={"pages": {}}) == []


def test_le_gherkin_REEL_de_v1_declenche_bien_l_avertissement():
    """🔴 La preuve sur les VRAIES données — pas sur un extrait que j'aurais écrit à ma main.

    Reproduit ce qui a été vérifié en réel le 2026-07-17 : le `.feature` de `v1` **tel qu'il était
    en base**, passé au modèle **tel que le crawl l'a mesuré**, produit **2 avertissements** — un
    par occurrence de `types_demandes = "new"` (lignes 20 et 48).

    Ces 2 lignes ont coûté 2 timeouts de 30 s, un diagnostic faux et des réparations à côté. Le
    smoke-check les voit pour $0, avant le premier run.

    ⚠️ Le Gherkin est reproduit ici **verbatim** (extrait des lignes qui comptent) plutôt que lu en
    base : un test ne doit pas dépendre de l'état d'une base de dev — `v1` a depuis été remplacée
    par `v8` (fix `0019` D), et le test se mettrait à passer pour la mauvaise raison.
    """
    feature_v1 = (
        'Scénario: [NOMINAL] Demande avec PC Portable HP et accessoires par défaut\n'
        '  Et le champ demande "name" est rempli avec "Demande test BDD - PC Portable HP"\n'
        '  Et le champ demande "types_demandes" est rempli avec "new"\n'
        '  Et le champ demande "destinataire_name" est rempli avec "Jean Dupont"\n'
        'Scénario: [LIMITE] Demande avec PC Portable HP 14 VIP et 4 accessoires\n'
        '  Et le champ demande "types_demandes" est rempli avec "new"\n')

    avis = smoke_check(feature_v1, modele=MODELE)
    fautifs = [a for a in avis if a["kind"] == "valeur_option_inexistante"]

    assert len(fautifs) == 2, f"les 2 occurrences de « new » doivent être vues : {avis}"
    assert {a["step"] for a in fautifs} == {"types_demandes"}
    # `destinataire_name` n'est pas dans l'extrait du modèle : il ne doit PAS être signalé comme
    # champ inconnu ici — sinon ce test croirait mesurer 0019 tout en mesurant du bruit.
    assert all(a["kind"] == "valeur_option_inexistante" for a in avis), (
        f"seule la valeur inventée doit être signalée, pas les champs absents du modèle : {avis}")


def test_la_navigation_manquante_de_0020_N_EST_PAS_vue():
    """🔴 La LIMITE, verrouillée par un test plutôt qu'écrite dans une doc que personne ne lit.

    `0020` : le test clique l'onglet « Ordinateurs » depuis `/my/home`, où il n'est pas. Les
    champs et valeurs sont **tous corrects** — c'est la PAGE qui est fausse. Ce module est pur et
    sans état : il ne suit pas la navigation, donc il **ne peut pas** voir ça.

    Le dire par un test évite qu'on croie le smoke-check plus fort qu'il n'est. Attraper `0020`
    demande un modèle de TRANSITIONS (le graphe de l'étape 3), pas un index de champs.
    """
    feature = (
        '  Soit le demandeur est authentifié sur le portail des services\n'
        '  Et le demandeur clique sur onglet "Ordinateurs"\n'
        '  Et le champ demande "types_demandes" est rempli avec "nouvel_entrant"\n')

    assert smoke_check(feature, modele=MODELE) == [], (
        "si ce test échoue, le smoke-check a gagné une capacité : mettre à jour la note 0021")


# ── §F8 (2026-09-23) : un texte de message doit avoir été OBSERVÉ, pas deviné ─────────────────
#
# Rejoue le défaut mesuré en campagne réelle (cas 97, projet Sapian portail, 23/09/2026,
# `docs/mesures/campagne-lot01-2026-09-23.md`) : un step personnalisé affirmait un message de
# validation HTML5 exact que l'agent n'avait jamais observé — le message réel de l'application
# était différent, ce qui a produit un faux `non_conforme` (l'app avait raison de refuser, c'est
# le TEXTE du test qui se trompait).

_FEATURE_MESSAGE_DEVINE = (
    '  Alors le message de validation HTML5 contenant '
    '"Veuillez saisir un numéro à 7 chiffres" est affiché sur le champ "code_client1"\n')


def test_GARDE_un_message_jamais_observe_est_signale():
    avis = check_messages_observes(_FEATURE_MESSAGE_DEVINE, verified_fields={})

    assert len(avis) == 1
    assert avis[0]["kind"] == "message_non_observe"
    assert "Veuillez saisir un numéro à 7 chiffres" in avis[0]["message"]


def test_un_message_reellement_observe_ne_declenche_rien():
    """Le fragment observé (`attempt_form_submission`, via `MESSAGE_SOURCE_PREFIX`) DISCULPE le
    texte du test — correspondance partielle dans les deux sens, comme les autres contrôles."""
    verified = {f"{MESSAGE_SOURCE_PREFIX}attempt_form_submission:/mutation":
                ["Veuillez saisir un numéro à 7 chiffres."]}

    assert check_messages_observes(_FEATURE_MESSAGE_DEVINE, verified_fields=verified) == []


def test_sans_registre_aucune_generation_instrumentee_le_smoke_check_se_tait():
    """`verified_fields is None` (version ancienne) ne peut rien prouver ni infirmer — silence,
    même contrat que `check_champs_existants` dans le même cas."""
    assert check_messages_observes(_FEATURE_MESSAGE_DEVINE, verified_fields=None) == []


def test_un_registre_VIDE_mais_instrumente_signale_quand_meme():
    """`{}` (génération instrumentée, rien observé) N'EST PAS `None` — le motif exact que ce lot
    corrige : le silence sur un registre vide masquerait précisément le cas 97."""
    avis = check_messages_observes(_FEATURE_MESSAGE_DEVINE, verified_fields={})
    assert len(avis) == 1


def test_un_texte_hors_alors_nest_pas_concerne():
    """Seules les lignes d'assertion (`Alors`/`Et`/`Mais`) sont concernées — une simple mention du
    mot « message » dans un `Quand`/`Soit` n'affirme rien et ne doit rien déclencher."""
    feature = '  Quand je clique sur le bouton "Envoyer un message"\n'
    assert check_messages_observes(feature, verified_fields={}) == []


def test_les_entrees_de_message_ne_sont_jamais_prises_pour_des_noms_de_champ():
    """§F8 : une entrée `message:…` de `verified_fields` porte un TEXTE, jamais un nom de champ —
    `check_champs_existants` doit continuer à l'ignorer, sinon un message qui contient par hasard
    la même chaîne qu'un champ existant masquerait un vrai `champ_inconnu`."""
    verified = {f"{MESSAGE_SOURCE_PREFIX}attempt_form_submission:/x": ["code_client1_invalide"]}
    feature = '  Et je renseigne le champ "code_client1_invalide" avec la valeur "test"\n'

    avis = check_champs_existants(feature, modele={}, verified_fields=verified)

    assert len(avis) == 1 and avis[0]["kind"] == "champ_inconnu", (
        "le texte du message ne doit pas être confondu avec un nom de champ observé")


def test_un_message_observe_trop_court_ne_disculpe_pas_n_importe_quel_texte():
    """Un message observé vide ou d'un caractère est sous-chaîne de tout : il ne doit rien
    disculper (revue verdict-reviewer, 2026-09-24)."""
    for court in ("", " ", ".", "Erreur"):
        verified = {f"{MESSAGE_SOURCE_PREFIX}attempt_form_submission:/x": [court]}
        assert len(check_messages_observes(_FEATURE_MESSAGE_DEVINE, verified_fields=verified)) == 1
