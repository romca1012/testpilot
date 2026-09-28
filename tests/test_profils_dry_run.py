"""Lot 06 (D6) — non-régression RÉELLE (`--dry-run` Behave, pas une lecture de code) : un `.feature`
qui utilise les steps déplacés vers un profil résout SEULEMENT quand ce profil est choisi — la
preuve la plus proche d'un rejeu de cas réel que ce cloud, sans base porteur, peut produire (voir
le rapport du lot : la vraie non-régression, sur les `.feature` APPROUVÉS du porteur, reste à faire
par lui une fois `scripts/migration_lot06_profil_instance.py` appliqué sur sa base réelle).
"""

from __future__ import annotations

from testpilot import config
from testpilot.execution.behave_runner import BehaveRunner

_FEATURE_SAPIAN = """# language: fr
Fonctionnalité: Sonde du profil Sapian
  Scénario: le step du profil resout
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Quand je clique sur le bouton "Nouveau"
    Et je force le nom du ticket à "Ticket de sonde"
"""

_FEATURE_DEMO_SAUCEDEMO = """# language: fr
Fonctionnalité: Sonde du profil demo_saucedemo
  Scénario: le step du profil resout
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Quand je clique sur le bouton "Ajouter" avec accessoires
"""


def _dry_run(tmp_path, module_name: str, feature: str, *, profil_instance: str | None):
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    (generated / f"{module_name}.feature").write_text(feature, encoding="utf-8")
    runner = BehaveRunner(
        runtime_dir=config.BEHAVE_RUNTIME_DIR, generated_dir=generated,
        steps_library_dir=config.STEPS_LIBRARY_DIR, connector_type="odoo",
        profil_instance=profil_instance)
    return runner.dry_run(module_name)


def test_le_profil_sapian_resout_son_step_en_dry_run(tmp_path):
    result = _dry_run(tmp_path, "sonde_sapian", _FEATURE_SAPIAN, profil_instance="sapian")

    assert not result.undefined_steps, f"steps non résolus : {result.undefined_steps}"
    assert not result.ambiguous_steps, f"steps ambigus : {result.ambiguous_steps}"
    assert result.success, f"dry-run échoué (rc={result.returncode})\n{result.raw_stderr}"


def test_falsifiable_sans_le_profil_sapian_le_meme_step_est_indefini(tmp_path):
    """La preuve que le succès ci-dessus vient RÉELLEMENT du profil, pas d'un accident : sans lui,
    Behave rapporte le step comme `undefined` (le socle ne le connaît plus, lot 06). `success`/
    `returncode`, pas `undefined_steps` : vérifié en clair (sortie brute du sous-processus) que
    Behave écrit bien « 1 undefined » dans ce cas précis, mais le formatter JSON maison ne le
    reporte pas toujours dans `undefined_steps` pour un dry-run à un seul scénario — signal
    ROBUSTE retenu ici, celui que `derive_verdict` lit réellement (`dry_run_passed`)."""
    result = _dry_run(tmp_path, "sonde_sapian_sans_profil", _FEATURE_SAPIAN, profil_instance=None)

    assert result.success is False and result.returncode != 0


def test_le_profil_demo_saucedemo_resout_son_step_en_dry_run(tmp_path):
    result = _dry_run(tmp_path, "sonde_demo", _FEATURE_DEMO_SAUCEDEMO, profil_instance="demo_saucedemo")

    assert not result.undefined_steps, f"steps non résolus : {result.undefined_steps}"
    assert not result.ambiguous_steps, f"steps ambigus : {result.ambiguous_steps}"
    assert result.success, f"dry-run échoué (rc={result.returncode})\n{result.raw_stderr}"


def test_falsifiable_sans_le_profil_demo_saucedemo_le_meme_step_est_indefini(tmp_path):
    result = _dry_run(tmp_path, "sonde_demo_sans_profil", _FEATURE_DEMO_SAUCEDEMO, profil_instance=None)

    assert result.success is False and result.returncode != 0


def test_le_profil_sapian_n_expose_pas_le_step_du_profil_demo_saucedemo(tmp_path):
    """Un profil n'inclut QUE ses propres steps — jamais ceux d'un autre profil."""
    result = _dry_run(tmp_path, "sonde_croisee", _FEATURE_DEMO_SAUCEDEMO, profil_instance="sapian")

    assert result.success is False and result.returncode != 0
