"""La contrainte de complétude injectée au GÉNÉRATEUR (volet 1 du lot (1)+(2)).

LE DÉFAUT MESURÉ (2026-07-19). Le prompt système demandait déjà les champs requis — mais **par
l'observation** : « lis-les sur le formulaire réel ». Une instruction qui dépend de l'exploration,
donc du tirage, et que **rien ne vérifiait**. Sur la MÊME spec, deux générations successives :

    v10 → 6 champs remplis + step de soumission explicite   → le ticket est créé
    v20 → 2 champs sur 8, aucune soumission                 → rien n'est créé, 4 `non_conforme`

L'annuaire portait pourtant `required: true` sur les 8 champs depuis toujours : **seul le gate le
lisait**. On donne désormais la liste au générateur au lieu de la lui faire deviner — motif `0021`
(*lire plutôt que deviner*), appliqué au remplissage.

Tests à froid : aucun LLM, aucune I/O réseau.
"""
from testpilot.analysis.plan import TestPlan
from testpilot.generation import domain_model, prompt

REQUIS = ["name", "types_demandes", "partner_name", "partner_email",
          "destinataire_name", "street", "city", "zip"]


def _page(requis=REQUIS):
    champs = [{"name": n, "required": True, "tag": "input"} for n in requis]
    champs.append({"name": "types_demandes", "required": True, "tag": "select",
                   "options": [["nouvel_entrant", "Nouvel entrant"],
                               ["remplacement_materiel", "Remplacement"]]})
    champs.append({"name": "commentaire", "required": False, "tag": "textarea"})
    return {"champs": champs}


MODELE = {"mesure_le": "2026-07-17",
          "pages": {"/formulaire/{id}": _page(), "/product/{id}/accessories": _page(),
                    "/myservices": {"champs": [{"name": "search", "required": False}]}}}


def _plan(routes=("/formulaire/{id}",)):
    return TestPlan(module_name="demande_materiel", models=["helpdesk.ticket"], scenarios=[],
                    personas=["employé"], portal_routes=list(routes), risks=[])


# ── L'extraction depuis l'annuaire ────────────────────────────────────────────

def test_formulaires_requis_rend_les_champs_requis_de_la_route_visee():
    formulaires = domain_model.formulaires_requis(MODELE, ["/formulaire/{id}"])

    assert len(formulaires) == 1
    assert {c["name"] for c in formulaires[0]["requis"]} == set(REQUIS)


def test_formulaires_requis_deduplique_deux_routes_qui_exigent_LA_MEME_chose():
    """Mesuré : `/formulaire/{id}` et `/product/{id}/accessories` exigent exactement les mêmes
    8 champs. Les répéter noierait la contrainte sans rien apprendre."""
    formulaires = domain_model.formulaires_requis(
        MODELE, ["/formulaire/78", "/product/78/accessories"])

    assert len(formulaires) == 1, "deux formulaires identiques ne se répètent pas"


def test_formulaires_requis_matche_une_URL_CONCRETE_sur_un_placeholder():
    """Le plan porte des URL réelles (`/formulaire/78`), l'annuaire des gabarits."""
    assert domain_model.formulaires_requis(MODELE, ["http://localhost:10017/formulaire/78"])


def test_formulaires_requis_ignore_les_pages_sans_champ_requis():
    assert domain_model.formulaires_requis(MODELE, ["/myservices"]) == []


# ── L'injection dans le message initial ───────────────────────────────────────

def test_la_contrainte_nomme_TOUS_les_champs_requis_et_leurs_options():
    msg = prompt.build_initial_message(_plan(), MODELE)

    assert "## Champs OBLIGATOIRES" in msg
    for champ in REQUIS:
        assert f"`{champ}`" in msg, f"{champ} doit être nommé dans la contrainte"
    # Les valeurs d'un select sont données : l'agent n'a plus à les inventer (motif 0019).
    assert "nouvel_entrant" in msg and "remplacement_materiel" in msg


def test_la_contrainte_est_IMPERATIVE_et_exige_une_soumission_explicite():
    """Ferme, pas suggestive — c'est tout l'objet du correctif. Et elle dit explicitement que
    « j'attends la soumission » n'envoie rien (la cause prouvée du ticket jamais créé)."""
    msg = prompt.build_initial_message(_plan(), MODELE)

    # Formulation ajustée le 2026-07-21 (« … DOIT remplir TOUS ceux-ci ») quand la contrainte a
    # commencé à distinguer champs saisissables et champs cachés. Ce test garde le caractère
    # IMPÉRATIF, pas une tournure exacte : on assertit donc les deux mots qui le portent.
    assert "DOIT remplir TOUS" in msg
    assert "Soumettre EXPLICITEMENT" in msg
    assert "n'envoie RIEN" in msg, "l'attente passive doit être dénoncée nommément"


def test_la_contrainte_porte_la_DATE_du_modele():
    """Le modèle est une photo : un avertissement daté est vérifiable, un non daté est une
    affirmation (borne du principe 2)."""
    assert "2026-07-17" in prompt.build_initial_message(_plan(), MODELE)


def test_la_contrainte_prevoit_l_exception_du_scenario_d_ERREUR():
    """Sans cette exception, la contrainte contredirait la couverture minimale du prompt système
    (« [Erreur] : champ requis manquant ») — l'agent recevrait deux ordres opposés."""
    msg = prompt.build_initial_message(_plan(), MODELE)

    assert "[ERREUR]" in msg and "omission" in msg


# ── Le silence, quand on ne sait pas ──────────────────────────────────────────

def test_aucune_contrainte_inventee_sans_modele():
    """Sans annuaire, le message est celui d'avant : on n'invente pas d'obligation."""
    assert "## Champs OBLIGATOIRES" not in prompt.build_initial_message(_plan(), None)


def test_aucune_contrainte_si_la_route_du_plan_n_est_pas_au_modele():
    msg = prompt.build_initial_message(_plan(routes=("/une/route/inconnue",)), MODELE)

    assert "## Champs OBLIGATOIRES" not in msg
