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
