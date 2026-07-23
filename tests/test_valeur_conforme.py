"""Le verrou 2a du §2bis — le déterministe fabrique-t-il une valeur RECEVABLE ?

⚠️ **Ce test est le pari, rendu falsifiable.** La re-mesure du 2026-07-22 a prouvé que donner les
contraintes au LLM ne suffit pas (il écrit « FAC-TEST-001 » dans un champ `\\d{7}`). Le pari du
résolveur : une couche déterministe qui LIT l'annuaire produira, elle, une valeur conforme. Si ce
pari est faux, il tombe ICI — sur le corpus des 21 règles RÉELLES du portail — avant qu'on engage
le gros du chantier. C'est le verrou de dé-risquage : pur, sans LLM, ~0 €.

La garde centrale (`test_toute_regle_reelle_a_motif_produit_une_valeur_recevable`) rejoue chaque
motif que le crawl a capté et exige que la valeur produite le satisfasse. Elle ÉCHOUERAIT si le
générateur régressait — c'est ce qui en fait une garde, pas une description.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from testpilot.generation import domain_model
from testpilot.generation import valeur_conforme as vc

ANNUAIRE_REEL = Path("data/domain/projet-1.json")


# ── Le générateur de motif, sur la famille RÉELLE mesurée ─────────────────────

@pytest.mark.parametrize("motif", [
    r"\d{7}",                     # code_client1, numero_cheque, compte_client…
    r"\d{9}",                     # siren
    r"\d{6}",                     # numero_fournisseur, compte_fournisseur
    r"[A-Za-z0-9]{8,11}",         # bic_client
    r"[a-zA-Z0-9]{1,10}",         # numero_facture_annulation
    r"\d{9} \d{5}",               # siret_fournisseur (14 chiffres + espace)
    r"\+?[0-9\s\-\(\)]{10,}",     # phone_contact_comptable
])
def test_le_generateur_satisfait_chaque_motif_reel(motif):
    """Chaque motif du portail doit produire une valeur que `re.fullmatch` accepte —
    c'est la définition même de « recevable par le navigateur »."""
    valeur = vc.valeur_pour_motif(motif)
    assert re.fullmatch(motif, valeur), f"{valeur!r} ne satisfait pas {motif!r}"


def test_un_motif_hors_famille_LEVE_plutot_que_mentir():
    """Le générateur ne couvre pas tout. Sur ce qu'il ne sait pas faire, il lève —
    plutôt que rendre une valeur qui serait refusée en silence à l'exécution."""
    with pytest.raises(vc.ValeurNonSynthetisable):
        vc.valeur_pour_motif(r"chat|chien")  # alternation : hors périmètre du générateur


def test_la_valeur_qui_a_produit_le_FAUX_verdict_est_bien_rejetee_par_le_motif():
    """Le contrôle négatif, sur le cas exact mesuré. Si `\\d{7}` acceptait « FAC-TEST-001 »,
    tout ce module serait inutile."""
    assert not re.fullmatch(r"\d{7}", "FAC-TEST-001")
    assert re.fullmatch(r"\d{7}", vc.valeur_pour({"type": "text", "contraintes": {"pattern": r"\d{7}"}}))


# ── `valeur_pour` — chaque famille de champ ──────────────────────────────────

def test_une_liste_d_options_ne_s_invente_pas():
    """0019 : on prend une option RÉELLE, jamais une valeur devinée."""
    assert vc.valeur_pour({"type": "select", "options": ["particulier", "entreprise"]}) == "particulier"


def test_un_champ_fichier_rend_un_nom_de_fichier():
    assert vc.valeur_pour({"type": "file"}).endswith(".pdf")


def test_une_case_a_cocher_requise_recoit_oui():
    """Cas 52 : `fill_field` DÉcoche pour toute valeur ≠ « oui/true/1 ». Une case obligatoire
    doit donc recevoir « oui », sinon la soumission reste bloquée."""
    assert vc.valeur_pour({"type": "checkbox"}) == "oui"


def test_un_select_SANS_option_leve_au_lieu_d_inventer():
    """Correctif B (rejeu 2026-07-23, `agence`) : un `<select>` sans option sélectionnable ne doit
    PAS recevoir un texte inventé (« TestPilot ») — ça produisait une `InvalidOptionValueError`
    trompeuse. On lève clairement : rien de déterministe à mettre."""
    with pytest.raises(vc.ValeurNonSynthetisable, match="option"):
        vc.valeur_pour({"tag": "select", "type": "select", "options": [""]})
    with pytest.raises(vc.ValeurNonSynthetisable):
        vc.valeur_pour({"tag": "select", "options": []})


