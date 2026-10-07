"""Q3-a — définitions d'outils envoyées à l'API : mode strict, `input_examples`, non-régression.

Ce que l'on prouve, SANS appel réseau :
1. interrupteurs éteints (défaut), ce que l'API reçoit est IDENTIQUE, octet pour octet, à ce qui était
   envoyé avant Q3-a (témoin figé : `tests/fixtures/tools_definitions_avant_q3a.json`, produit depuis
   le commit 2b46988 avant toute modification) — et allumés, ça change (la garde n'est pas vide) ;
2. le schéma « compatible API » respecte les règles de la doc officielle (aucun mot-clé non supporté,
   `additionalProperties: false`, tout `required`, `minItems` ≤ 1) — et le vérificateur sait REFUSER
   le schéma local (sinon il ne prouverait rien) ;
3. la validation LOCALE garde le schéma complet : le mode strict ne l'affaiblit pas ;
4. les `input_examples` sont valides contre le schéma local ET le schéma API, et compilent contre le
   vrai catalogue de steps ;
5. `call_with_tools` et `run_loop` transmettent ces définitions telles quelles.

⚠️ Ce que ces tests NE prouvent PAS : que l'API Anthropic ACCEPTE ces schémas en strict (grammaire
compilée côté serveur). Cela ne se vérifie que par un appel réel, à faire avec l'accord du porteur.
"""

from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot.generation import steps_library
from testpilot.generation.interrupteurs import (
    ENV_PROMPT_HYPOTHESES,
    ENV_TOOLS_DESCRIPTIONS_V2,
    ENV_TOOLS_STRICT,
)
from testpilot.generation.provenance import fingerprint
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState
from testpilot.generation.technical_plan import (
    HYPOTHESES_CLE,
    INPUT_EXAMPLES,
    SCHEMA,
    write_test_plan,
)
from testpilot.generation.tool_validation import validate_tool_input
from testpilot.generation.tools import TOOLS_DEFINITIONS, ToolContext, dispatch
from testpilot.generation.tools.api_definitions import (
    OUTILS_STRICTS,
    exemples_pour,
    schema_compatible_api,
    tools_for_api,
)
from testpilot.llm.adapter import LLMAdapter, LLMResponse

_TEMOIN = Path(__file__).parent / "fixtures" / "tools_definitions_avant_q3a.json"
_TOUS_ETEINTS: dict[str, str] = {}
_STRICT = {ENV_TOOLS_STRICT: "1"}
_COMBINAISONS = [dict(zip((ENV_TOOLS_STRICT, ENV_PROMPT_HYPOTHESES, ENV_TOOLS_DESCRIPTIONS_V2),
                          ("1" if b else "0" for b in bits), strict=True))
                 for bits in itertools.product((False, True), repeat=3)]


def _json(outils) -> str:
    return json.dumps(outils, ensure_ascii=False)


def _outil(outils, nom):
    return next(o for o in outils if o["name"] == nom)


# ── 1. Non-régression octet pour octet ───────────────────────────────────────────────────────

def test_interrupteurs_eteints_rien_ne_change_octet_pour_octet():
    assert _json(tools_for_api(_TOUS_ETEINTS)) == _TEMOIN.read_text(encoding="utf-8")


def test_sans_variable_d_environnement_le_defaut_est_eteint(monkeypatch):
    for nom in (ENV_TOOLS_STRICT, ENV_PROMPT_HYPOTHESES, ENV_TOOLS_DESCRIPTIONS_V2):
        monkeypatch.delenv(nom, raising=False)
    assert _json(tools_for_api()) == _TEMOIN.read_text(encoding="utf-8")


def test_l_empreinte_de_provenance_est_inchangee_interrupteurs_eteints():
    assert fingerprint(tools_for_api(_TOUS_ETEINTS)) == fingerprint(
        json.loads(_TEMOIN.read_text(encoding="utf-8")))


