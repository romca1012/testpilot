"""§A du plan « fiabiliser le verdict automatique » (2026-08-06) : le commentaire IA qui
accompagne CHAQUE résultat automatique, tous statuts confondus — décision explicite du porteur.

Patron de test répliqué de `tests/test_generation_deux_passes.py` (FakeLLM à `call_simple`,
la voie sans sorties structurées, celle qu'un test unitaire peut exercer sans vraie API).
"""

import json

from testpilot.verdict.explication import propose_explication
from testpilot.verdict.status import CaseVerdict, ScenarioVerdict


class FakeLLM:
    def __init__(self, payload, *, leve: bool = False):
        self.payload = payload
        self.leve = leve
        self.prompts: list[str] = []

    def call_simple(self, *, user_content="", **_):
        self.prompts.append(user_content)
        if self.leve:
            raise RuntimeError("panne réseau simulée")
        return self.payload


def _verdict_passed() -> CaseVerdict:
    return CaseVerdict(
        execution_status="success", functional_status="conforme",
        scenarios=[ScenarioVerdict("Réception d'une commande valide", "success", "conforme")],
        scenarios_passed=1, scenarios_failed=0)


def _verdict_failed() -> CaseVerdict:
    return CaseVerdict(
        execution_status="success", functional_status="non_conforme",
        scenarios=[ScenarioVerdict(
            "Rejet d'un code payeur invalide", "success", "non_conforme",
            cause_category="assertion_mismatch", error="ASSERT FAILED: attendu 7 chiffres")],
        scenarios_passed=0, scenarios_failed=1)


def test_genere_un_commentaire_a_partir_du_json():
    payload = json.dumps({"explication": "Le formulaire a bien créé le ticket attendu."})

    texte, cout = propose_explication(_verdict_passed(), llm=FakeLLM(payload))

    assert texte == "Le formulaire a bien créé le ticket attendu."
    assert cout == 0.0  # FakeLLM ne track aucun token : coût nul, attendu en test unitaire.


def test_sur_un_verdict_positif_le_prompt_demande_ce_qui_a_ete_confirme():
    """Consigne §A : un « passed » doit expliquer ce qui a été vérifié, pas juste dire que
    tout va bien — sinon le commentaire n'apporte rien à un lecteur qui vérifie humainement."""
    llm = FakeLLM(json.dumps({"explication": "ok"}))

    propose_explication(_verdict_passed(), llm=llm)

    assert "positif" in llm.prompts[0] and "ce qui a été confirmé" in llm.prompts[0]


def test_le_prompt_traduit_la_cause_en_francais_clair_jamais_le_code_brut():
    """`cause_category` porte un CODE interne (`assertion_mismatch`) — le prompt doit transmettre
    son LIBELLÉ français (`defect_taxonomy.LABELS`), jamais le code, sinon l'IA reçoit du jargon
    en entrée et risque de le recopier en sortie."""
    llm = FakeLLM(json.dumps({"explication": "ok"}))

    propose_explication(_verdict_failed(), llm=llm)

    assert "Assertion métier en échec" in llm.prompts[0]
    assert "assertion_mismatch" not in llm.prompts[0]


def test_une_reponse_illisible_rend_une_chaine_vide_jamais_un_texte_invente():
    """Même discipline que `metier_writer` : pas de contenu fabriqué sur un échec de parsing."""
    texte, cout = propose_explication(_verdict_passed(), llm=FakeLLM("désolé, je ne peux pas"))

    assert texte == "" and cout == 0.0


def test_un_appel_qui_leve_ne_fait_jamais_tomber_l_appelant():
    """Best-effort ABSOLU (§A) : le verdict doit TOUJOURS pouvoir se clore, même si l'appel IA
    plante — une exception ici serait pire qu'un commentaire manquant."""
    texte, cout = propose_explication(_verdict_failed(), llm=FakeLLM("", leve=True))

    assert texte == "" and cout == 0.0


# ── Le défaut qui produisait des explications FAUSSES (2026-09-14, cas réel SauceDemo) ─────────
#
# Un test attendait le message d'erreur de connexion AVEC un point final ; SauceDemo l'affiche
# SANS. L'application avait donc PARFAITEMENT refusé la connexion — mais le commentaire généré
# affirmait « l'application a accepté la connexion... un problème de sécurité dans le système
# d'authentification », un récit inventé à partir du seul TITRE du scénario (qui annonce une
# connexion refusée), jamais du vrai écart mesuré (un point final manquant).

