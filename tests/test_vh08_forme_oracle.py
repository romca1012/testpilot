"""Lot VH-08 (décision A51 du porteur, 2026-10-16) — l'IA connaît la FORME des réponses de l'oracle, jamais leurs valeurs.

Mesuré (banc base-7, 2026-10-11) : 4 des 7 tests faux tenaient à l'oracle, dont l'agent ne connaissait que le nom des requêtes.
Ce que ces tests gardent :
1. une forme ne contient AUCUNE valeur ni aucun compte (sinon elle deviendrait l'attendu d'un « Alors ») ;
2. seules les requêtes GET sont appelées (une lecture) ; une requête qui échoue est dite illisible, sans son message ;
3. l'exploration relève la forme ; la fin d'un essai aussi, AVANT la remise à zéro, et seulement interrupteur allumé ;
4. interrupteur éteint : ce que l'IA reçoit est identique à avant, octet pour octet ; allumé : les formes des requêtes encore
   déclarées seulement ;
5. un test qui cite une requête d'oracle non déclarée est refusé à l'écriture (interrupteur allumé).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.connectors import forme_oracle as f
from testpilot.generation import interrupteurs
from testpilot.generation.prompt import build_initial_message
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import essai as e
from testpilot.generation.tools import write as w

RACINE = Path(__file__).resolve().parent.parent

PLEINE = {"commandes": [{"numero": "CMD-0042", "lignes": [{"nom": "Chaise", "quantite": 3, "prix_unitaire": "19.90"}],
                         "total_ttc": "129.15", "payee": True, "note": None}],
          "panier": {"lignes": [], "remise_pct": "10"}, "enregistrements": [{"id": 7, "ville": "Lyon"}]}


@pytest.fixture(autouse=True)
def eteint(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "0")


# ── 1. La forme, jamais une valeur ────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_forme_ne_contient_aucune_valeur_ni_aucun_compte():
    rendu = "\n".join(f.rendre_tout({"etat": f.forme(PLEINE)}))

    for interdit in ("CMD-0042", "Chaise", "19.90", "129.15", "Lyon", "10", "3", "7", "True", "1 élément", "2 élément"):
        assert interdit not in rendu, f"« {interdit} » ne doit jamais revenir à l'IA"
    for attendu in ("commandes : liste d'objets, chacun :", "numero : texte", "quantite : nombre", "payee : vrai/faux",
                    "note : vide", "lignes : liste vide (forme de ses éléments inconnue)", "remise_pct : texte"):
        assert attendu in rendu


def test_la_forme_des_elements_d_une_liste_reunit_leurs_types_sans_trahir_leur_nombre():
    """Revue du 2026-10-16 : « nombre ou texte ou nombre ou texte » trahissait combien d'éléments avaient été lus."""
    forme = f.forme([{"a": 1}, {"a": "x"}, {"a": 2}, {"a": "y"}, {"a": None}])
    assert forme == {"liste": {"a": "nombre ou texte ou vide"}}
    assert f.forme([]) == {"liste": None}
    assert "\n".join(f.rendre_tout({"r": f.forme([1, 2])})).endswith("liste de : nombre")


def test_falsifiable_des_elements_aux_cles_differentes_ne_montrent_pas_leurs_cles():
    forme = f.forme([{"sac-a-dos": 2}, {"lampe": 0}])
    assert forme == {"liste": f.CLES_DE_DONNEES}
    assert "lampe" not in "\n".join(f.rendre_tout({"r": forme}))


# ── Fin d'essai : clés de données et état du moment (revue du 2026-10-16, bloquant) ──────────────────────────────────────

EXPLORATION = {"commandes": [], "panier": {}, "paiement": None, "client": {"nom": "x"}}


def test_falsifiable_un_objet_vide_a_l_exploration_ne_montre_pas_les_cles_vues_a_l_essai():
    """Le panier rangé par référence : `{"bike-light": 1}` après l'essai. « bike-light » est une donnée — si elle était
    montrée, l'IA écrirait « le champ "panier.bike-light" vaut "1" » et un défaut (mauvais article ajouté) passerait vert."""
    cumul = f.completer(f.forme(EXPLORATION), f.forme({"commandes": [{"numero": "CMD-0042", "total": "2.00"}],
                                                       "panier": {"bike-light": 1}, "paiement": "carte",
                                                       "client": {"nom": "y", "secret_ajoute": "z"}}))
    rendu = "\n".join(f.rendre_tout({"etat": cumul}))

    assert "bike-light" not in rendu and "secret_ajoute" not in rendu and "CMD-0042" not in rendu
    assert "panier : objet dont les clés sont des données (non montrées)" in rendu
    assert "commandes : liste d'objets, chacun :" in rendu and "numero : texte" in rendu
    assert "paiement : texte ou vide" in rendu, "un champ rempli par l'essai ne se lit plus « vide » seul"