@pytest.mark.parametrize("nom", [ENV_TOOLS_STRICT, ENV_PROMPT_HYPOTHESES, ENV_TOOLS_DESCRIPTIONS_V2])
def test_chaque_interrupteur_change_ce_que_l_api_recoit(nom):
    """Sens inverse : la garde d'identité ci-dessus n'est pas vide, chaque interrupteur agit."""
    assert _json(tools_for_api({nom: "1"})) != _TEMOIN.read_text(encoding="utf-8")
    assert fingerprint(tools_for_api({nom: "1"})) != fingerprint(tools_for_api(_TOUS_ETEINTS))


def test_le_champ_d_hypotheses_n_est_expose_que_si_son_interrupteur_est_allume():
    assert HYPOTHESES_CLE not in _outil(tools_for_api(_TOUS_ETEINTS),
                                        "write_test_plan")["input_schema"]["properties"]
    assert HYPOTHESES_CLE in _outil(tools_for_api({ENV_PROMPT_HYPOTHESES: "1"}),
                                    "write_test_plan")["input_schema"]["properties"]
    # Et le schéma local, lui, le connaît toujours (la validation l'accepte dans tous les cas).
    assert HYPOTHESES_CLE in SCHEMA["properties"]


def test_les_descriptions_v2_ne_sont_servies_que_si_leur_interrupteur_est_allume(monkeypatch):
    monkeypatch.delenv(ENV_TOOLS_DESCRIPTIONS_V2, raising=False)
    eteint = tools_for_api()
    monkeypatch.setenv(ENV_TOOLS_DESCRIPTIONS_V2, "1")
    allume = tools_for_api()
    assert [o["name"] for o in allume] == [o["name"] for o in eteint]          # mêmes noms, même ordre
    assert all("quand" in o["description"].lower() for o in allume)
    assert not any("quand l'utiliser" in o["description"].lower() for o in eteint)


def test_tools_for_api_ne_mute_jamais_les_definitions_locales():
    avant = copy.deepcopy(TOOLS_DEFINITIONS)
    for env in _COMBINAISONS:
        tools_for_api(env)
    assert TOOLS_DEFINITIONS == avant


# ── 2. Le schéma « compatible API » respecte la doc officielle ───────────────────────────────

_INTERDITS = ("minLength", "maxLength", "minimum", "maximum", "multipleOf", "maxItems")


def _violations(noeud: dict, chemin: str = "input") -> list[str]:
    """Écarts entre un schéma et ce que le mode strict accepte (doc « Structured outputs »)."""
    fautes = [f"{chemin}.{mot}" for mot in _INTERDITS if mot in noeud]
    if noeud.get("minItems", 0) > 1:
        fautes.append(f"{chemin}.minItems={noeud['minItems']}")
    if noeud.get("type") == "object":
        proprietes = noeud.get("properties") or {}
        if not proprietes:
            fautes.append(f"{chemin} : objet libre")
        if noeud.get("additionalProperties") is not False:
            fautes.append(f"{chemin}.additionalProperties")
        if set(noeud.get("required", [])) != set(proprietes):
            fautes.append(f"{chemin}.required incomplet")
        for nom, sous in proprietes.items():
            fautes += _violations(sous, f"{chemin}.{nom}")
    if isinstance(noeud.get("items"), dict):
        fautes += _violations(noeud["items"], f"{chemin}[]")
    return fautes


def test_le_verificateur_refuse_le_schema_local(monkeypatch):
    """Falsifiabilité du vérificateur : le schéma local de `write_test_plan` porte `minLength` et un
    `required` incomplet — s'il ne les voyait pas, les tests ci-dessous passeraient à vide."""
    local = _outil(TOOLS_DEFINITIONS, "write_test_plan")["input_schema"]
    fautes = _violations(local)
    assert any("minLength" in f for f in fautes) and any("required incomplet" in f for f in fautes)


