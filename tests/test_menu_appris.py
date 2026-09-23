"""Le store de la mémoire de libellés de menu APPRIS (Lot 2 du plan de fiabilisation, 2026-09-23).

Ce que ces tests protègent, dans l'ordre d'importance :

1. **le dernier libellé écrit pour un segment fait foi** — un run qui reboucle sur le même
   segment (menu parent puis destination finale) doit voir le libellé le plus précis l'emporter ;
2. **les projets ne partagent pas leur mémoire** — un libellé appris sur une application n'apprend
   rien sur une autre ;
3. un fichier abîmé n'empêche pas un run de tourner ;
4. un fait sans segment ni libellé est ignoré, jamais écrit à moitié.
"""

from __future__ import annotations

import json

import pytest

from testpilot.generation import menu_appris as ma


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isole le store dans un dossier jetable et vide le cache entre deux tests."""
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    ma._lire.cache_clear()
    yield tmp_path
    ma._lire.cache_clear()


def _fait(segment="All Tickets", libelle="Tous les tickets", chemin="Assistance / All Tickets"):
    return {"segment_original": segment, "libelle_reel": libelle, "menu_path": chemin}


# ── Écriture et relecture ────────────────────────────────────────────────────

def test_un_premier_libelle_est_ecrit_et_relu(store):
    assert ma.enregistrer(1, [_fait()], execution_id=188) == 1
    connus = ma.charger(1)
    assert connus["All Tickets"].libelle_reel == "Tous les tickets"
    assert connus["All Tickets"].menu_path == "Assistance / All Tickets"


def test_le_fichier_porte_execution_id_et_version_de_format(store):
    ma.enregistrer(1, [_fait()], execution_id=188)
    ligne = json.loads(ma.chemin(1).read_text(encoding="utf-8").splitlines()[0])
    assert ligne["execution_id"] == 188
    assert ligne["v"] == ma.FORMAT_VERSION
    assert ligne["mesure_le"]


def test_un_projet_sans_fichier_rend_un_dictionnaire_vide_sans_lever(store):
    assert ma.charger(999) == {}


# ── Dernier écrit gagne (le reboucle de navigate_menu sur un même segment) ───

def test_un_second_clic_sur_le_meme_segment_ecrase_le_premier(store):
    """`navigate_menu` reboucle sur le MÊME segment quand le premier clic n'ouvre qu'un menu
    parent (« Tickets ») avant de trouver la vraie destination (« Tous les tickets ») — le
    libellé le plus récent, le plus précis, doit l'emporter à la lecture."""
    ma.enregistrer(1, [_fait(segment="All Tickets", libelle="Tickets")])
    ma.enregistrer(1, [_fait(segment="All Tickets", libelle="Tous les tickets")])
    assert ma.charger(1)["All Tickets"].libelle_reel == "Tous les tickets"


def test_deux_segments_distincts_ne_se_confondent_pas(store):
    ma.enregistrer(1, [_fait(segment="Surveys", libelle="Sondages"),
                       _fait(segment="All Tickets", libelle="Tous les tickets")])
    connus = ma.charger(1)
    assert connus["Surveys"].libelle_reel == "Sondages"
    assert connus["All Tickets"].libelle_reel == "Tous les tickets"


def test_les_projets_ne_partagent_pas_leur_memoire(store):
    ma.enregistrer(1, [_fait()])
    assert ma.charger(2) == {}


def test_le_cache_est_invalide_quand_le_fichier_change(store):
    ma.enregistrer(1, [_fait(segment="Surveys", libelle="Sondages")])
    assert len(ma.charger(1)) == 1
    ma.enregistrer(1, [_fait(segment="All Tickets", libelle="Tous les tickets")])
    assert len(ma.charger(1)) == 2, "un cache non invalidé servirait la version d'avant"


# ── Tolérance ─────────────────────────────────────────────────────────────────

def test_un_fichier_illisible_ne_fait_pas_tomber_l_enregistrement(store):
    ma.enregistrer(1, [_fait()])
    with ma.chemin(1).open("a", encoding="utf-8") as flux:
        flux.write("{ceci n'est pas du JSON\n")
    ma._lire.cache_clear()
    assert len(ma.charger(1)) == 1, "la ligne saine doit survivre à la ligne abîmée"


def test_un_fait_sans_segment_ni_libelle_est_ignore(store):
    assert ma.enregistrer(1, [{"segment_original": "", "libelle_reel": "Sondages"}]) == 0
    assert ma.enregistrer(1, [{"segment_original": "Surveys", "libelle_reel": ""}]) == 0
    assert ma.charger(1) == {}


def test_sans_project_id_rien_n_est_ecrit(store):
    assert ma.enregistrer(None, [_fait()]) == 0
    assert not ma.chemin(1).exists()


def test_sans_fait_rien_n_est_ecrit(store):
    assert ma.enregistrer(1, []) == 0
    assert not ma.chemin(1).exists()


def test_enregistrer_accepte_un_objet_pas_seulement_un_dict(store):
    """Même tolérance que `selector_memory.enregistrer` : un objet portant les mêmes attributs
    doit fonctionner, pas seulement un dictionnaire brut — c'est ce que `navigate_menu` transmet
    depuis son sidecar relu (des dicts en pratique, mais le contrat reste large)."""
    from dataclasses import dataclass

    @dataclass
    class _Fait:
        segment_original: str
        libelle_reel: str
        menu_path: str = ""

    assert ma.enregistrer(1, [_Fait(segment_original="Surveys", libelle_reel="Sondages")]) == 1
    assert ma.charger(1)["Surveys"].libelle_reel == "Sondages"