def test_falsifiable_le_cumul_ne_dit_jamais_l_etat_du_moment():
    """Une liste connue par un essai précédent reste connue : un essai qui la laisse vide ne la redit pas vide."""
    deja = f.completer(f.forme(EXPLORATION), f.forme({"commandes": [{"numero": "C1"}]}))
    apres = f.completer(deja, f.forme({"commandes": []}))
    assert apres == deja
    assert f.completer(f.forme(EXPLORATION), {"illisible": "URLError"}) == f.forme(EXPLORATION)


def test_falsifiable_un_element_seul_aux_cles_qui_ne_sont_pas_des_noms_de_champs_est_masque():
    """Revue du 2026-10-16 (2e passe) : le panier rangé `[{"<référence>": quantité}]` — un seul élément, rien à comparer. Une
    clé vue seulement à l'essai qui n'a pas la syntaxe d'un nom de champ n'est jamais montrée."""
    for donnee in ({"sauce-labs-backpack": 1}, {"CMD-0042": {"total": "1"}}, {"Câble HDMI": 2}, {"2026-10-16": 1}):
        cumul = f.completer(f.forme({"lignes": []}), f.forme({"lignes": [donnee]}))
        assert cumul == {"lignes": {"liste": f.CLES_DE_DONNEES}}, donnee
    assert f.completer(f.forme({"lignes": []}), f.forme({"lignes": [{"numero": "C1", "total_ttc": "2"}]})) == {
        "lignes": {"liste": {"numero": "texte", "total_ttc": "texte"}}}


def test_un_objet_niche_dans_un_element_vu_a_l_essai_n_est_pas_detaille():
    cumul = f.completer({"liste": None}, f.forme([{"numero": "C1", "quantites": {"ref-1": 2}}]))
    assert cumul == {"liste": {"numero": "texte", "quantites": f.CLES_DE_DONNEES}}


def test_une_requete_jamais_relevee_a_l_exploration_n_est_pas_montree_apres_un_essai():
    assert f.completer_tout({"etat": {"x": "texte"}}, {"etat": {"x": "texte"}, "autre": {"y": "texte"}}) == {
        "etat": {"x": "texte"}}


def test_seules_les_requetes_get_sont_appelees():
    requetes = json.dumps([{"name": "etat", "path": "/e"}, {"name": "creer", "method": "POST", "path": "/c"},
                           {"name": "lire", "method": "get", "path": "/l"}])
    assert f.requetes_en_lecture(requetes) == ["etat", "lire"]
    assert f.requetes_en_lecture("illisible") == []


def test_une_requete_qui_echoue_est_illisible_sans_son_message():
    def executer(nom):
        if nom == "panne":
            raise OSError("https://secret.exemple.test/?jeton=abc")
        return {"x": 1}

    formes = f.relever(executer, ["etat", "panne"])
    assert formes == {"etat": {"x": "nombre"}, "panne": {"illisible": "OSError"}}
    assert "jeton" not in "\n".join(f.rendre_tout(formes))


# ── 2. L'exploration relève la forme ─────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_l_exploration_releve_la_forme_des_requetes_get(tmp_path, monkeypatch):
    from testpilot.api.services import exploration_service as ex
    from testpilot.connectors import oracle_http
    from testpilot.generation import domain_model

    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "domain")   # jamais l'annuaire réel du poste
    appelees = []
    monkeypatch.setattr(oracle_http.OracleHttp, "executer", lambda self, nom: appelees.append(nom) or PLEINE)
    monkeypatch.setattr(ex, "_crawl", lambda connexion, max_pages: {"pages": {"/": {}}, "transitions": {}})
    connexion = {"connector_type": "web", "nom": "Boutique", "base_url": "http://app", "oracle": {
        "base_url": "http://app", "auth": {}, "queries": [{"name": "etat", "path": "/__etat"},
                                                         {"name": "vider", "method": "POST", "path": "/__vider"}]}}

    ex.run_exploration("job", project_id=3, connexion=connexion)

    modele = json.loads(domain_model.chemin_du_modele(3).read_text(encoding="utf-8"))
    assert appelees == ["etat"], "jamais une requête POST"
    assert modele["formes_oracle"]["etat"]["commandes"]["liste"]["numero"] == "texte"
    assert "CMD-0042" not in json.dumps(modele)