def _verdict_connexion_refusee_avec_ecart_texte() -> CaseVerdict:
    return CaseVerdict(
        execution_status="success", functional_status="non_conforme",
        scenarios=[ScenarioVerdict(
            "[Erreur] Connexion refusée avec mot de passe incorrect pour un utilisateur valide",
            "success", "non_conforme", cause_category="assertion_mismatch",
            error=("Message d'erreur inattendu.\n"
                   "  Attendu (contient) : 'Username and password do not match any user in "
                   "this service.'\n"
                   "  Obtenu            : 'Epic sadface: Username and password do not match "
                   "any user in this service'"))],
        scenarios_passed=0, scenarios_failed=1)


def test_le_prompt_transmet_le_vrai_detail_mesure_pas_seulement_le_titre():
    """LE correctif : sans le détail réel, le LLM ne voyait que le titre + une étiquette
    générale — et devinait. Le détail mesuré (ScenarioVerdict.error) doit désormais lui parvenir."""
    llm = FakeLLM(json.dumps({"explication": "ok"}))

    propose_explication(_verdict_connexion_refusee_avec_ecart_texte(), llm=llm)

    prompt = llm.prompts[0]
    assert "Ce que le test a réellement mesuré" in prompt
    assert "Username and password do not match any user in this service." in prompt
    assert "Epic sadface: Username and password do not match any user in this service" in prompt


def test_un_scenario_reussi_ne_porte_aucun_detail_d_erreur():
    """Rien à mesurer sur un succès — la ligne PAR SCÉNARIO ne doit apparaître QUE pour un échec.
    (La phrase existe par ailleurs dans la consigne système elle-même — on teste ici le résumé
    PAR SCÉNARIO directement, `_resume_scenario`, pas la présence du mot dans tout le prompt.)"""
    from testpilot.verdict.explication import _resume_scenario

    ligne = _resume_scenario(_verdict_passed().scenarios[0])

    assert "Ce que le test a réellement mesuré" not in ligne


def test_le_systeme_interdit_explicitement_de_deviner_depuis_le_titre():
    """Le prompt système doit porter la consigne, pas seulement le prompt utilisateur — sinon un
    modèle qui ignore une instruction noyée dans les données continuerait d'inventer."""
    from testpilot.verdict.explication import _SYSTEM

    assert "titre" in _SYSTEM.lower()
    assert "réellement mesuré" in _SYSTEM


# ── La note de confiance générique (étape 2.2 du plan de consolidation, 2026-09-15) ─────────────
#
# Ajoutée DÉTERMINISTIQUEMENT, jamais confiée au LLM : la fiabilité d'un verdict générique est un
# fait structurel du connecteur, pas une nuance qu'un modèle de langage pourrait oublier de dire.

def test_un_verdict_ui_only_recoit_la_note_deterministe():
    from testpilot.verdict.status import GROUND_TRUTH_UI_ONLY

    v = _verdict_passed()
    v.ground_truth = GROUND_TRUTH_UI_ONLY
    llm = FakeLLM(json.dumps({"explication": "Le formulaire a bien créé le ticket attendu."}))

    texte, _cout = propose_explication(v, llm=llm)

    assert texte.startswith("Le formulaire a bien créé le ticket attendu.")
    assert "recouper le résultat avec une donnée de référence côté serveur" in texte


def test_un_verdict_backend_verified_ne_recoit_aucune_note():
    """Comportement HISTORIQUE inchangé pour un cas Odoo (défaut de `CaseVerdict.ground_truth`) :
    aucune mention ajoutée, byte-identique à avant ce correctif."""
    llm = FakeLLM(json.dumps({"explication": "Le formulaire a bien créé le ticket attendu."}))

    texte, _cout = propose_explication(_verdict_passed(), llm=llm)

    assert texte == "Le formulaire a bien créé le ticket attendu."


# ── Citer ou replier (backlog 1.3) ────────────────────────────────────────────
#
# Le défaut SauceDemo (ci-dessus) n'était corrigé que par une INSTRUCTION de prompt — jamais
# vérifié après coup. Un modèle qui ignore l'instruction (ou une future régression de prompt)
# reproduirait le même récit inventé sans qu'aucun contrôle ne le détecte.

def test_une_explication_SANS_citation_verifiable_recoit_un_repli_sur():
    """Le cas mesuré, rejoué : le récit peut sembler plausible, mais rien ne le rattache au vrai
    détail mesuré — il ne doit jamais atteindre l'utilisateur tel quel."""
    payload = json.dumps({
        "explication": "L'application a accepté la connexion, un problème de sécurité existe.",
        "citation": "",
    })

    texte, _cout = propose_explication(
        _verdict_connexion_refusee_avec_ecart_texte(), llm=FakeLLM(payload))

    assert "problème de sécurité" not in texte
    assert texte == (
        "Un résultat a été mesuré pour ce test, mais l'explication automatique n'a pas pu être "
        "confirmée par rapport au détail réellement observé — voir le détail technique du "
        "scénario pour l'analyse exacte.")