@pytest.mark.parametrize("env", _COMBINAISONS, ids=lambda e: "".join(sorted(k[-6:] + v for k, v in e.items())))
def test_les_outils_stricts_ont_un_schema_conforme_dans_toutes_les_combinaisons(env):
    outils = tools_for_api({**env, ENV_TOOLS_STRICT: "1"})
    stricts = [o["name"] for o in outils if o.get("strict")]
    assert set(stricts) == set(OUTILS_STRICTS)
    for nom in OUTILS_STRICTS:
        outil = _outil(outils, nom)
        assert outil["strict"] is True
        assert _violations(outil["input_schema"]) == [], nom


def test_seuls_les_outils_critiques_sont_stricts_les_autres_sont_inchanges():
    outils = tools_for_api(_STRICT)
    for outil in outils:
        if outil["name"] in OUTILS_STRICTS:
            continue
        assert "strict" not in outil and "input_examples" not in outil
        assert outil == _outil(TOOLS_DEFINITIONS, outil["name"]), outil["name"]
    assert {o["name"] for o in outils} == {o["name"] for o in TOOLS_DEFINITIONS}


def test_les_trois_outils_critiques_sont_bien_stricts():
    assert set(OUTILS_STRICTS) >= {"write_test_plan", "write_feature_file", "write_steps_file"}


def test_les_limites_de_la_doc_sont_respectees():
    """20 outils stricts, 24 paramètres optionnels, 16 unions par requête (doc, 2026-10-07)."""
    outils = tools_for_api({ENV_TOOLS_STRICT: "1", ENV_PROMPT_HYPOTHESES: "1"})
    stricts = [o for o in outils if o.get("strict")]
    assert len(stricts) <= 20

    def optionnels(noeud):
        total = 0
        if noeud.get("type") == "object":
            total += len(set(noeud.get("properties", {})) - set(noeud.get("required", [])))
            total += sum(optionnels(s) for s in noeud.get("properties", {}).values())
        if isinstance(noeud.get("items"), dict):
            total += optionnels(noeud["items"])
        return total

    def unions(noeud):
        total = 1 if ("anyOf" in noeud or isinstance(noeud.get("type"), list)) else 0
        total += sum(unions(s) for s in noeud.get("properties", {}).values())
        if isinstance(noeud.get("items"), dict):
            total += unions(noeud["items"])
        return total

    assert sum(optionnels(o["input_schema"]) for o in stricts) <= 24
    assert sum(unions(o["input_schema"]) for o in stricts) <= 16


def test_les_contraintes_retirees_sont_rappelees_a_l_agent():
    """L'API ne garantit plus `minLength`/`maxItems` : on les DIT dans la description (comme le fait
    le SDK officiel) — la validation locale, elle, les impose."""
    schema = _outil(tools_for_api({ENV_TOOLS_STRICT: "1", ENV_PROMPT_HYPOTHESES: "1"}),
                    "write_test_plan")["input_schema"]
    assert "non vide" in schema["properties"]["title"]["description"]
    hyp = schema["properties"][HYPOTHESES_CLE]
    assert "5 éléments au plus" in hyp["description"]
    assert "200 caractères au plus" in hyp["items"]["description"]
    assert schema["properties"]["scenarios"]["minItems"] == 1       # conservé : l'API l'accepte (0/1)


def test_un_objet_libre_ne_peut_pas_etre_rendu_strict():
    with pytest.raises(ValueError, match="incompatible avec le mode strict"):
        schema_compatible_api({"type": "object", "properties": {"x": {"type": "object"}}})
    # C'est précisément le cas de `attempt_form_submission.field_values` : hors liste d'outils stricts.
    libre = _outil(TOOLS_DEFINITIONS, "attempt_form_submission")["input_schema"]
    with pytest.raises(ValueError):
        schema_compatible_api(libre)
    assert "attempt_form_submission" not in OUTILS_STRICTS


