"""Q3-a — descriptions d'outils V2 : qualité mesurable, schémas intacts, promesses tenues par le code.

La doc « Define tools » (relue le 2026-10-07) fait de la description le premier facteur de performance
d'un outil : quoi, quand l'utiliser, quand NE PAS l'utiliser, sens de chaque paramètre, limites, en 3-4
phrases au moins. Ces tests rendent ce standard VÉRIFIABLE, et lient chaque chiffre annoncé (plafonds,
refus) au code qui l'applique (principe 6) — une description qui promet ce que l'outil ne fait pas est
un « affiché ≠ réel » au niveau du prompt.
"""

from __future__ import annotations

import copy
import re

import pytest

from testpilot.generation.technical_plan import HYPOTHESES_CLE
from testpilot.generation.tools import TOOLS_DEFINITIONS, ToolContext, dispatch
from testpilot.generation.tools.descriptions_v2 import (
    DESCRIPTIONS_V2,
    PARAMETRES_V2,
    appliquer_v2,
)

_NOMS = [t["name"] for t in TOOLS_DEFINITIONS]
_LONGUEUR_MIN = 250
_PHRASES_MIN = 3


def _proprietes(schema: dict, chemin: str = ""):
    """(chemin, nœud) de chaque PARAMÈTRE du schéma, imbriqués compris."""
    for nom, sous in (schema.get("properties") or {}).items():
        yield f"{chemin}{nom}", sous
        yield from _proprietes(sous, f"{chemin}{nom}.")
    if isinstance(schema.get("items"), dict):
        yield from _proprietes(schema["items"], f"{chemin}[].")


def _defauts(definition: dict) -> list[str]:
    """Écarts d'une définition d'outil au standard Anthropic. Vide = conforme."""
    description = definition.get("description", "")
    bas = description.lower()
    defauts = []
    if len(description) < _LONGUEUR_MIN:
        defauts.append(f"trop courte ({len(description)} < {_LONGUEUR_MIN} caractères)")
    if len([p for p in re.split(r"(?<=[.!?])\s+", description.strip()) if p]) < _PHRASES_MIN:
        defauts.append(f"moins de {_PHRASES_MIN} phrases")
    if "quand" not in bas:
        defauts.append("ne dit pas QUAND l'utiliser")
    if "ne pas" not in bas:
        defauts.append("ne dit pas quand NE PAS l'utiliser")
    for chemin, noeud in _proprietes(definition.get("input_schema", {})):
        if len(str(noeud.get("description", "")).strip()) < 15:
            defauts.append(f"paramètre `{chemin}` sans description utile")
    return defauts


def _sans_descriptions(valeur):
    """Le schéma d'un outil, descriptions retirées : c'est ce qui ne doit PAS changer."""
    if isinstance(valeur, dict):
        return {k: _sans_descriptions(v) for k, v in valeur.items() if k != "description"}
    if isinstance(valeur, list):
        return [_sans_descriptions(v) for v in valeur]
    return valeur


def _v2(nom: str, avec_hypotheses: bool = True) -> dict:
    definition = copy.deepcopy(next(t for t in TOOLS_DEFINITIONS if t["name"] == nom))
    if not avec_hypotheses:
        (definition["input_schema"].get("properties") or {}).pop(HYPOTHESES_CLE, None)
    return appliquer_v2(definition)


# ── 1. Le standard, mesurable ────────────────────────────────────────────────────────────────

def test_il_y_a_une_description_v2_par_outil_et_pas_une_de_plus():
    assert set(DESCRIPTIONS_V2) == set(_NOMS) == set(PARAMETRES_V2)


@pytest.mark.parametrize("nom", _NOMS)
@pytest.mark.parametrize("avec_hypotheses", [True, False])
def test_chaque_description_v2_respecte_le_standard(nom, avec_hypotheses):
    assert _defauts(_v2(nom, avec_hypotheses)) == []