def test_une_citation_reformulee_ne_suffit_pas():
    """La citation doit être un extrait MOT POUR MOT du détail mesuré — une paraphrase fidèle sur
    le fond ne prouve pas que l'explication s'appuie vraiment sur le fait réel."""
    payload = json.dumps({
        "explication": "Le message de refus affiché diffère légèrement de celui attendu.",
        "citation": "un message d'erreur différent de celui attendu a été affiché",
    })

    texte, _cout = propose_explication(
        _verdict_connexion_refusee_avec_ecart_texte(), llm=FakeLLM(payload))

    assert texte != "Le message de refus affiché diffère légèrement de celui attendu."


def test_une_explication_AVEC_citation_verifiable_est_conservee():
    payload = json.dumps({
        "explication": "L'application a bien refusé la connexion ; seul le texte exact du "
                       "message diffère de celui attendu (point final manquant).",
        "citation": "Epic sadface: Username and password do not match any user in this service",
    })

    texte, _cout = propose_explication(
        _verdict_connexion_refusee_avec_ecart_texte(), llm=FakeLLM(payload))

    assert texte.startswith("L'application a bien refusé la connexion")


def test_aucune_citation_requise_quand_rien_n_a_ete_mesure():
    """Un verdict sans échec n'a rien à confronter — exiger une citation serait absurde."""
    payload = json.dumps({"explication": "Le formulaire a bien créé le ticket attendu.",
                          "citation": ""})

    texte, _cout = propose_explication(_verdict_passed(), llm=FakeLLM(payload))

    assert texte == "Le formulaire a bien créé le ticket attendu."


def test_le_prompt_demande_explicitement_une_citation_verifiable():
    llm = FakeLLM(json.dumps({"explication": "ok", "citation": ""}))

    propose_explication(_verdict_connexion_refusee_avec_ecart_texte(), llm=llm)

    assert "citation" in llm.prompts[0].lower()
    assert "mot pour mot" in llm.prompts[0].lower()


def test_la_note_n_est_jamais_ajoutee_a_un_commentaire_vide():
    """Un échec de génération reste `("", 0.0)` — la note ne doit pas transformer un défaut
    mineur (commentaire manquant) en une demi-explication orpheline."""
    from testpilot.verdict.status import GROUND_TRUTH_UI_ONLY

    v = _verdict_passed()
    v.ground_truth = GROUND_TRUTH_UI_ONLY

    texte, cout = propose_explication(v, llm=FakeLLM("désolé, je ne peux pas"))

    assert texte == "" and cout == 0.0


# ── Lot 02 (D1) : un test `blocked` n'a rien constaté sur l'application ─────────────────────

def _verdict_bloque() -> CaseVerdict:
    return CaseVerdict(
        execution_status="blocked", functional_status="indetermine",
        scenarios=[ScenarioVerdict(
            "Rejet d'un SIREN invalide", "blocked", "indetermine",
            cause_category="precondition_non_remplie",
            error="PreconditionNonRemplieError: Le module Odoo 'x' n'est pas installé.")],
        scenarios_passed=0, scenarios_failed=1)


def test_un_test_bloque_recoit_toujours_la_note_deterministe():
    """La note n'est PAS confiée au modèle : une IA qui l'oublierait laisserait croire à un défaut."""
    payload = json.dumps({"explication": "Le test n'a pas pu commencer.",
                          "citation": "n'est pas installé"})

    texte, _ = propose_explication(_verdict_bloque(), llm=FakeLLM(payload))

    assert texte.startswith("Le test n'a pas pu commencer.")
    assert "un prérequis de l'environnement n'est pas rempli" in texte
    assert "Ce n'est pas un défaut de l'application ni du test" in texte


def test_le_prompt_d_un_test_bloque_interdit_de_conclure_a_un_defaut():
    llm = FakeLLM(json.dumps({"explication": "x", "citation": ""}))

    propose_explication(_verdict_bloque(), llm=llm)

    prompt = llm.prompts[0]
    assert "PAS pu être joué" in prompt
    assert "Ne conclus JAMAIS que l'application est défectueuse" in prompt
    assert "bloqué avant d'avoir pu être joué" in prompt


def test_les_autres_statuts_ne_recoivent_ni_note_ni_avertissement_de_blocage():
    """Non-régression : les prompts et textes des statuts existants ne changent pas."""
    llm = FakeLLM(json.dumps({"explication": "Le ticket a été créé."}))

    texte, _ = propose_explication(_verdict_passed(), llm=llm)

    assert texte == "Le ticket a été créé."
    assert "PAS pu être joué" not in llm.prompts[0]
