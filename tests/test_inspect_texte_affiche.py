"""Rendu de `inspect_page_snapshot` à l'agent : le texte affiché est distingué du nom accessible (2026-10-08)."""

from __future__ import annotations

from types import SimpleNamespace

from testpilot.generation.tools import inspect as outil


def _ctx(elements):
    connecteur = SimpleNamespace(inspect_page_snapshot=lambda url: {"url": url, "elements": elements, "error": ""})
    return SimpleNamespace(connector=connecteur)


def test_le_texte_affiche_est_montre_quand_il_differe_du_nom_accessible():
    sortie = outil.inspect_page_snapshot(_ctx([
        {"role": "button", "nom": "Ajouter Clavier mécanique au panier", "type": "submit", "texte": "Ajouter"}]), "/produits")

    texte = sortie.observation
    assert "texte affiché : « Ajouter »" in texte and "Légende" in texte and ":has-text()" in texte


def test_sans_difference_le_rendu_est_celui_d_avant_et_sans_legende():
    sortie = outil.inspect_page_snapshot(_ctx([{"role": "button", "nom": "Valider", "type": ""}]), "/x")

    texte = sortie.observation
    assert "- button « Valider »" in texte and "Légende" not in texte and "texte affiché" not in texte