def test_le_test_de_qualite_n_est_pas_vide_les_descriptions_actuelles_echouent():
    """Falsifiabilité du prédicat : sur les descriptions V1, il DOIT signaler des défauts — sinon un
    test qui passe sur V2 ne prouverait rien."""
    en_defaut = {nom for nom in _NOMS
                 if _defauts(next(t for t in TOOLS_DEFINITIONS if t["name"] == nom))}
    assert {"inspect_schema", "query_data", "discover_route", "inspect_page_form",
            "write_feature_file"} <= en_defaut
    assert len(en_defaut) >= 9      # presque toutes : c'est tout l'intérêt de la V2
    # …et chaque critère sait échouer isolément.
    base = _v2("inspect_schema")
    sans_quand = {**base, "description": base["description"].replace("Quand", "Si").replace(
        "quand", "si")}
    assert any("QUAND" in d for d in _defauts(sans_quand))
    sans_non = {**base, "description": base["description"].replace("Ne pas", "Éviter")}
    assert any("NE PAS" in d for d in _defauts(sans_non))
    sans_param = copy.deepcopy(base)
    sans_param["input_schema"]["properties"]["model"].pop("description")
    assert any("sans description" in d for d in _defauts(sans_param))


# ── 2. Ni les noms ni les schémas ne changent ────────────────────────────────────────────────

@pytest.mark.parametrize("nom", _NOMS)
def test_la_v2_ne_change_ni_le_nom_ni_le_schema(nom):
    ancien = next(t for t in TOOLS_DEFINITIONS if t["name"] == nom)
    nouveau = _v2(nom)
    assert nouveau["name"] == nom
    assert _sans_descriptions(nouveau) == _sans_descriptions(ancien)


def test_appliquer_v2_ne_mute_pas_l_entree():
    avant = copy.deepcopy(TOOLS_DEFINITIONS)
    for nom in _NOMS:
        _v2(nom)
    assert TOOLS_DEFINITIONS == avant


def test_un_parametre_sans_description_v2_est_refuse():
    """La dérive est refusée, pas servie à moitié décrite."""
    definition = copy.deepcopy(next(t for t in TOOLS_DEFINITIONS if t["name"] == "inspect_schema"))
    definition["input_schema"]["properties"]["nouveau_parametre"] = {"type": "string"}
    with pytest.raises(KeyError, match="nouveau_parametre"):
        appliquer_v2(definition)


def test_une_description_v2_d_un_parametre_disparu_est_refusee(monkeypatch):
    monkeypatch.setitem(PARAMETRES_V2["inspect_schema"], "fantome", "paramètre qui n'existe plus")
    with pytest.raises(KeyError, match="fantome"):
        _v2("inspect_schema")


def test_un_outil_sans_description_v2_est_refuse():
    with pytest.raises(KeyError):
        appliquer_v2({"name": "outil_inconnu", "description": "x",
                      "input_schema": {"type": "object", "properties": {}}})


# ── 3. Les promesses déjà testées sur V1 survivent, et ne citent aucun outil fantôme ─────────

def test_les_promesses_des_outils_d_ecriture_sont_conservees():
    for nom in ("write_feature_file", "write_steps_file"):
        description = DESCRIPTIONS_V2[nom]
        assert "REMPLACE" in description and "ENTIER" in description
    assert "ASCII" in DESCRIPTIONS_V2["write_steps_file"]
    assert "pas de step partagé redéfini" in DESCRIPTIONS_V2["write_steps_file"]


def test_une_description_ne_cite_que_des_outils_qui_existent():
    autorises = set(_NOMS) | {"evidence_ids", "requirement_ids", HYPOTHESES_CLE}
    for nom, description in DESCRIPTIONS_V2.items():
        for cite in re.findall(r"`([a-z]+(?:_[a-z]+)+)`", description):
            assert cite in autorises, f"{nom} cite `{cite}`, qui n'est pas un outil"


def test_le_renvoi_vers_un_autre_outil_est_reciproquement_coherent():
    """Quand une description dit « c'est `X` », X doit exister ET être l'outil du bon usage."""
    assert "`attempt_login`" in DESCRIPTIONS_V2["attempt_form_submission"]
    assert "`attempt_form_submission`" in DESCRIPTIONS_V2["attempt_login"]
    assert "`write_test_plan`" in DESCRIPTIONS_V2["write_feature_file"]


# ── 4. Chaque chiffre et chaque refus annoncé est tenu par le code (principe 6) ───────────────

