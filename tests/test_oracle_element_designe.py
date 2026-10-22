"""Étape 5 (2026-10-22) — « l'élément de la liste … de l'oracle … dont "<clé>" est la valeur affichée pour "<libellé>" a
"<champ>" qui vaut / compte … », et le refus d'écriture LECTURE_PAGE_ENTIERE.

Mesuré sur le banc (`commande_persistance_serveur`, bras « après ») : faute de step pour juger le DÉTAIL de la commande que
l'écran affiche, l'IA lisait tout le texte de la page avec une expression régulière, attrapait « sContrôle » du menu, et le
test accusait une application saine. Chaque test `falsifiable` échoue si le step juge un autre élément que celui que l'écran
désigne, ou s'il conclut sur un test mal posé.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

from testpilot.generation import interrupteurs  # noqa: E402
from testpilot.generation.tools import write as w  # noqa: E402

ECRAN = '<p role="status">Numéro de commande : <strong id="numero-commande">{numero}</strong></p>'


def _oracle(*commandes):
    return {"commandes": list(commandes), "panier": {"lignes": []}}


def _commande(numero, nom="Tapis de souris", quantite=3, lignes=None):
    return {"numero": numero, "lignes": [{"nom": nom, "quantite": quantite}] if lignes is None else lignes}


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture
def ecran(navigateur, monkeypatch, tmp_path):
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 800)
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    H.definir_etat_constat(scenario="s", step_type="then")
    ouvertes = []

    def ouvrir(numero, reponse, corps=None):
        p = navigateur.new_page()
        p.set_content(f"<html><body>{corps or ECRAN.format(numero=numero)}</body></html>")
        ouvertes.append(p)
        monkeypatch.setattr(H, "_executer_oracle", lambda context, requete: reponse)
        return SimpleNamespace(page=p)

    ouvrir.journal = tmp_path / "c.jsonl"
    yield ouvrir
    for p in ouvertes:
        p.close()
    H.definir_etat_constat(scenario="", step_type="")


def _constats(ecran):
    if not ecran.journal.exists():
        return []
    return [(c["ok"], c["source"]) for c in map(json.loads, ecran.journal.read_text(encoding="utf-8").splitlines())]


def _vaut(contexte, champ, valeur):
    H.oracle_element_affiche_champ_vaut(contexte, "commandes", "etat", "numero", "Numéro de commande", champ, valeur)


def _compte(contexte, champ, n):
    H.oracle_element_affiche_champ_compte(contexte, "commandes", "etat", "numero", "Numéro de commande", champ, n)


@pytest.mark.conformance
def test_l_element_designe_par_l_ecran_est_juge(ecran):
    contexte = ecran("CMD-0001", _oracle(_commande("CMD-0001")))
    _compte(contexte, "lignes", 1)
    _vaut(contexte, "lignes.0.nom", "Tapis de souris")
    _vaut(contexte, "lignes.0.quantite", "3")
    assert _constats(ecran) == [(True, "oracle")] * 3
    assert vars(contexte) == {"page": contexte.page}, "rien n'est gardé d'un step à l'autre"


@pytest.mark.conformance
def test_falsifiable_c_est_l_element_affiche_qui_est_juge_jamais_un_autre(ecran):
    """L'écran affiche CMD-0002 ; CMD-0001 a la bonne ligne, CMD-0002 une quantité fausse : le step doit échouer."""
    contexte = ecran("CMD-0002", _oracle(_commande("CMD-0001"), _commande("CMD-0002", quantite=2)))
    with pytest.raises(AssertionError, match="« 2 », « 3 » attendu"):
        _vaut(contexte, "lignes.0.quantite", "3")
    assert _constats(ecran) == [(False, "oracle")]


@pytest.mark.conformance
@pytest.mark.parametrize("commande, champ, attendu", [
    (_commande("CMD-0001", nom="Clavier"), "lignes.0.nom", "Tapis de souris"),
    (_commande("CMD-0001", lignes=[]), "lignes.0.nom", "Tapis de souris"),
])
def test_falsifiable_un_champ_faux_ou_absent_echoue(ecran, commande, champ, attendu):
    contexte = ecran("CMD-0001", _oracle(commande))
    with pytest.raises(AssertionError):
        _vaut(contexte, champ, attendu)
    assert _constats(ecran) == [(False, "oracle")]


