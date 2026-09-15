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
