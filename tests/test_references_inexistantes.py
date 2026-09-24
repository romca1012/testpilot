"""Lot 12, commit 3 (D11) — une référence PROUVÉE inexistante est refusée à l'écriture.

Bloquant seulement quand la source fait autorité (`name_search` RPC d'un champ relationnel Odoo ;
`<select>` entièrement relevé) ; détectif sinon (produits web). Jamais de refus pour une valeur créée
plus tôt dans le même scénario ou marquée « rendue unique pour cette tentative ».
"""
from __future__ import annotations

from pathlib import Path

from testpilot.connectors import _web_helpers, odoo
from testpilot.generation import references as refs
from testpilot.generation.smoke_check import (
    CATALOGUE_SOURCE_PREFIX,
    check_champs_existants,
    check_produits_observes,
    smoke_check,
)
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import inspect as inspect_tools
from testpilot.generation.tools import write as write_tools

PARTENAIRES = [(1, "Administrator"), (2, "Azure Interior"), (3, "Deco Addict"),
               (4, "Gemini Furniture"), (5, "Lumber Inc"), (6, "Wood Corner")]


def _name_search(modele, texte, limite):
    assert modele == "res.partner"
    if not texte:
        return PARTENAIRES[:limite]
    return [p for p in PARTENAIRES if texte.lower() in p[1].lower()][:limite]


def _feature(*etapes):
    return "# language: fr\nFonctionnalité: F\n  Scénario: S\n" + "".join(
        f"    {e}\n" for e in etapes)


# ── verifier_references ─────────────────────────────────────────────────────────────────────

def test_GARDE_un_partenaire_inexistant_est_refuse_avec_les_5_valeurs_les_plus_proches():
    feature = _feature('Quand je sélectionne "Azur Interiors" dans le champ "partner_id"')

    (refus,) = refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}}, _name_search)

    assert refus["champ"] == "partner_id" and refus["valeur"] == "Azur Interiors"
    assert len(refus["proches"]) == 5 and refus["proches"][0] == "Azure Interior"
    assert "name_search RPC" in refus["source"]
    assert "Azure Interior" in refs.message_refus([refus])


def test_un_partenaire_existant_n_est_jamais_refuse():
    feature = _feature('Quand je sélectionne "Deco Addict" dans le champ "partner_id"')
    assert refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}},
                                    _name_search) == []


def test_un_select_entierement_releve_fait_autorite_valeur_ou_libelle():
    options = {"types_demandes": {"nouvel_entrant", "Demande de nouvel entrant"}}
    bon = _feature('Et je sélectionne "Demande de nouvel entrant" dans le champ "types_demandes"')
    mauvais = _feature('Et je sélectionne "new" dans le champ "types_demandes"')

    assert refs.verifier_references(bon, options, {}, None) == []
    (refus,) = refs.verifier_references(mauvais, options, {}, None)
    assert refus["proches"][0] in options["types_demandes"]


def test_jamais_de_refus_pour_une_valeur_marquee_rendue_unique():
    feature = _feature('Quand je renseigne le champ "partner_id" avec la valeur "Neuf 123" rendue '
                       'unique pour cette tentative')
    assert refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}},
                                    _name_search) == []


def test_jamais_de_refus_pour_une_valeur_creee_plus_tot_dans_le_meme_scenario():
    feature = _feature('Quand je renseigne le champ "name" avec la valeur "Client Neuf"',
                       'Et je sélectionne "Client Neuf" dans le champ "partner_id"')
    assert refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}},
                                    _name_search) == []


def test_source_injoignable_ou_ambigue_ne_refuse_rien():
    feature = _feature('Quand je sélectionne "Inconnu" dans le champ "partner_id"')

    def en_panne(*_a):
        raise RuntimeError("RPC perdu")

    assert refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}}, en_panne) == []
    assert refs.verifier_references(
        feature, {}, {"partner_id": {"res.partner", "res.users"}}, _name_search) == []
    assert refs.verifier_references(feature, {}, {"partner_id": {"res.partner"}}, None) == []
    assert refs.verifier_references(feature, {}, {}, _name_search) == []


# ── write_feature_file : refus bloquant ─────────────────────────────────────────────────────

class _Connecteur:
    def name_search(self, modele, texte, limite):
        return _name_search(modele, texte, limite)


def _ctx(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=_Connecteur())
    ctx.champs_relationnels["partner_id"] = {"res.partner"}
    return ctx


def test_write_feature_file_refuse_une_reference_inexistante_et_n_ecrit_rien(tmp_path):
    feature = _feature('Quand je sélectionne "Azur Interiors" dans le champ "partner_id"')

    resultat = write_tools.write_feature_file(_ctx(tmp_path), feature)

    assert resultat.ok is False and "REFERENCE_INEXISTANTE" in resultat.observation
    assert "Azure Interior" in resultat.observation
    assert not (tmp_path / "m.feature").exists()


