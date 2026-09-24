"""Lot 12 (2026-09-24), commit 1 — la valeur RETENUE par un champ devient un fait structuré, la
sonde de saisie est branchée dans les connecteurs, et le masque devient visible au générateur.

Avant : « FAC-TEST-001 » → « 001 » n'existait que dans le TEXTE de `preuve` (inexploitable par
machine). Désormais `RefusMesure.valeur_retenue` → sidecar → `RegleApprise.valeur_retenue`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402
from testpilot.connectors import generic_web, odoo  # noqa: E402
from testpilot.generation import regles_apprises as ra  # noqa: E402
from testpilot.generation.evidence import record_observation  # noqa: E402
from testpilot.generation.tools import ToolContext  # noqa: E402


class _Champ:
    def __init__(self, retenu):
        self._retenu = retenu

    def evaluate(self, _js):
        return self._retenu


class _Page:
    url = "https://app.test/en/retenue_garantie/1"


def test_le_filtre_de_saisie_consigne_la_valeur_retenue_en_champ_structure():
    with pytest.raises(H.DonneeRefuseeError) as erreur:
        H._verifier_valeur_retenue(_Page(), _Champ("001"), "numero_facture1", "FAC-TEST-001")

    (refus,) = erreur.value.refus
    assert refus.valeur_retenue == "001"
    assert refus.valeur_refusee == "FAC-TEST-001"
    assert refus.type_contrainte == "filtre_saisie" and refus.valeur_contrainte == r"\d"


def test_la_valeur_retenue_survit_au_sidecar_puis_aux_regles_apprises(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path)
    with pytest.raises(H.DonneeRefuseeError) as erreur:
        H._verifier_valeur_retenue(_Page(), _Champ("001"), "numero_facture1", "FAC-TEST-001")
    mesures = [json.loads(json.dumps(m.__dict__)) for m in erreur.value.refus]

    assert ra.enregistrer(1, mesures) == 1

    (regle,) = ra.charger(1)
    assert regle.valeur_retenue == "001" and regle.valeur_refusee == "FAC-TEST-001"
    assert "valeur_retenue" not in regle.cle().__repr__(), "hors clé d'identité"


def test_une_ligne_ancienne_sans_valeur_retenue_reste_lisible(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path)
    ancienne = {"route": "/retenue_garantie/{id}", "champ": "numero_facture1",
                "type_contrainte": "filtre_saisie", "valeur_contrainte": r"\d",
                "valeur_refusee": "FAC-TEST-001", "origine": "filtre_saisie",
                "preuve": "le champ a retenu '001'", "v": 1, "mesure_le": "2026-08-07T00:00:00+00:00"}
    (tmp_path / "projet-1.jsonl").write_text(json.dumps(ancienne) + "\n", encoding="utf-8")

    (regle,) = ra.charger(1)

    assert regle.valeur_retenue == ""


def test_deux_mesures_du_meme_refus_gardent_la_valeur_retenue(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path)
    base = {"route": "/f/{id}", "champ": "c", "type_contrainte": "filtre_saisie",
            "valeur_contrainte": r"\d", "valeur_refusee": "AB-1", "origine": "filtre_saisie"}
    ra.enregistrer(1, [{**base, "valeur_retenue": "1"}])
    ra.enregistrer(1, [{**base, "valeur_retenue": ""}])

    (regle,) = ra.charger(1)

    assert regle.occurrences == 2 and regle.valeur_retenue == "1"


def test_la_liste_blanche_des_observations_transmet_les_attributs_de_masque():
    ctx = ToolContext(module_name="m", generated_dir=Path("."))
    champ = {"name": "tel", "type": "text", "minlength": "10", "inputmode": "numeric",
             "placeholder": "06 12 34 56 78", "title": "10 chiffres", "data_mask": "00 00 00 00 00",
             "inputmask": "'mask': '99 99'", "secret": "ne-doit-pas-passer"}

    record_observation(ctx, source="ui", resource="/f", fields=[champ])

    observe = ctx.observations[0]["fields"][0]
    for cle in ("minlength", "inputmode", "placeholder", "title", "data_mask", "inputmask"):
        assert observe[cle] == champ[cle]
    assert "secret" not in observe


class _PageConnecteur:
    url = "https://app.test/en/retenue_garantie/1"

    def goto(self, *_a, **_k):
        pass

    def wait_for_load_state(self, *_a, **_k):
        pass

    def wait_for_selector(self, *_a, **_k):
        pass


def _brancher(monkeypatch, module, appels):
    monkeypatch.setattr(module, "extract_form", lambda page: {"fields": [], "submission": {}})
    monkeypatch.setattr(module, "sonder_formulaire",
                        lambda page, url: appels.append(url) or {"statut": "ok", "champs": {}})


def test_le_connecteur_web_generique_branche_la_sonde_dans_son_inspection(monkeypatch):
    appels = []
    _brancher(monkeypatch, generic_web, appels)
    connecteur = generic_web.GenericWebConnector("https://app.test")
    monkeypatch.setattr(connecteur, "_ensure_page", lambda: _PageConnecteur())

    resultat = connecteur._inspect_sync("/retenue_garantie/1")

    assert resultat["sonde"] == {"statut": "ok", "champs": {}}
    assert appels == ["https://app.test/en/retenue_garantie/1"]


def test_odoo_sonde_un_formulaire_portail_mais_jamais_le_back_office(monkeypatch):
    appels = []
    _brancher(monkeypatch, odoo, appels)
    monkeypatch.setattr(odoo, "_extract_odoo_form_fields",
                        lambda page: {"fields": [], "submission": {}})
    connecteur = odoo.OdooConnector("https://app.test", "db", "u", "p")
    portail = _PageConnecteur()
    monkeypatch.setattr(connecteur, "_ensure_page", lambda: portail)

    assert "sonde" in connecteur._inspect_sync("/retenue_garantie/1")
    assert len(appels) == 1

    class _BackOffice(_PageConnecteur):
        url = "https://app.test/web#action=180&model=helpdesk.ticket&view_type=form"

    monkeypatch.setattr(connecteur, "_ensure_page", lambda: _BackOffice())
    resultat = connecteur._inspect_sync("/web#action=180&model=helpdesk.ticket&view_type=form")

    assert "sonde" not in resultat and len(appels) == 1, "aucune sonde sur le back-office"