def test_schema_compatible_api_est_pur():
    local = _outil(TOOLS_DEFINITIONS, "write_test_plan")["input_schema"]
    avant = copy.deepcopy(local)
    api = schema_compatible_api(local)
    assert local == avant and api is not local
    assert api != local


# ── 3. La validation locale garde le schéma COMPLET ──────────────────────────────────────────

def test_le_mode_strict_n_affaiblit_pas_la_validation_locale(tmp_path, monkeypatch):
    """Le schéma API n'a plus `minLength` : un titre vide serait accepté par la grammaire de l'API.
    C'est `dispatch`, sur le schéma local, qui le refuse — mode strict allumé ou non."""
    monkeypatch.setenv(ENV_TOOLS_STRICT, "1")
    api = _outil(tools_for_api(), "write_test_plan")["input_schema"]
    assert "minLength" not in json.dumps(api)                    # l'API ne le garantit plus…
    plan = {"title": "  ", "scenarios": [{"name": "s", "requirement_ids": ["r"], "steps": [
        {"keyword": "Soit", "text": "x", "evidence_ids": []}]}]}
    resultat = dispatch("write_test_plan", plan, ToolContext("cas", tmp_path))
    assert not resultat.ok and "texte vide interdit" in resultat.observation   # …le local, si


# ── 4. Les input_examples ────────────────────────────────────────────────────────────────────

def _catalogue_ctx(tmp_path, exemple):
    ctx = ToolContext("cas", tmp_path)
    identifiants = {i for s in exemple["scenarios"] for i in s["requirement_ids"]}
    ctx.requirements = {i: f"exigence {i}" for i in identifiants}
    ctx.shared_steps = steps_library.catalogue()
    ctx.observations = [{"id": "observation-1"}]
    return ctx


def test_il_y_a_deux_exemples_un_nominal_un_avec_attente_apres_un_alors():
    assert len(INPUT_EXAMPLES) == 2
    etapes = [(e["keyword"], e["text"]) for e in INPUT_EXAMPLES[1]["scenarios"][0]["steps"]]
    indice_attente = etapes.index(("Et", "j'attends la soumission du formulaire"))
    assert any(mot == "Alors" for mot, _ in etapes[:indice_attente]), (
        "l'attente doit suivre un `Alors` qui constate")


@pytest.mark.parametrize("env", _COMBINAISONS, ids=lambda e: "".join(sorted(k[-6:] + v for k, v in e.items())))
def test_chaque_exemple_est_valide_contre_le_schema_local_et_le_schema_api(env):
    outil = _outil(tools_for_api({**env, ENV_TOOLS_STRICT: "1"}), "write_test_plan")
    local = _outil(TOOLS_DEFINITIONS, "write_test_plan")["input_schema"]
    assert len(outil["input_examples"]) == 2
    for exemple in outil["input_examples"]:
        assert validate_tool_input(exemple, outil["input_schema"]) == "", exemple
        assert validate_tool_input(exemple, local) == "", exemple


def test_un_exemple_non_filtre_serait_refuse_par_le_schema_sans_hypotheses():
    """Falsifiabilité du filtre `exemples_pour` : l'exemple brut (avec `hypotheses_non_verifiees`) est
    INVALIDE contre un schéma qui n'expose pas le champ — l'API répondrait 400. Le filtre est donc
    nécessaire, et il suffit."""
    api = _outil(tools_for_api(_STRICT), "write_test_plan")["input_schema"]
    assert HYPOTHESES_CLE not in api["properties"]
    assert "propriétés inconnues" in validate_tool_input(INPUT_EXAMPLES[1], api)
    assert all(validate_tool_input(e, api) == "" for e in exemples_pour(api))


def test_les_exemples_ne_partent_qu_avec_le_mode_strict():
    for env in ({}, {ENV_PROMPT_HYPOTHESES: "1"}, {ENV_TOOLS_DESCRIPTIONS_V2: "1"}):
        assert all("input_examples" not in o for o in tools_for_api(env)), env
    seuls = [o["name"] for o in tools_for_api(_STRICT) if "input_examples" in o]
    assert seuls == ["write_test_plan"]


