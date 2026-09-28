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


# ── Lot 06 (D6) : profils d'instance — jamais inclus par défaut, opt-in seulement ──────────────

def test_falsifiable_aucun_profil_n_est_inclus_sans_choix_explicite():
    """Un `profil_instance` non fourni (ou vide) ne doit JAMAIS faire fuiter un step de profil —
    ni dans le catalogue, ni dans la copie du runner."""
    labels = {s.label for s in steps_library.catalogue(connector_type="odoo")}
    assert 'je force le nom du ticket à "{value}"' not in labels
    assert 'je clique sur le bouton "{label}" avec accessoires' not in labels

    fichiers = {f.name for f in BehaveRunner(connector_type="odoo")._steps_library_files()}
    assert "sapian.py" not in fichiers and "demo_saucedemo.py" not in fichiers


def test_catalogue_avec_profil_sapian_expose_ses_steps():
    labels = {s.label for s in steps_library.catalogue(connector_type="odoo", profil_instance="sapian")}
    assert 'je force le nom du ticket à "{value}"' in labels
    assert 'je clique sur le bouton "{label}" avec accessoires' not in labels  # profil DIFFÉRENT


def test_catalogue_avec_profil_demo_saucedemo_expose_ses_steps():
    labels = {s.label for s in steps_library.catalogue(connector_type="odoo", profil_instance="demo_saucedemo")}
    assert 'je clique sur le bouton "{label}" avec accessoires' in labels
    assert 'je force le nom du ticket à "{value}"' not in labels


def test_catalogue_un_profil_inconnu_n_ajoute_rien_ni_ne_leve():
    labels_sans = {s.label for s in steps_library.catalogue(connector_type="odoo")}
    labels_inconnu = {s.label for s in steps_library.catalogue(connector_type="odoo",
                                                               profil_instance="n_existe_pas")}
    assert labels_sans == labels_inconnu


def test_assemble_copie_les_deux_volets_du_profil_sapian_sous_un_nom_canonique(tmp_path):
    runner = BehaveRunner(connector_type="odoo", profil_instance="sapian")
    fichiers = runner._profil_files()
    noms = set(fichiers.values())
    assert noms == {"_profil_generic.py", "_profil_connecteur.py"}
    sources = {str(src) for src in fichiers}
    assert any("generic/profils/sapian.py" in s for s in sources)
    assert any("odoo/profils/sapian.py" in s for s in sources)


def test_assemble_profil_demo_saucedemo_n_a_qu_un_volet_generique(tmp_path):
    """`demo_saucedemo` n'a un fichier QUE côté `generic/profils/` — aucun fichier
    `odoo/profils/demo_saucedemo.py` n'existe : `_profil_files` ne doit pas en inventer un."""
    runner = BehaveRunner(connector_type="odoo", profil_instance="demo_saucedemo")
    fichiers = runner._profil_files()
    assert set(fichiers.values()) == {"_profil_generic.py"}


def test_assemble_sans_profil_ne_copie_aucun_fichier_canonique(tmp_path):
    assert BehaveRunner(connector_type="odoo")._profil_files() == {}
    assert BehaveRunner(connector_type="odoo", profil_instance=None)._profil_files() == {}


def test_profils_disponibles_liste_les_profils_reels():
    from testpilot.generation.steps_library import profils_disponibles

    assert "sapian" in profils_disponibles("odoo")
    assert "demo_saucedemo" in profils_disponibles("odoo")


def test_falsifiable_profils_disponibles_ne_liste_pas_un_nom_invente():
    from testpilot.generation.steps_library import profils_disponibles

    assert "profil_qui_n_existe_pas" not in profils_disponibles("odoo")


def test_sans_connecteur_ne_copie_pas_les_steps_d_un_autre_connecteur_que_le_defaut():
    """Lot 07a : `web/` et `odoo/` déclarent le même libellé « je me connecte avec mes identifiants
    utilisateur » — les copier ensemble ferait lever `AmbiguousStep` à un run sans connecteur résolu
    (mesuré : dry-run du harnais en échec). « Tout copier » vaut generic + le connecteur par défaut."""
    runner = BehaveRunner(connector_type=None)
    fichiers = {f.name for f in runner._steps_library_files()}

    assert "_web_steps.py" not in fichiers
    assert "_odoo_steps.py" in fichiers
    assert "_web_steps.py" in {f.name for f in BehaveRunner(connector_type="web")._steps_library_files()}