@pytest.mark.conformance
def test_falsifiable_un_compte_faux_echoue(ecran):
    contexte = ecran("CMD-0001", _oracle(_commande("CMD-0001", lignes=[{"nom": "a"}, {"nom": "b"}])))
    with pytest.raises(AssertionError):
        _compte(contexte, "lignes", 1)
    assert _constats(ecran) == [(False, "oracle")]


@pytest.mark.conformance
def test_falsifiable_un_numero_affiche_que_le_serveur_n_a_pas_echoue(ecran):
    """Le défaut `etat_non_enregistre` : l'écran confirme une commande que le serveur n'a pas."""
    contexte = ecran("CMD-0009", _oracle(_commande("CMD-0001")))
    with pytest.raises(AssertionError, match="aucun élément"):
        _vaut(contexte, "lignes.0.nom", "Tapis de souris")
    assert _constats(ecran) == [(False, "oracle")]


@pytest.mark.conformance
@pytest.mark.parametrize("reponse, champ, valeur", [
    (_oracle(_commande("CMD-0001"), _commande("CMD-0001")), "lignes.0.nom", "Tapis de souris"),  # doublon : jamais le premier
    (_oracle(_commande("CMD-0001")), "lignes.0.quantité", "3"),                                 # clé mal écrite
    (_oracle(_commande("CMD-0001")), "lignes", "3"),                                            # une liste ne « vaut » pas
    (_oracle(_commande("CMD-0001")), "lignes.0.quantite", "3 pièces"),                          # nombre contre texte
    ({"commandes": {"numero": "CMD-0001"}}, "lignes.0.nom", "Tapis de souris"),                 # pas une liste
])
def test_falsifiable_un_test_mal_pose_n_est_jamais_un_vert_ni_un_defaut(ecran, reponse, champ, valeur):
    contexte = ecran("CMD-0001", reponse)
    with pytest.raises(H.ReponseOracleNonComptableError):
        _vaut(contexte, champ, valeur)
    assert _constats(ecran) == [], "un test mal posé ne consigne aucun constat"


@pytest.mark.conformance
def test_falsifiable_un_libelle_absent_est_une_erreur_du_test(ecran):
    contexte = ecran("", _oracle(_commande("CMD-0001")), corps="<p>Merci</p>")
    with pytest.raises(H.ElementIntrouvableError):
        _vaut(contexte, "lignes.0.nom", "Tapis de souris")
    assert _constats(ecran) == []


@pytest.mark.conformance
def test_un_numero_rendu_juste_apres_l_action_est_relu(ecran, monkeypatch):
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 3000)
    corps = (ECRAN.format(numero="…") + "<script>setTimeout(function(){document.getElementById('numero-commande')"
             ".textContent='CMD-0001';},500)</script>")
    contexte = ecran("", _oracle(_commande("CMD-0001")), corps=corps)
    _vaut(contexte, "lignes.0.nom", "Tapis de souris")
    assert _constats(ecran) == [(True, "oracle")]


# ── Refus d'écriture LECTURE_PAGE_ENTIERE (interrupteur TESTPILOT_IA_INFORMEE) ─────────────────────────────────────────────

_ENTETE = "from behave import then\nimport re\nfrom _base_helpers import constater\n\n\n@then('le numéro est lu')\ndef step(context):\n"


@pytest.mark.parametrize("ligne", [
    "    texte = context.page.inner_text('body')",
    "    texte = context.page.locator('body').inner_text()",
    "    texte = context.page.text_content('html')",
    "    texte = context.page.content()",
    "    texte = context.page.evaluate('() => document.body.innerText')",
])
def test_falsifiable_lire_toute_la_page_est_refuse(ligne):
    arbre = __import__("ast").parse(_ENTETE + ligne + "\n    constater(re.search('CMD', texte) is not None, 'x')\n")
    assert w._lecture_de_page_entiere(arbre)


@pytest.mark.parametrize("ligne", [
    "    texte = context.page.locator('#numero-commande').inner_text()",
    "    texte = context.page.get_by_role('status').inner_text()",
    "    context.page.locator('body').click()",
    "    '''on ne lit jamais inner_text(\"body\")'''",
])
def test_lire_un_element_precis_reste_permis(ligne):
    assert not w._lecture_de_page_entiere(__import__("ast").parse(_ENTETE + ligne + "\n"))


