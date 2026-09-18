"""Le DÉCOUPAGE d'une spécification en user stories + cas planifiés (§9a, 2026-08-05).

Ce que ces tests figent :
- une spec → une liste de user stories, chacune avec l'ensemble de cas planifiés (titre + brief) ;
- une story sans titre, ou sans aucun cas exploitable, est éliminée plutôt que de fabriquer un
  plan à trous (même prudence que `metier_writer.propose_metier`) ;
- le prompt cherche explicitement le PLUS PETIT ensemble de cas qui couvre tout, sans
  redondance — jamais « énumère tout ce qui est possible ».
"""

import json

from testpilot.analysis.plan import TestPlan
from testpilot.generation.decoupage import StoryPlan, _build_prompt, propose_decoupage


_SPEC_PAR_DEFAUT = ("La spec complète du module : la connexion se fait avec identifiant et mot "
                   "de passe ; la réinitialisation du mot de passe envoie un lien par email.")


def _plan(spec=_SPEC_PAR_DEFAUT):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


class FakeLLM:
    """Rend un texte fixe pour `call_simple` — le découpage n'utilise pas d'outil."""

    def __init__(self, payload):
        self.payload = payload

    def call_simple(self, *, user_content="", **_):
        return self.payload


_BON_JSON = json.dumps({
    "stories": [
        {"user_story": "Connexion", "citation": "la connexion se fait avec identifiant et mot de passe",
         "cases": [{"title": "Connexion réussie", "brief": "identifiants valides"}]},
        {"user_story": "Réinitialisation du mot de passe",
         "citation": "la réinitialisation du mot de passe envoie un lien par email",
         "cases": [
             {"title": "Demande valide", "brief": "email connu, lien envoyé"},
             {"title": "Email inconnu", "brief": "email absent du système, refus"},
         ]},
    ]
}, ensure_ascii=False)


# ── Le prompt cherche le MINIMAL, pas le MAXIMAL ──────────────────────────────

def test_le_prompt_cherche_explicitement_le_plus_petit_ensemble_SANS_redondance():
    """⚠️ Arbitrage du porteur (2026-08-05) : « un cas de test qui peut être validé par un autre
    n'est pas intéressant ». Le prompt doit porter CETTE consigne, pas « énumère tout le
    possible »."""
    prompt = _build_prompt(_plan())

    assert "plus petit ensemble" in prompt.lower()
    assert "redond" in prompt.lower()
    assert "n'énumère pas" in prompt.lower(), (
        "le prompt doit explicitement REFUSER l'énumération maximale, pas seulement omettre de "
        "la demander")


# ── Le découpage lui-même ──────────────────────────────────────────────────────

def test_propose_decoupage_rend_une_story_par_user_story_identifiee():
    stories = propose_decoupage(_plan(), llm=FakeLLM(_BON_JSON))

    assert [s.user_story for s in stories] == ["Connexion", "Réinitialisation du mot de passe"]


def test_le_nombre_de_cas_par_story_est_CELUI_DU_MODELE_pas_un_nombre_fixe():
    """Le cœur du §9 : une story a UN cas, l'autre en a DEUX — jamais le même nombre imposé."""
    stories = propose_decoupage(_plan(), llm=FakeLLM(_BON_JSON))

    assert len(stories[0].cases) == 1
    assert len(stories[1].cases) == 2
    assert [c.title for c in stories[1].cases] == ["Demande valide", "Email inconnu"]


def test_une_story_SANS_titre_est_ELIMINEE():
    """Un titre de story vide ne peut rien nommer sur l'écran — on ne fabrique pas de nom."""
    payload = json.dumps({"stories": [
        {"user_story": "  ", "citation": "connexion", "cases": [{"title": "Un cas", "brief": "b"}]},
        {"user_story": "Connexion", "citation": "la connexion se fait avec identifiant",
         "cases": [{"title": "Connexion réussie", "brief": "b"}]},
    ]})

    stories = propose_decoupage(_plan(), llm=FakeLLM(payload))

    assert [s.user_story for s in stories] == ["Connexion"]