class _Connecteur:
    """Doublure : enregistre ce que l'outil demande au connecteur."""

    def __init__(self, champs: int = 3):
        self.limite = None
        self._champs = champs

    def get_schema(self, model):
        return {f"champ_{i}": {"type": "char", "required": False} for i in range(self._champs)}

    def search(self, model, domaine, limit=0):
        self.limite = limit
        return [1]

    def read(self, model, ids, fields):
        return [{"id": 1}]

    def inspect_odoo_view(self, model, view_type):
        raise NotImplementedError("pas Odoo")


def _ctx(tmp_path, connecteur=None, **kw):
    return ToolContext("cas", tmp_path, connector=connecteur, **kw)


@pytest.mark.parametrize("demande, attendu", [(99, 10), (10, 10), (5, 5), (0, 1), (-4, 1)])
def test_query_data_borne_entre_1_et_10(tmp_path, demande, attendu):
    assert "entre 1 et 10" in PARAMETRES_V2["query_data"]["limit"]
    connecteur = _Connecteur()
    dispatch("query_data", {"model": "m", "limit": demande}, _ctx(tmp_path, connecteur))
    assert connecteur.limite == attendu


def test_query_data_lit_3_enregistrements_par_defaut(tmp_path):
    assert "3 si absent" in PARAMETRES_V2["query_data"]["limit"]
    connecteur = _Connecteur()
    dispatch("query_data", {"model": "m"}, _ctx(tmp_path, connecteur))
    assert connecteur.limite == 3


def test_inspect_schema_rend_50_champs_au_plus(tmp_path):
    assert "50 champs au plus" in DESCRIPTIONS_V2["inspect_schema"]
    resultat = dispatch("inspect_schema", {"model": "m"}, _ctx(tmp_path, _Connecteur(champs=80)))
    assert resultat.observation.count("\n- ") == 50
    peu = dispatch("inspect_schema", {"model": "m"}, _ctx(tmp_path, _Connecteur(champs=4)))
    assert peu.observation.count("\n- ") == 4          # sens inverse : pas de troncature gratuite


@pytest.mark.parametrize("nom, entree", [
    ("query_data", {"model": "m"}),
    ("attempt_login", {"username": "u", "password": "p"}),
    ("attempt_form_submission", {"page_url": "/x", "field_values": {"a": "b"}}),
])
def test_ces_outils_sont_refuses_en_mode_qualification(tmp_path, nom, entree):
    assert "qualification" in DESCRIPTIONS_V2[nom]
    ctx = _ctx(tmp_path, _Connecteur(), qualification=True, calibration_writes_enabled=True)
    resultat = dispatch(nom, entree, ctx)
    assert not resultat.ok and "qualification" in resultat.observation


def test_inspect_schema_n_est_pas_refuse_en_qualification(tmp_path):
    """Sens inverse : la description ne promet pas ce refus pour `inspect_schema`, et il n'existe pas."""
    assert "qualification" not in DESCRIPTIONS_V2["inspect_schema"]
    assert dispatch("inspect_schema", {"model": "m"},
                    _ctx(tmp_path, _Connecteur(), qualification=True)).ok


def test_attempt_form_submission_est_refuse_sans_autorisation_du_projet(tmp_path):
    assert "explicitement autorisé" in DESCRIPTIONS_V2["attempt_form_submission"]
    resultat = dispatch("attempt_form_submission", {"page_url": "/x", "field_values": {"a": "b"}},
                        _ctx(tmp_path, _Connecteur(), calibration_writes_enabled=False))
    assert not resultat.ok and "désactivée" in resultat.observation


def test_inspect_odoo_view_repond_que_le_connecteur_n_expose_pas_de_vues_odoo(tmp_path):
    assert "n'expose pas de vues Odoo" in DESCRIPTIONS_V2["inspect_odoo_view"]
    resultat = dispatch("inspect_odoo_view", {"model": "m"}, _ctx(tmp_path, _Connecteur()))
    assert not resultat.ok and "n'expose pas de vues Odoo" in resultat.observation


def test_write_feature_file_refuse_ce_que_sa_description_dit_refuser(tmp_path):
    for contenu in ("", "pas du gherkin", "# language: fr\nFonctionnalité: F\n"):
        resultat = dispatch("write_feature_file", {"content": contenu}, _ctx(tmp_path))
        assert not resultat.ok, contenu
    ok = dispatch("write_feature_file",
                  {"content": "# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit un pas\n"},
                  _ctx(tmp_path))
    assert ok.ok                                       # sens inverse : un fichier valide passe