@pytest.mark.parametrize("allume, oracle", [(True, None), (False, {"base_url": "http://app", "auth": {},
                                                                    "queries": [{"name": "etat", "path": "/e"}]})])
def test_sans_oracle_ou_interrupteur_eteint_l_exploration_est_celle_d_avant(tmp_path, monkeypatch, allume, oracle):
    from testpilot.api.services import exploration_service as ex
    from testpilot.connectors import oracle_http
    from testpilot.generation import domain_model

    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1" if allume else "0")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "domain")   # jamais l'annuaire réel du poste
    monkeypatch.setattr(oracle_http.OracleHttp, "executer", lambda self, nom: pytest.fail("l'oracle ne doit pas être appelé"))
    monkeypatch.setattr(ex, "_crawl", lambda connexion, max_pages: {"pages": {"/": {}}, "transitions": {}})
    ex.run_exploration("job", project_id=4, connexion={"connector_type": "web", "nom": "B", "base_url": "http://app",
                                                       "oracle": oracle})
    assert "formes_oracle" not in json.loads(domain_model.chemin_du_modele(4).read_text(encoding="utf-8"))


# ── 3. Ce que l'IA reçoit ─────────────────────────────────────────────────────────────────────────────────────────────────

def _plan():
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[])


def test_falsifiable_eteint_le_message_est_celui_d_avant(monkeypatch):
    from testpilot.generation.agent import GenerationAgent

    modele = {"formes_oracle": {"etat": f.forme(PLEINE)}}
    projet = {"oracle_requetes_disponibles": ["etat"]}
    assert GenerationAgent._formes_oracle(modele, projet) is None
    assert build_initial_message(_plan(), oracle=["etat"], formes_oracle=None) == build_initial_message(_plan(), oracle=["etat"])

    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1")
    formes = GenerationAgent._formes_oracle(modele, projet)
    message = build_initial_message(_plan(), oracle=["etat"], formes_oracle=formes)
    assert "Forme des réponses de l'oracle" in message and "numero : texte" in message
    assert "CMD-0042" not in message and "129.15" not in message


def test_falsifiable_la_generation_branche_les_formes_et_le_controle_des_requetes(monkeypatch, tmp_path):
    """`GenerationAgent.generate` pose `ctx.requetes_oracle` et `ctx.formes_oracle`, et donne les formes au message de départ.
    Le test s'arrête à la boucle (aucun appel au modèle de langage)."""
    from testpilot.generation import agent as agent_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_mod.domain_model, "DOMAIN_DIR", tmp_path / "domain")   # jamais l'annuaire réel du poste
    vus = []

    def _boucle(**kw):
        vus.append((kw["ctx"], kw["state"].messages[0]["content"]))
        raise RuntimeError("arrêt du test")

    monkeypatch.setattr(agent_mod, "run_loop", _boucle)
    monkeypatch.setattr(agent_mod.domain_model, "charger_modele",
                        lambda projet: {"formes_oracle": {"etat": {"commandes": {"liste": None}}}})
    projet = {"id": 1, "connector_type": "web", "oracle_requetes_disponibles": ["etat"]}
    for allume in (False, True):
        monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1" if allume else "0")
        with pytest.raises(RuntimeError, match="arrêt du test"):
            agent_mod.GenerationAgent(llm=object(), connector=None, dry_runner=None).generate(_plan(), projet=projet)

    (eteint, message_eteint), (allume, message_allume) = vus
    assert eteint.requetes_oracle is None and eteint.formes_oracle is None
    assert "Forme des réponses de l'oracle" not in message_eteint
    assert allume.requetes_oracle == frozenset({"etat"}) and allume.formes_oracle == {"etat": {"commandes": {"liste": None}}}
    assert "Forme des réponses de l'oracle" in message_allume


def test_seules_les_requetes_encore_declarees_sont_montrees(monkeypatch):
    from testpilot.generation.agent import GenerationAgent

    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1")
    modele = {"formes_oracle": {"etat": {"x": "texte"}, "ancienne": {"y": "texte"}}}
    assert GenerationAgent._formes_oracle(modele, {"oracle_requetes_disponibles": ["etat"]}) == {"etat": {"x": "texte"}}
    assert GenerationAgent._formes_oracle(modele, {"oracle_requetes_disponibles": []}) is None
    assert build_initial_message(_plan(), oracle=None, formes_oracle={"etat": {"x": "texte"}}) == build_initial_message(_plan())