def test_une_story_SANS_AUCUN_cas_exploitable_est_ELIMINEE():
    """Une story sans cas ne couvre rien — la garder créerait une Section vide."""
    payload = json.dumps({"stories": [
        {"user_story": "Story vide", "citation": "connexion", "cases": []},
        {"user_story": "Connexion", "citation": "la connexion se fait avec identifiant",
         "cases": [{"title": "Connexion réussie", "brief": "b"}]},
    ]})

    stories = propose_decoupage(_plan(), llm=FakeLLM(payload))

    assert [s.user_story for s in stories] == ["Connexion"]


def test_un_cas_SANS_titre_est_ELIMINE_mais_pas_toute_sa_story():
    payload = json.dumps({"stories": [
        {"user_story": "Connexion", "citation": "la connexion se fait avec identifiant", "cases": [
            {"title": "", "brief": "b"},
            {"title": "Connexion réussie", "brief": "b"},
        ]},
    ]})

    stories = propose_decoupage(_plan(), llm=FakeLLM(payload))

    assert len(stories) == 1
    assert [c.title for c in stories[0].cases] == ["Connexion réussie"]


def test_une_reponse_illisible_ne_FABRIQUE_aucune_story():
    """Même prudence que `metier_writer` : un plan vide et signalé, jamais des stories inventées."""
    stories = propose_decoupage(_plan(), llm=FakeLLM("désolé, je ne peux pas"))

    assert stories == []


# ── Citer ou retirer (backlog 1.2) ────────────────────────────────────────────
#
# Un site « texte pur » (aucun outil d'observation) : jusqu'ici, une user story plausible pour
# le domaine mais absente de la spec traversait cette étape sans aucun contrôle.

def test_une_story_SANS_citation_verifiable_est_ecartee():
    payload = json.dumps({"stories": [
        {"user_story": "Suppression du compte", "citation": "la suppression est instantanée",
         "cases": [{"title": "Suppression réussie", "brief": "b"}]},
        {"user_story": "Connexion", "citation": "la connexion se fait avec identifiant",
         "cases": [{"title": "Connexion réussie", "brief": "b"}]},
    ]})

    stories = propose_decoupage(_plan(), llm=FakeLLM(payload))

    assert [s.user_story for s in stories] == ["Connexion"]


def test_une_citation_reformulee_ne_suffit_pas():
    """La citation doit être un extrait MOT POUR MOT — une paraphrase fidèle sur le fond ne
    prouve pas que la story vient réellement de la spec."""
    payload = json.dumps({"stories": [
        {"user_story": "Connexion", "citation": "l'utilisateur s'authentifie sur la plateforme",
         "cases": [{"title": "Connexion réussie", "brief": "b"}]},
    ]})

    stories = propose_decoupage(_plan(), llm=FakeLLM(payload))

    assert stories == []


def test_story_plan_as_dict_porte_le_meme_patron_que_metier_writer():
    from testpilot.generation.decoupage import CaseBrief

    story = StoryPlan(user_story="Connexion",
                      cases=[CaseBrief(title="T", brief="b")])

    assert story.as_dict() == {"user_story": "Connexion",
                               "cases": [{"title": "T", "brief": "b"}]}


# ── Sorties structurées (même patron que `metier_writer`, §2bis A2) ──────────

def test_propose_decoupage_passe_par_call_json_quand_disponible():
    class _Adaptateur:
        def __init__(self):
            self.appels = []

        def call_json(self, *, schema, **kw):
            self.appels.append("structured")
            return json.loads(_BON_JSON)

    adaptateur = _Adaptateur()
    stories = propose_decoupage(_plan(), llm=adaptateur)

    assert adaptateur.appels == ["structured"]
    assert len(stories) == 2