@pytest.mark.parametrize("indice", [0, 1])
def test_chaque_exemple_se_compile_contre_le_vrai_catalogue(tmp_path, indice):
    exemple = copy.deepcopy(INPUT_EXAMPLES[indice])
    resultat = write_test_plan(_catalogue_ctx(tmp_path, exemple), exemple)
    assert resultat.ok, resultat.observation
    gherkin = (tmp_path / "cas.feature").read_text(encoding="utf-8")
    assert "Alors" in gherkin


def test_l_exemple_est_refuse_si_on_le_degrade(tmp_path):
    """Falsifiabilité : un exemple faux N'EST PAS compilé — le test ci-dessus n'est pas tautologique."""
    inconnu = copy.deepcopy(INPUT_EXAMPLES[0])
    inconnu["scenarios"][0]["steps"][1]["text"] = "une action absente du catalogue"
    assert not write_test_plan(_catalogue_ctx(tmp_path, inconnu), inconnu).ok

    seulement_attente = copy.deepcopy(INPUT_EXAMPLES[1])
    seulement_attente["scenarios"][0]["steps"] = [
        s for s in seulement_attente["scenarios"][0]["steps"]
        if not (s["keyword"] == "Alors" and "Merci" in s["text"])]
    resultat = write_test_plan(_catalogue_ctx(tmp_path, seulement_attente), seulement_attente)
    assert not resultat.ok and "sans assertion" in resultat.observation


# ── 5. Le transport : call_with_tools et run_loop ────────────────────────────────────────────

class _FauxMessages:
    def __init__(self):
        self.recu = {}

    def create(self, **kwargs):
        self.recu = kwargs
        usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_creation_input_tokens=0,
                                cache_read_input_tokens=0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")],
                               stop_reason="end_turn", usage=usage)


def test_call_with_tools_transmet_les_definitions_strictes_sans_les_modifier():
    adaptateur = LLMAdapter()
    faux = SimpleNamespace(messages=_FauxMessages())
    adaptateur._client = faux
    outils = tools_for_api({**_STRICT, ENV_PROMPT_HYPOTHESES: "1", ENV_TOOLS_DESCRIPTIONS_V2: "1"})
    envoyes = copy.deepcopy(outils)
    reponse, _brut = adaptateur.call_with_tools(
        system_prompt="s", messages=[{"role": "user", "content": "x"}], tools=outils)
    assert isinstance(reponse, LLMResponse) and reponse.text == "ok"
    assert faux.messages.recu["tools"] == envoyes
    assert faux.messages.recu["tools"][-1]["strict"] is True
    assert "input_examples" in faux.messages.recu["tools"][-1]


def test_run_loop_envoie_tools_for_api_et_pas_les_definitions_locales(monkeypatch):
    recu = {}

    class _LLM:
        def call_with_tools(self, **kwargs):
            recu.update(kwargs)
            return LLMResponse(stop_reason="end_turn", raw_stop_reason="end_turn"), None

    def lancer():
        run_loop(llm=_LLM(), system_prompt="s", state=AgentState(module_name="m", messages=[]),
                 ctx=None, dry_runner=None, cost_tracker=None, max_iterations=1, stall_limit=1)
        return recu["tools"]

    monkeypatch.delenv(ENV_TOOLS_STRICT, raising=False)
    monkeypatch.delenv(ENV_PROMPT_HYPOTHESES, raising=False)
    assert _json(lancer()) == _TEMOIN.read_text(encoding="utf-8")        # défaut : l'ancienne liste

    monkeypatch.setenv(ENV_TOOLS_STRICT, "1")
    assert _outil(lancer(), "write_test_plan")["strict"] is True          # allumé : la nouvelle
