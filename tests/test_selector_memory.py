"""Le store de la mémoire de dérive des sélecteurs (§1.2 du plan de consolidation).

Ce que ces tests protègent, dans l'ordre d'importance :

1. **une dérive n'est détectée QUE contre le dernier palier connu** — jamais entre deux champs
   du même run, jamais devinée sans historique préalable ;
2. **un palier identique d'un run à l'autre ne déclenche aucune fausse alerte** — c'est le cas
   nominal, pas une exception ;
3. **projet, module et identifiant forment ensemble la clé** — un même identifiant dans deux
   modules différents ne doit jamais se confondre ;
4. un fichier abîmé n'empêche pas un run de tourner.
"""

from __future__ import annotations

import json

import pytest

from testpilot.execution import selector_memory as sm


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isole le store dans un dossier jetable et vide le cache entre deux tests."""
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()
    yield tmp_path
    sm._lire.cache_clear()


def _resolution(ident="rib", tier="name"):
    return {"ident": ident, "tier": tier}


# ── Écriture et relecture ────────────────────────────────────────────────────

def test_une_premiere_resolution_est_ecrite_sans_derive(store):
    """Rien à comparer la première fois : aucun historique, donc aucune dérive possible."""
    derives = sm.enregistrer(1, "demande_materiel", [_resolution()], execution_id=128)
    assert derives == []
    connues = sm.charger(1)
    assert connues[("demande_materiel", "rib")].tier == "name"


def test_le_fichier_porte_execution_id_et_version_de_format(store):
    sm.enregistrer(1, "demande_materiel", [_resolution()], execution_id=128)
    ligne = json.loads(sm.chemin(1).read_text(encoding="utf-8").splitlines()[0])
    assert ligne["execution_id"] == 128
    assert ligne["v"] == sm.FORMAT_VERSION
    assert ligne["mesure_le"]
    assert ligne["module"] == "demande_materiel"


def test_un_projet_sans_fichier_rend_un_dictionnaire_vide_sans_lever(store):
    assert sm.charger(999) == {}


# ── La dérive : le cœur du mécanisme ─────────────────────────────────────────

def test_le_meme_palier_deux_fois_ne_declenche_aucune_fausse_alerte(store):
    sm.enregistrer(1, "demande_materiel", [_resolution(tier="name")])
    derives = sm.enregistrer(1, "demande_materiel", [_resolution(tier="name")])
    assert derives == []


def test_un_changement_de_palier_est_detecte(store):
    sm.enregistrer(1, "demande_materiel", [_resolution(tier="name")])
    derives = sm.enregistrer(1, "demande_materiel", [_resolution(tier="label")])
    assert len(derives) == 1
    assert derives[0] == sm.Derive(module="demande_materiel", ident="rib",
                                   ancien_tier="name", nouveau_tier="label")


def test_deux_champs_du_meme_run_ne_se_comparent_jamais_entre_eux(store):
    """Une dérive se lit contre L'HISTORIQUE, jamais contre un autre champ résolu au même run."""
    derives = sm.enregistrer(1, "demande_materiel",
                             [_resolution("rib", "name"), _resolution("agence", "label")])
    assert derives == []


def test_le_meme_identifiant_dans_deux_modules_ne_se_confond_pas(store):
    sm.enregistrer(1, "demande_materiel", [_resolution(tier="name")])
    derives = sm.enregistrer(1, "reclamation", [_resolution(tier="label")])
    assert derives == [], "modules différents : aucun historique commun, donc aucune dérive"
    assert sm.charger(1)[("demande_materiel", "rib")].tier == "name"
    assert sm.charger(1)[("reclamation", "rib")].tier == "label"


def test_les_projets_ne_partagent_pas_leur_memoire(store):
    sm.enregistrer(1, "demande_materiel", [_resolution(tier="name")])
    assert sm.charger(2) == {}


def test_le_cache_est_invalide_quand_le_fichier_change(store):
    sm.enregistrer(1, "demande_materiel", [_resolution("rib", "name")])
    assert len(sm.charger(1)) == 1
    sm.enregistrer(1, "demande_materiel", [_resolution("agence", "name")])
    assert len(sm.charger(1)) == 2, "un cache non invalidé servirait la version d'avant"


# ── Tolérance ─────────────────────────────────────────────────────────────────

def test_un_fichier_illisible_ne_fait_pas_tomber_l_enregistrement(store):
    sm.enregistrer(1, "demande_materiel", [_resolution("rib", "name")])
    with sm.chemin(1).open("a", encoding="utf-8") as flux:
        flux.write("{ceci n'est pas du JSON\n")
    sm._lire.cache_clear()
    connues = sm.charger(1)
    assert len(connues) == 1, "la ligne saine doit survivre à la ligne abîmée"


def test_une_resolution_sans_ident_ni_tier_est_ignoree(store):
    assert sm.enregistrer(1, "demande_materiel", [{"ident": "", "tier": "name"}]) == []
    assert sm.charger(1) == {}


def test_sans_project_id_rien_n_est_ecrit(store):
    assert sm.enregistrer(None, "demande_materiel", [_resolution()]) == []
    assert not sm.chemin(1).exists()


def test_sans_resolution_rien_n_est_ecrit(store):
    assert sm.enregistrer(1, "demande_materiel", []) == []
    assert not sm.chemin(1).exists()


def test_enregistrer_accepte_un_objet_pas_seulement_un_dict(store):
    """Même tolérance que `regles_apprises.enregistrer` : un objet portant les mêmes attributs
    doit fonctionner, pas seulement un dictionnaire brut."""
    from dataclasses import dataclass

    @dataclass
    class _Fait:
        ident: str
        tier: str

    derives = sm.enregistrer(1, "demande_materiel", [_Fait(ident="rib", tier="name")])
    assert derives == []
    assert sm.charger(1)[("demande_materiel", "rib")].tier == "name"
