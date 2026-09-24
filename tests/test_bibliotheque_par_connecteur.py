"""Bibliothèque de steps rangée par connecteur (audit DA, 2026-08-13) — decision liée à 0003.

Avant, `behave_runtime/steps_library/` était un dossier PLAT mélangeant des steps vraiment
génériques et des steps spécifiques à Odoo, sans distinction ni signalement — un fichier nommé
`_generic_steps.py` affirmait même « ZÉRO step spécifique » alors qu'il appelait `context.odoo.env`
directement. Rangé maintenant en `generic/` (portable, tout connecteur) + `odoo/` (spécifique).

Ces tests gardent trois invariants :
- le catalogue SANS scope reste la même union qu'avant la restructuration (aucun step perdu) ;
- le catalogue SCOPÉ à un connecteur ne contient jamais les steps d'un AUTRE connecteur ;
- la copie effectuée par `BehaveRunner._assemble()` (via `_steps_library_files`) suit la même
  règle, ET copie toujours les helpers de la racine (sans quoi les imports `from _base_helpers
  import ...` des steps copiés casseraient au runtime).
"""

from pathlib import Path

from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation import steps_library


def test_catalogue_sans_scope_reste_une_union_complete():
    """Repli sûr : un appelant qui n'a pas encore de connecteur résolu ne perd aucun step."""
    catalogue = steps_library.catalogue()
    assert len(catalogue) > 10, "la bibliothèque partagée doit être détectée"
    sources = {s.source for s in catalogue}
    assert any(s.startswith("generic/") for s in sources)
    assert any(s.startswith("odoo/") for s in sources)


def test_catalogue_odoo_contient_les_steps_odoo():
    catalogue = steps_library.catalogue(connector_type="odoo")
    labels = {s.label for s in catalogue}
    assert 'je navigue vers le menu Odoo "{menu_path}"' in labels
    assert 'je me connecte avec mes identifiants utilisateur' in labels


def test_catalogue_odoo_contient_aussi_le_socle_generique():
    """Le scope par connecteur, c'est generic/ + <connecteur> — jamais <connecteur> seul."""
    catalogue = steps_library.catalogue(connector_type="odoo")
    labels = {s.label for s in catalogue}
    assert 'je clique sur le bouton "{label}"' in labels


def test_catalogue_scope_a_un_connecteur_inexistant_ne_contient_pas_odoo():
    """Un connecteur qui n'a pas encore de sous-dossier ne voit QUE le socle générique — jamais
    les steps Odoo, qui n'auraient aucun sens pour lui (pas de risque de collision à tort)."""
    catalogue = steps_library.catalogue(connector_type="sap_pas_encore_cree")
    labels = {s.label for s in catalogue}
    assert 'je navigue vers le menu Odoo "{menu_path}"' not in labels
    assert 'je clique sur le bouton "{label}"' in labels  # le socle générique reste visible


def test_reserved_labels_suit_le_meme_scope():
    reserves_odoo = steps_library.reserved_labels(connector_type="odoo")
    reserves_sans_scope = steps_library.reserved_labels()
    assert reserves_odoo <= reserves_sans_scope
    assert 'je navigue vers le menu Odoo "{menu_path}"' in reserves_odoo


def test_assemble_copie_generic_et_le_connecteur_actif(tmp_path):
    runner = BehaveRunner(connector_type="odoo")
    fichiers = {f.name for f in runner._steps_library_files()}
    assert "_generic_steps.py" in fichiers
    assert "_odoo_steps.py" in fichiers
    assert "_odoo_background_steps.py" in fichiers
    # Toujours copiés, quel que soit le connecteur : les steps importent depuis ces helpers.
    assert "_base_helpers.py" in fichiers
    assert "_accent_matcher.py" in fichiers


def test_assemble_sans_connecteur_copie_tout():
    runner = BehaveRunner(connector_type=None)
    fichiers = {f.name for f in runner._steps_library_files()}
    assert {"_generic_steps.py", "_odoo_steps.py", "_odoo_background_steps.py",
            "_base_helpers.py", "_accent_matcher.py"} <= fichiers


def test_assemble_scope_a_un_connecteur_inexistant_exclut_odoo(tmp_path):
    runner = BehaveRunner(connector_type="sap_pas_encore_cree")
    fichiers = {f.name for f in runner._steps_library_files()}
    assert "_odoo_steps.py" not in fichiers
    assert "_odoo_background_steps.py" not in fichiers
    assert "_generic_steps.py" in fichiers
    assert "_base_helpers.py" in fichiers  # toujours copié


def test_catalogue_odoo_scope_egale_le_catalogue_sans_scope(tmp_path):
    """Phase 1c — régression zéro sur le taux de blocage : aujourd'hui, seul Odoo existe, donc
    scoper à "odoo" (generic/ + odoo/) doit rendre EXACTEMENT le même ensemble de labels que le
    catalogue non scopé — aucun step perdu, aucun faux positif `AmbiguousStep` en plus."""
    labels_scopes = {s.label for s in steps_library.catalogue(connector_type="odoo")}
    labels_sans_scope = {s.label for s in steps_library.catalogue()}
    assert labels_scopes == labels_sans_scope


def test_sans_connecteur_ne_copie_pas_les_steps_d_un_autre_connecteur_que_le_defaut():
    """Lot 07a : `web/` et `odoo/` déclarent le même libellé « je me connecte avec mes identifiants
    utilisateur » — les copier ensemble ferait lever `AmbiguousStep` à un run sans connecteur résolu
    (mesuré : dry-run du harnais en échec). « Tout copier » vaut generic + le connecteur par défaut."""
    runner = BehaveRunner(connector_type=None)
    fichiers = {f.name for f in runner._steps_library_files()}

    assert "_web_steps.py" not in fichiers
    assert "_odoo_steps.py" in fichiers
    assert "_web_steps.py" in {f.name for f in BehaveRunner(connector_type="web")._steps_library_files()}
