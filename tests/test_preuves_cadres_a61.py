"""Étape 2 du plan unique (A61, porteur 2026-10-20) — deux autres fausses alertes « champ sans preuve » :

1. une version jamais instrumentée (`''`) devenait « instrumentée, rien vu » (`'[]'`) à sa première copie ;
6. un champ dans un cadre (iframe) n'était jamais relevé : la saisie « dans le cadre "X" » n'avait jamais de preuve.

Le contrôle d'un cadre est plus STRICT qu'avant : un champ vu dans la page principale ne prouve pas une saisie dans un
cadre, et inversement.
"""

from __future__ import annotations

from datetime import datetime, timezone

from testpilot.connectors._web_helpers import extract_form
from testpilot.generation.evidence import contextual_warnings, record_observation
from testpilot.generation.provenance import revision_metadata
from testpilot.generation.tools import ToolContext


class _El:
    def __init__(self, **attrs):
        self.attrs = attrs

    def get_attribute(self, nom):
        return self.attrs.get(nom)


class _Document:
    def __init__(self, champs):
        self.champs = [_El(name=n) for n in champs]

    def query_selector_all(self, _selecteur):
        return self.champs

    def query_selector(self, _selecteur):
        return None


class _Cadre(_Document):
    def __init__(self, champs, parent, **balise):
        super().__init__(champs)
        self.parent_frame = parent
        self.balise = _El(**balise)

    def frame_element(self):
        return self.balise


class _Page(_Document):
    def __init__(self, champs, cadres):
        super().__init__(champs)
        self.main_frame = object()
        self.frames = [self.main_frame] + [_Cadre(c, self.main_frame, **b) for c, b in cadres]
        self.url = "http://127.0.0.1:8095/paiement"


def test_une_version_jamais_instrumentee_le_reste_a_la_copie():
    assert revision_metadata({"id": 1, "observation_evidence": ""})["observation_evidence"] == ""
    assert revision_metadata({"id": 1})["observation_evidence"] == ""
    assert revision_metadata({"id": 1, "observation_evidence": "[]"})["observation_evidence"] == "[]", \
        "instrumentée sans rien voir : le contrôle s'applique toujours"


def test_les_champs_d_un_cadre_enfant_sont_releves_avec_son_nom():
    page = _Page(["email"], [(["carte"], {"name": "paiement", "id": "cadre-1"})])
    champs = {f["name"]: f.get("cadre") for f in extract_form(page)["fields"]}
    assert champs == {"email": None, "carte": ["paiement", "cadre-1"]}


def test_un_cadre_petit_enfant_n_est_pas_releve():
    """L'exécution (`_base_helpers.cadre`) ne cherche que les iframes de la page : un cadre dans un cadre n'est pas atteint."""
    page = _Page([], [])
    intermediaire = _Cadre(["x"], page.main_frame, name="externe")
    page.frames += [intermediaire, _Cadre(["profond"], intermediaire, name="interne")]
    assert {f["name"] for f in extract_form(page)["fields"]} == {"x"}


def _avis(ligne, champs):
    ctx = ToolContext("paiement", "/tmp", target_sha256="c1")
    record_observation(ctx, source="ui", resource="http://127.0.0.1:8095/paiement",
                       fields=[{**f, "visible": True} for f in champs])
    feature = f'# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit j\'ouvre la page "/paiement"\n    {ligne}\n'
    return contextual_warnings(feature, ctx.observations, target_sha256="c1", base_url="http://127.0.0.1:8095",
                               reference_time=datetime.now(timezone.utc))


def test_falsifiable_une_saisie_dans_un_cadre_se_prouve_dans_ce_cadre():
    ligne = 'Quand dans le cadre "paiement", je renseigne le champ "carte" avec la valeur "4242"'
    assert _avis(ligne, [{"name": "carte", "cadre": ["paiement", "cadre-1"]}]) == []
    assert _avis(ligne, [{"name": "carte", "cadre": ["autre"]}]), "vu dans un AUTRE cadre"
    assert _avis(ligne, [{"name": "carte"}]), "vu dans la page principale : l'exécution cherchera dans le cadre"


def test_falsifiable_une_saisie_hors_cadre_ne_se_prouve_pas_par_un_champ_de_cadre():
    ligne = 'Quand je renseigne le champ "carte" avec la valeur "4242"'
    assert _avis(ligne, [{"name": "carte"}]) == []
    assert _avis(ligne, [{"name": "carte", "cadre": ["paiement"]}]), "seulement dans un cadre : introuvable à l'exécution"