def test_le_refus_ne_s_applique_qu_interrupteur_allume(monkeypatch, tmp_path):
    from testpilot.generation.tools import ToolContext

    contenu = _ENTETE + "    texte = context.page.inner_text('body')\n    constater('CMD' in texte, 'x')\n"
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)
    monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    refus = w.write_steps_file(ctx, contenu)
    assert not refus.ok and "LECTURE_PAGE_ENTIERE" in refus.observation and "la valeur affichée pour" in refus.observation
    monkeypatch.delenv(interrupteurs.ENV_IA_INFORMEE)
    assert "LECTURE_PAGE_ENTIERE" not in w.write_steps_file(ctx, contenu).observation



# ── Refus d'écriture ORACLE_OBJET_COMPTE (interrupteur TESTPILOT_IA_INFORMEE) ──────────────────────────────────────────────

_FORMES = {"etat": {"commandes": {"liste": {"numero": "texte"}}, "panier": {"lignes": {"liste": None}}},
           "commandes": {"liste": {"numero": "texte"}}}


def _feature(etape):
    return f"# language: fr\nFonctionnalité: F\n  Scénario: s\n    Soit j'ouvre la page \"/\"\n    Alors {etape}\n"


def test_falsifiable_compter_un_objet_est_refuse_a_l_ecriture():
    sortie = w.requetes_comptees_sur_un_objet(_feature("l'oracle \"etat\" renvoie 0 résultat"), _FORMES)
    assert sortie == [("etat", ["commandes"])]


@pytest.mark.parametrize("etape, formes", [
    ("l'oracle \"commandes\" renvoie 1 résultat", _FORMES),         # une liste se compte
    ("l'oracle \"etat\" renvoie 0 résultat", None),                  # sans relevé : aucun contrôle
    ("l'oracle \"etat\" renvoie 0 résultat", {"etat": "texte"}),      # une valeur : rien
    # Revue (bloquant) : la forme RÉELLE d'une requête en échec à l'exploration — jamais prise pour un objet.
    ("l'oracle \"commandes\" renvoie 1 résultat", {"commandes": {"illisible": "HTTPError"}}),
    ("le champ \"commandes\" de l'oracle \"etat\" compte 1 élément", _FORMES),
])
def test_ce_qui_peut_marcher_n_est_jamais_refuse(etape, formes):
    assert w.requetes_comptees_sur_un_objet(_feature(etape), formes) == []


def test_le_refus_dit_quoi_ecrire_a_la_place(tmp_path):
    from testpilot.generation.tools import ToolContext

    ctx = ToolContext(module_name="m", generated_dir=tmp_path, formes_oracle_relevees=_FORMES)
    refus = w.write_feature_file(ctx, _feature("l'oracle \"etat\" renvoie 0 résultat"))
    assert not refus.ok and "ORACLE_OBJET_COMPTE" in refus.observation
    assert "le champ \"<clé>\" de l'oracle \"etat\" compte <n> élément(s)" in refus.observation
    assert "« commandes »" in refus.observation



def test_les_cles_qui_sont_des_donnees_ne_sont_jamais_montrees():
    """Revue (A51) : un oracle qui range ses données PAR CLÉ ne doit pas les faire sortir dans le message du refus."""
    formes = {"etat": {"alice@x.fr": {"liste": None}, "commandes": {"liste": None}}}
    assert w.requetes_comptees_sur_un_objet(_feature("l'oracle \"etat\" renvoie 0 résultat"), formes) == [
        ("etat", ["commandes"])]


def test_le_refus_de_lecture_de_page_ne_bloque_pas_une_reparation(monkeypatch, tmp_path):
    from testpilot.generation.tools import ToolContext

    contenu = _ENTETE + "    texte = context.page.inner_text('body')\n    constater('CMD' in texte, 'x')\n"
    monkeypatch.setenv(interrupteurs.ENV_IA_INFORMEE, "1")
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, gel_steps=contenu)  # le test approuvé, gelé tel quel
    assert "LECTURE_PAGE_ENTIERE" not in w.write_steps_file(ctx, contenu).observation