def test_write_feature_file_accepte_une_reference_reelle(tmp_path):
    feature = _feature('Quand je sélectionne "Azure Interior" dans le champ "partner_id"')

    assert write_tools.write_feature_file(_ctx(tmp_path), feature).ok is True


# ── L'exploration alimente les sources qui font autorité ─────────────────────────────────────

def test_inspect_schema_retient_les_champs_relationnels(tmp_path):
    class _C:
        def get_schema(self, modele):
            return {"partner_id": {"type": "many2one", "relation": "res.partner"},
                    "name": {"type": "char"}}

    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=_C())
    inspect_tools.inspect_schema(ctx, "helpdesk.ticket")

    assert ctx.champs_relationnels == {"partner_id": {"res.partner"}}


def test_inspect_page_form_retient_les_selects_et_le_catalogue(tmp_path):
    class _C:
        def inspect_form(self, url):
            return {"url": url, "submission": {}, "liens": ["PC Portable Dell", "Écran 27 pouces"],
                    "fields": [{"name": "types_demandes", "tag": "select",
                                "options": [["a", "Option A"], ["b", "Option B"]]}]}

    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=_C())
    sortie = inspect_tools.inspect_page_form(ctx, "https://app.test/formulaire/1")

    assert ctx.options_select == {"types_demandes": {"a", "b", "Option A", "Option B"}}
    assert sortie.verified_fields[f"{CATALOGUE_SOURCE_PREFIX}https://app.test/formulaire/1"] == [
        "PC Portable Dell", "Écran 27 pouces"]
    assert "« PC Portable Dell »" in sortie.observation


def test_extract_form_releve_les_liens_visibles_et_ignore_un_retour_non_liste():
    class _Page:
        url = "https://app.test/"

        def __init__(self, liens):
            self._liens = liens

        def query_selector_all(self, _s):
            return []

        def query_selector(self, _s):
            return None

        def evaluate(self, _js):
            return self._liens

    assert _web_helpers.extract_form(_Page(["A", "B"]))["liens"] == ["A", "B"]
    assert _web_helpers.extract_form(_Page(object()))["liens"] == []


def test_odoo_name_search_delegue_au_rpc_natif():
    class _Modele:
        def name_search(self, name, operator, limit):
            assert (name, operator, limit) == ("azur", "ilike", 3)
            return [[2, "Azure Interior"]]

    connecteur = odoo.OdooConnector("https://app.test", "db", "u", "p")
    connecteur._client = type("C", (), {"env": {"res.partner": _Modele()}})()

    assert connecteur.name_search("res.partner", "azur", 3) == [(2, "Azure Interior")]


# ── Produits web : avis DÉTECTIF (jamais bloquant) ──────────────────────────────────────────

_PRODUIT = 'Quand je sélectionne le produit "PC Portable HP" dans la liste'


def test_un_produit_hallucine_est_signale_avec_les_elements_observes_les_plus_proches():
    verified = {f"{CATALOGUE_SOURCE_PREFIX}/shop": ["PC Portable Dell", "Écran 27 pouces"]}

    (avis,) = check_produits_observes(_feature(_PRODUIT), verified)

    assert avis["kind"] == "produit_non_observe" and "PC Portable Dell" in avis["message"]


def test_un_produit_observe_ne_declenche_rien():
    verified = {f"{CATALOGUE_SOURCE_PREFIX}/shop": ["PC Portable HP EliteBook"]}
    assert check_produits_observes(_feature(_PRODUIT), verified) == []


def test_sans_registre_silence_et_registre_vide_signale():
    assert check_produits_observes(_feature(_PRODUIT), None) == []
    (avis,) = check_produits_observes(_feature(_PRODUIT), {})
    assert "Aucune liste de produits n'a été observée" in avis["message"]


def test_le_catalogue_n_est_jamais_pris_pour_des_noms_de_champ_et_smoke_check_le_branche():
    verified = {f"{CATALOGUE_SOURCE_PREFIX}/shop": ["code_client1"]}
    feature = _feature('Et je renseigne le champ "code_client1" avec la valeur "x"')

    avis = check_champs_existants(feature, modele={}, verified_fields=verified)

    assert len(avis) == 1 and avis[0]["kind"] == "champ_inconnu"
    assert any(a["kind"] == "produit_non_observe"
               for a in smoke_check(_feature(_PRODUIT), verified_fields={}))


def test_le_kind_produit_non_observe_a_un_libelle_francais_a_l_ecran():
    vue = Path("frontend/src/components/ReviewGate.vue").read_text(encoding="utf-8")
    assert "produit_non_observe: 'donnée'" in vue