# ── 4. À la fin d'un essai, avant la remise à zéro ───────────────────────────────────────────────────────────────────────

def _environment():
    sys.path.insert(0, str(RACINE))
    from behave_runtime import environment
    return environment


def test_les_noms_de_la_variable_d_essai_sont_d_accord():
    assert _environment().ESSAI_FORME_ORACLE_ENV == e.ESSAI_FORME_ORACLE_ENV


def test_falsifiable_le_harnais_ne_releve_la_forme_que_si_l_essai_le_demande(monkeypatch):
    from testpilot.connectors import oracle_config

    sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
    env = _environment()
    contexte = SimpleNamespace(oracle=SimpleNamespace(executer=lambda nom: PLEINE))
    monkeypatch.setenv(oracle_config.ENV_ORACLE, json.dumps({"queries": [{"name": "etat", "path": "/e"},
                                                                         {"name": "p", "method": "POST", "path": "/p"}]}))
    monkeypatch.delenv(env.ESSAI_FORME_ORACLE_ENV, raising=False)
    assert env._formes_de_l_oracle_a_la_fin_de_l_essai(contexte) == {}

    monkeypatch.setenv(env.ESSAI_FORME_ORACLE_ENV, "1")
    formes = env._formes_de_l_oracle_a_la_fin_de_l_essai(contexte)
    assert list(formes) == ["etat"] and formes["etat"]["commandes"]["liste"]["total_ttc"] == "texte"
    assert env._formes_de_l_oracle_a_la_fin_de_l_essai(SimpleNamespace(oracle=None)) == {}


@pytest.mark.parametrize("allume", [False, True])
def test_falsifiable_l_essai_demande_la_forme_seulement_interrupteur_allume(tmp_path, monkeypatch, allume):
    from testpilot.execution.behave_result import BehaveResult
    from testpilot.generation.litteraux_observes import Annuaire
    from testpilot.guardrails import bac_a_sable

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    bac_a_sable.reinitialiser_pour_les_tests()
    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1" if allume else "0")
    vues = []

    class _Runner:
        def __init__(self, variables):
            self.variables = variables
            vues.append(dict(variables))

        def dry_run(self, module):
            return BehaveResult(success=True, returncode=0, dry_run=True, undefined_steps=[])

        def real_run(self, module):
            etat = {"url": "http://app/commande", "elements": []}
            if self.variables.get(e.ESSAI_FORME_ORACLE_ENV) == "1":
                etat["formes_oracle"] = {"etat": f.forme(PLEINE)}
            Path(self.variables[e.ESSAI_ETAT_FILE_ENV]).write_text(json.dumps(etat), encoding="utf-8")
            return BehaveResult(success=True, returncode=0, failures=[])

    essai = e.EssaiBacASable(remettre_a_zero=lambda: None, cle="http://app:80",
                             fabriquer_runner=lambda dossier, variables: _Runner(variables))
    # La forme de l'exploration (listes vides), que l'essai complète — `None` interrupteur éteint (`GenerationAgent`).
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=Annuaire(),
                      formes_oracle={"etat": f.forme({"commandes": [], "panier": {"lignes": [], "remise_pct": "0"},
                                                      "enregistrements": []})} if allume else None)

    sortie = e.essayer_les_actions(ctx, ['Quand j\'ouvre la page "/produits"'])
    bac_a_sable.reinitialiser_pour_les_tests()

    assert (e.ESSAI_FORME_ORACLE_ENV in vues[0]) is allume
    assert ("numero : texte" in sortie.observation) is allume
    assert "CMD-0042" not in sortie.observation and "129.15" not in sortie.observation


