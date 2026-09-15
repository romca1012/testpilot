"""Le palier de résolution d'un champ traverse la frontière de PROCESSUS et devient une mémoire de
dérive du projet (§1.2 du plan de consolidation, audit « Le pari Mabl/Testim » 2026-09-15).

Le palier est constaté dans le sous-processus Behave ; la comparaison et la mémoire doivent vivre
côté outil. Entre les deux : un fichier sidecar, puis le store du projet — même schéma de preuve
que `test_transport_refus.py` (§5bis n°1), pour la même raison : un scénario VERT ne recrache rien
sur stdout/stderr/logging dès qu'un `environment.py` est présent, ce que `BehaveRunner._assemble`
fait TOUJOURS. Ces tests lancent donc un VRAI `BehaveRunner`, sur une aire de forme réelle.
"""

from __future__ import annotations

from pathlib import Path

from behave_runtime.steps_library import _base_helpers
from testpilot.execution import behave_result
from testpilot.execution import selector_memory as sm
from testpilot.execution.behave_runner import BehaveRunner

RACINE = Path(__file__).resolve().parents[1]


def test_les_deux_noms_de_variable_denv_concordent():
    """Le nom est DUPLIQUÉ des deux côtés (importer `_base_helpers` tirerait Playwright dans la
    couche API). Rien dans le code ne tient cet accord — ce test, si."""
    assert _base_helpers.SELECTOR_TIER_FILE_ENV == behave_result.SELECTOR_TIER_FILE_ENV


def _aire_de_run(tmp_path, *, tier: str):
    """Aire minimale mais de FORME RÉELLE : `environment.py` assemblé, comme en production.

    Le step appelle `_record_selector_tier` DIRECTEMENT plutôt que `locate_field` : aucun
    navigateur n'est nécessaire pour prouver le TRANSPORT (sidecar → résultat → mémoire), et
    `locate_field` lui-même est déjà couvert séparément (`test_select_field_value_sans_name.py`).
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "environment.py").write_text(
        "# Sa PRÉSENCE suffit à activer la capture de Behave.\n"
        "def before_all(context):\n    pass\n", encoding="utf-8")

    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "garde_steps.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, r'{RACINE}')\n"
        "from behave import given\n"
        "from behave_runtime.steps_library._base_helpers import _record_selector_tier\n"
        "\n"
        "@given('un champ est resolu')\n"
        "def step_impl(context):\n"
        f"    _record_selector_tier('rib', '{tier}')\n",
        encoding="utf-8")

    gen = tmp_path / "gen"
    gen.mkdir(parents=True)
    (gen / "garde.feature").write_text(
        "# language: fr\n"
        "Fonctionnalité: garde de la resolution de selecteur\n"
        "  Scénario: un scenario VERT qui resout un champ\n"
        "    Soit un champ est resolu\n", encoding="utf-8")

    return BehaveRunner(runtime_dir=runtime, generated_dir=gen, steps_library_dir=lib,
                        real_timeout=120, project_id=7)


def test_GARDE_une_resolution_dans_un_run_VERT_remonte_jusqu_au_resultat(tmp_path, monkeypatch):
    """⚠️ Échoue sur le code d'avant : `BehaveResult` n'avait pas de `selector_tiers`, et rien ne
    posait la variable d'environnement dans le sous-processus."""
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    runner = _aire_de_run(tmp_path, tier="name")
    result = runner.real_run("garde")

    assert result.passed == 1, f"le scénario de garde doit être VERT : {result.raw_stdout}"
    assert result.selector_tiers == [{"ident": "rib", "tier": "name"}]


def test_GARDE_un_changement_de_palier_devient_une_DERIVE_du_projet(tmp_path, monkeypatch):
    """La chaîne complète, sur DEUX runs successifs : sous-processus → sidecar → store du projet
    → dérive détectée au second run. C'est le test qui dit si le mécanisme existe vraiment."""
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()

    runner = _aire_de_run(tmp_path, tier="name")
    runner.real_run("garde")

    connues = sm.charger(7)
    assert connues[("garde", "rib")].tier == "name"

    # Le champ « rib » se résout désormais par son libellé — l'application a changé sous ce champ.
    # Deuxième aire DISTINCTE (même projet, même module) : `_aire_de_run` construit ses dossiers
    # sous `tmp_path`, que le premier appel a déjà peuplé.
    runner_suivant = _aire_de_run(tmp_path / "second-run", tier="label")
    runner_suivant.real_run("garde")

    connues = sm.charger(7)
    assert connues[("garde", "rib")].tier == "label", "la mémoire doit refléter le DERNIER palier"


def test_GARDE_le_meme_palier_deux_fois_ne_journalise_aucune_derive(tmp_path, monkeypatch, caplog):
    """Anti-faux-positif : un champ stable d'un run à l'autre ne doit produire aucune alerte."""
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()

    runner = _aire_de_run(tmp_path, tier="name")
    runner.real_run("garde")
    with caplog.at_level("WARNING", logger="testpilot.execution.behave_runner"):
        runner.real_run("garde")

    assert "dérive de sélecteur" not in caplog.text


def test_GARDE_un_DRY_RUN_n_ecrit_JAMAIS_dans_la_memoire(tmp_path, monkeypatch):
    """Un dry-run ne touche pas l'application : il ne mesure rien, il ne peut rien enregistrer.

    ⚠️ Sans cette borne, la boucle de réparation — qui fait un dry-run avant chaque run réel —
    pollueraient la mémoire de dérive avec des résolutions qui n'ont jamais eu lieu."""
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()

    runner = _aire_de_run(tmp_path, tier="name")
    runner.dry_run("garde")

    assert sm.charger(7) == {}


def test_sans_project_id_la_resolution_remonte_mais_n_est_pas_memorisee(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()

    runner = _aire_de_run(tmp_path, tier="name")
    runner.project_id = None
    result = runner.real_run("garde")

    assert result.selector_tiers, "le fait reste mesuré et lisible dans le résultat"
    assert sm.charger(7) == {}


def test_le_sidecar_est_ARCHIVE_avec_les_autres_artefacts(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "MEMOIRE_DIR", tmp_path / "selecteurs")
    sm._lire.cache_clear()

    artefacts = tmp_path / "artefacts"
    runner = _aire_de_run(tmp_path, tier="name")
    runner.cibler_artefacts(artefacts)
    runner.real_run("garde")

    archive = artefacts / "execution.paliers-de-selecteur.jsonl"
    assert archive.exists()


def test_read_selector_tiers_est_TOLERANT(tmp_path):
    fichier = tmp_path / "tiers.jsonl"
    fichier.write_text('{"ident": "a", "tier": "name"}\nceci n\'est pas du JSON\n'
                       '{"ident": "b", "tier": "label"}\n', encoding="utf-8")
    assert [m["ident"] for m in behave_result.read_selector_tiers(fichier)] == ["a", "b"]
    assert behave_result.read_selector_tiers(tmp_path / "absent.jsonl") == []
