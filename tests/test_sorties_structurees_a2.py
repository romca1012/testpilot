"""Étape A2 du §2bis — sorties structurées, avec repli TRANSPARENT (zéro régression).

`call_json` demande à l'API un JSON conforme au schéma (`output_config.format`). Quand le modèle
— ou la version du SDK — ne le supporte pas, la requête est refusée et on retombe EXACTEMENT sur
le parsing tolérant d'avant. Ces gardes prouvent les deux chemins sans réseau réel.
"""

from __future__ import annotations

import json

from testpilot.generation.metier_writer import propose_metier
from testpilot.analysis.plan import TestPlan
from testpilot.llm.adapter import LLMAdapter


class _Usage:
    input_tokens = output_tokens = cache_creation_input_tokens = cache_read_input_tokens = 0


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.content = [_Block(text)]
        self.usage = _Usage()
        self.stop_reason = stop


class _FakeClient:
    """`messages.create` : refuse `output_config` si `structured_ok=False` (comme un modèle qui ne
    le supporte pas / un SDK trop ancien), réussit sinon. Trace les appels reçus."""

    def __init__(self, *, structured_ok, text):
        self.structured_ok = structured_ok
        self.text = text
        self.appels = []

    @property
    def messages(self):
        return self

    def create(self, **kw):
        self.appels.append("structured" if "output_config" in kw else "simple")
        if "output_config" in kw and not self.structured_ok:
            raise TypeError("output_config: unsupported parameter")
        return _Resp(self.text)


def _adaptateur(client):
    a = LLMAdapter()
    a._client = client  # court-circuite la création paresseuse
    return a


_JSON = json.dumps({"title": "Créer une demande", "preconditions": "être connecté",
                    "steps": ["Ouvrir le formulaire", "Saisir", "Envoyer"],
                    "expected_result": "la demande est créée", "angle": "nominal"})

_SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}},
           "required": ["title"], "additionalProperties": False}


def test_call_json_emprunte_la_voie_structuree_quand_elle_est_honoree():
    client = _FakeClient(structured_ok=True, text=_JSON)
    data = _adaptateur(client).call_json(user_content="x", schema=_SCHEMA)
    assert data["title"] == "Créer une demande"
    assert client.appels == ["structured"], "un seul appel, structuré, aucun repli"


def test_call_json_retombe_sur_le_parsing_tolerant_si_output_config_refuse():
    client = _FakeClient(structured_ok=False, text="Voici le JSON : " + _JSON + " (fin)")
    data = _adaptateur(client).call_json(user_content="x", schema=_SCHEMA)
    assert data["title"] == "Créer une demande", "le repli extrait quand même le JSON"
    assert client.appels == ["structured", "simple"], "tentative structurée PUIS repli"


def test_call_json_repli_rend_dict_vide_sans_json():
    client = _FakeClient(structured_ok=False, text="désolé, aucun JSON ici")
    assert _adaptateur(client).call_json(user_content="x", schema=_SCHEMA) == {}


def _plan():
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec="SPEC", entry_url="")


def test_propose_metier_passe_par_call_json_quand_disponible():
    """Le vrai bénéfice A2 : la passe métier fragile (regex + json.loads nu) emprunte la voie
    structurée. Un fake exposant `call_json` doit produire un document complet."""
    client = _FakeClient(structured_ok=True, text=_JSON)
    draft = propose_metier(_plan(), llm=_adaptateur(client))
    assert draft.complete
    assert draft.title == "Créer une demande"
    assert client.appels == ["structured"]