def test_falsifiable_apres_un_essai_seul_ce_qui_change_est_redit(tmp_path, monkeypatch):
    """Rejeu de M2 (2026-10-17) : le cumul entier revenait après chaque essai, six fois sur un même cas. L'IA l'a déjà reçu ;
    un essai qui n'apprend rien n'ajoute rien, et un essai qui apprend une requête ne redit que celle-là."""
    from testpilot.execution.behave_result import BehaveResult
    from testpilot.generation.litteraux_observes import Annuaire
    from testpilot.guardrails import bac_a_sable

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    bac_a_sable.reinitialiser_pour_les_tests()
    monkeypatch.setenv(interrupteurs.ENV_FORME_ORACLE, "1")
    reponses = [{"etat": {"commandes": [{"numero": "C1"}]}, "stock": {"articles": []}},
                {"etat": {"commandes": [{"numero": "C2"}]}, "stock": {"articles": []}},
                {"etat": {"commandes": []}, "stock": {"articles": [{"ref": "A-1"}]}}]

    class _Runner:
        def __init__(self, variables):
            self.variables = variables

        def dry_run(self, module):
            return BehaveResult(success=True, returncode=0, dry_run=True, undefined_steps=[])

        def real_run(self, module):
            etat = {"url": "http://app/", "elements": [],
                    "formes_oracle": {nom: f.forme(r) for nom, r in reponses.pop(0).items()}}
            Path(self.variables[e.ESSAI_ETAT_FILE_ENV]).write_text(json.dumps(etat), encoding="utf-8")
            return BehaveResult(success=True, returncode=0, failures=[])

    essai = e.EssaiBacASable(remettre_a_zero=lambda: None, cle="http://app:80",
                             fabriquer_runner=lambda dossier, variables: _Runner(variables))
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=Annuaire(),
                      formes_oracle={"etat": f.forme({"commandes": []}), "stock": f.forme({"articles": []})})

    sorties = [e.essayer_les_actions(ctx, ['Quand j\'ouvre la page "/produits"']).observation for _ in range(3)]
    bac_a_sable.reinitialiser_pour_les_tests()

    assert "« etat »" in sorties[0] and "numero : texte" in sorties[0] and "« stock »" not in sorties[0]
    assert "Forme des réponses de l'oracle : rien de nouveau depuis ce que tu as reçu." in sorties[1]
    assert "« etat »" not in sorties[1] and "« stock »" not in sorties[1], "rien de nouveau : rien n'est redit"
    assert "« stock »" in sorties[2] and "ref : texte" in sorties[2] and "« etat »" not in sorties[2]
    assert ctx.formes_oracle["etat"] == {"commandes": {"liste": {"numero": "texte"}}}, "le cumul, lui, garde tout"


# ── 5. Une requête d'oracle non déclarée est refusée à l'écriture ────────────────────────────────────────────────────────

FEATURE = ('# language: fr\nFonctionnalité: F\n  Scénario: S\n    Quand j\'ouvre la page "/"\n'
           '    Alors le champ "commandes" de l\'oracle "{nom}" compte 1 élément\n')


def test_falsifiable_une_requete_non_declaree_est_reperee():
    assert w.requetes_oracle_inconnues(FEATURE.format(nom="etat"), frozenset({"etat"})) == []
    assert w.requetes_oracle_inconnues(FEATURE.format(nom="commandes"), frozenset({"etat"})) == ["commandes"]
    assert w.requetes_oracle_inconnues(FEATURE.format(nom="commandes"), None) == [], "interrupteur éteint : aucun contrôle"
    renvoie = ('# language: fr\nFonctionnalité: F\n  Contexte:\n    Soit l\'oracle "y" renvoie 0 résultat\n'
               '  Scénario: S\n    Alors l\'oracle "x" renvoie 1 résultat\n')
    assert w.requetes_oracle_inconnues(renvoie, frozenset()) == ["y", "x"], "le contexte compte aussi"


def test_seules_les_etapes_comptent_ni_commentaire_ni_parametre_de_plan():
    feature = ('# language: fr\n# l\'oracle "brouillon" (un commentaire)\nFonctionnalité: F\n  Plan du Scénario: S\n'
               '    Alors le champ "commandes" de l\'oracle "<requete>" compte 1 élément\n\n    Exemples:\n'
               '      | requete |\n      | etat    |\n      | autre   |\n')
    assert w.requetes_oracle_inconnues(feature, frozenset({"etat"})) == ["autre"], "les valeurs des Exemples sont lues"


def test_falsifiable_les_etapes_sous_une_regle_sont_lues():
    feature = ('# language: fr\nFonctionnalité: F\n  Règle: R\n    Scénario: S\n'
               '      Alors l\'oracle "cachee" renvoie 1 résultat\n')
    assert w.requetes_oracle_inconnues(feature, frozenset({"etat"})) == ["cachee"]


def test_falsifiable_write_feature_file_refuse_une_requete_non_declaree(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, requetes_oracle=frozenset({"etat"}))

    refus = w.write_feature_file(ctx, FEATURE.format(nom="commandes"))
    assert not refus.ok and "ORACLE_INCONNU" in refus.observation and "« etat »" in refus.observation

    sans_controle = w.write_feature_file(ToolContext(module_name="m", generated_dir=tmp_path), FEATURE.format(nom="commandes"))
    assert "ORACLE_INCONNU" not in sans_controle.observation