def test_la_regle_lisible_sans_motif_donne_le_bon_nombre_de_chiffres():
    """`numero_facture1` sur `/demande_avoir` : pas de `pattern` HTML, mais le title dit
    « groupes de sept chiffres ». Le seul crochet quand la règle est en JavaScript."""
    v = vc.valeur_pour({"type": "text",
                        "contraintes": {"regle_lisible": "Veuillez saisir des groupes de sept chiffres."}})
    assert re.fullmatch(r"\d{7}", v), f"{v!r} n'est pas un code à 7 chiffres"


def test_un_nombre_respecte_le_minimum_et_le_pas_decimal():
    v = vc.valeur_pour({"type": "number", "contraintes": {"min": "0", "step": "0.01"}})
    assert float(v) >= 0 and "." in v


def test_une_date_future_est_bien_dans_le_futur():
    """« La date doit être ultérieure à la date actuelle » → une date STRICTEMENT après aujourd'hui."""
    v = vc.valeur_pour({"type": "date",
                        "contraintes": {"regle_lisible": "La date doit être ultérieure à la date actuelle."}})
    assert date.fromisoformat(v) > date.today()


def test_une_date_sans_direction_vaut_aujourd_hui():
    v = vc.valeur_pour({"type": "date", "contraintes": {}})
    assert date.fromisoformat(v) == date.today()


def test_un_iban_est_reconnu_a_sa_regle():
    v = vc.valeur_pour({"type": "text",
                        "contraintes": {"regle_lisible": "Veuillez saisir un IBAN valide au format FRXX XXXX"}})
    assert v.startswith("FR") and len(v) == 27


def test_la_longueur_maximale_est_respectee():
    """`denomination` : maxlength 25. Une valeur plus longue serait tronquée par le navigateur."""
    v = vc.valeur_pour({"type": "text", "contraintes": {"maxlength": "25"}})
    assert len(v) <= 25


def test_une_borne_placeholder_ne_fait_pas_planter():
    """`max="date_now"` (placeholder de gabarit qui a fui) ne doit pas casser la synthèse."""
    v = vc.valeur_pour({"type": "date", "contraintes": {"max": "date_now"}})
    assert date.fromisoformat(v)  # une date valide, la borne parasite ignorée


# ── LE CORPUS RÉEL — la garde qui prouve le pari ─────────────────────────────

def _champs_reels_avec_contraintes():
    """Tous les champs requis du portail, dans la forme EXACTE que le résolveur lira
    (`formulaires_requis`), filtrés à ceux qui portent une contrainte."""
    if not ANNUAIRE_REEL.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(ANNUAIRE_REEL.read_text(encoding="utf-8"))
    routes = list(modele.get("pages", {}).keys())
    champs = [c for form in domain_model.formulaires_requis(modele, routes)
              for c in form["requis"] if c.get("contraintes")]
    if not champs:
        pytest.skip("aucun champ contraint dans l'annuaire")
    return champs


def test_toute_regle_reelle_a_motif_produit_une_valeur_recevable():
    """⚠️ LA GARDE CENTRALE. Pour chaque champ RÉEL portant un `pattern`, la valeur synthétisée
    doit satisfaire ce motif. C'est « le déterministe produit une donnée que le navigateur
    accepte », vérifié sur le portail réel, pas sur des exemples choisis."""
    a_motif = [c for c in _champs_reels_avec_contraintes() if c["contraintes"].get("pattern")]
    assert a_motif, "aucun motif dans l'annuaire — le crawl a-t-il régressé ?"
    for champ in a_motif:
        motif = champ["contraintes"]["pattern"]
        valeur = vc.valeur_pour(champ)
        assert re.fullmatch(motif, valeur), (
            f"champ {champ['name']!r} : valeur {valeur!r} refusée par son motif {motif!r}")


def test_aucun_champ_contraint_reel_ne_fait_lever_le_resolveur():
    """Au-delà des motifs : AUCUN champ contraint réel (nombre, date, longueur, règle lisible…)
    ne doit faire échouer la synthèse. Un `raise` ici = un champ qu'on ne sait pas remplir =
    une erreur technique à l'exécution."""
    for champ in _champs_reels_avec_contraintes():
        try:
            assert vc.valeur_pour(champ) != "" or champ.get("type") == "file"
        except vc.ValeurNonSynthetisable as exc:
            pytest.fail(f"champ {champ['name']!r} ({champ.get('type')}) non synthétisable : {exc}")
