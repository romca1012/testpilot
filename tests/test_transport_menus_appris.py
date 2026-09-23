"""Le libellé de menu APPRIS par le repli adaptatif de `navigate_menu` traverse la frontière de
PROCESSUS et devient une mémoire de PROJET (Lot 2 du plan de fiabilisation, 2026-09-23).

Le libellé est constaté dans le sous-processus Behave ; la comparaison n'existe pas ici (contrairement
à `selector_memory`, ce n'est pas une dérive à détecter mais un fait à retenir tel quel) — la
persistance doit malgré tout vivre côté outil. Entre les deux : un fichier sidecar, puis le store du
projet — même schéma de preuve que `test_transport_derive_selecteurs.py`, pour la même raison : un
scénario VERT ne recrache rien sur stdout/stderr/logging dès qu'un `environment.py` est présent, ce
que `BehaveRunner._assemble` fait TOUJOURS. Ces tests lancent donc un VRAI `BehaveRunner`, sur une
aire de forme réelle.
"""

from __future__ import annotations

from pathlib import Path

from behave_runtime.steps_library import _base_helpers
from testpilot.execution import behave_result
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation import menu_appris as ma

RACINE = Path(__file__).resolve().parents[1]


def test_les_deux_noms_de_variable_denv_concordent():
    """Le nom est DUPLIQUÉ des deux côtés (importer `_base_helpers` tirerait Playwright dans la
    couche API). Rien dans le code ne tient cet accord — ce test, si."""
    assert _base_helpers.MENU_LEARNED_FILE_ENV == behave_result.MENU_LEARNED_FILE_ENV


def _aire_de_run(tmp_path, *, libelle_reel: str):
    """Aire minimale mais de FORME RÉELLE : `environment.py` assemblé, comme en production.

    Le step appelle `_record_menu_appris` DIRECTEMENT plutôt que `navigate_menu` : aucun
    navigateur n'est nécessaire pour prouver le TRANSPORT (sidecar → résultat → mémoire) — la
    résolution adaptative elle-même est déjà couverte séparément (`test_resolution_adaptative.py`).
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
        "from behave_runtime.steps_library._base_helpers import _record_menu_appris\n"
        "\n"
        "@given('un menu est resolu adaptativement')\n"
        "def step_impl(context):\n"
        f"    _record_menu_appris('All Tickets', '{libelle_reel}', "
        "'Assistance / All Tickets')\n",
        encoding="utf-8")

    gen = tmp_path / "gen"
    gen.mkdir(parents=True)
    (gen / "garde.feature").write_text(
        "# language: fr\n"
        "Fonctionnalité: garde de la resolution de menu adaptative\n"
        "  Scénario: un scenario VERT qui resout un menu adaptativement\n"
        "    Soit un menu est resolu adaptativement\n", encoding="utf-8")

    return BehaveRunner(runtime_dir=runtime, generated_dir=gen, steps_library_dir=lib,
                        real_timeout=120, project_id=7)


def test_GARDE_un_libelle_appris_dans_un_run_VERT_remonte_jusqu_au_resultat(tmp_path, monkeypatch):
    """⚠️ Échoue sur le code d'avant : `BehaveResult` n'avait pas de `menus_appris`, et rien ne
    posait la variable d'environnement dans le sous-processus."""
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    runner = _aire_de_run(tmp_path, libelle_reel="Tous les tickets")
    result = runner.real_run("garde")

    assert result.passed == 1, f"le scénario de garde doit être VERT : {result.raw_stdout}"
    assert result.menus_appris == [{"segment_original": "All Tickets",
                                    "libelle_reel": "Tous les tickets",
                                    "menu_path": "Assistance / All Tickets"}]


def test_GARDE_le_libelle_appris_devient_lisible_par_la_generation(tmp_path, monkeypatch):
    """La chaîne complète : sous-processus → sidecar → store du projet → relu par
    `menu_appris.charger`, exactement ce que `_section_modeles_backoffice` (`prompt.py`) lit."""
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    ma._lire.cache_clear()

    runner = _aire_de_run(tmp_path, libelle_reel="Tous les tickets")
    runner.real_run("garde")

    connus = ma.charger(7)
    assert connus["All Tickets"].libelle_reel == "Tous les tickets"
    assert connus["All Tickets"].menu_path == "Assistance / All Tickets"


def test_GARDE_un_DRY_RUN_n_ecrit_JAMAIS_dans_la_memoire(tmp_path, monkeypatch):
    """Un dry-run ne touche pas l'application : aucune navigation n'y a réellement lieu.

    ⚠️ Sans cette borne, la boucle de réparation — qui fait un dry-run avant chaque run réel —
    pollueraient la mémoire de menus avec des résolutions qui n'ont jamais eu lieu."""
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    ma._lire.cache_clear()

    runner = _aire_de_run(tmp_path, libelle_reel="Tous les tickets")
    runner.dry_run("garde")

    assert ma.charger(7) == {}


def test_sans_project_id_le_libelle_remonte_mais_n_est_pas_memorise(tmp_path, monkeypatch):
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    ma._lire.cache_clear()

    runner = _aire_de_run(tmp_path, libelle_reel="Tous les tickets")
    runner.project_id = None
    result = runner.real_run("garde")

    assert result.menus_appris, "le fait reste mesuré et lisible dans le résultat"
    assert ma.charger(7) == {}


def test_le_sidecar_est_ARCHIVE_avec_les_autres_artefacts(tmp_path, monkeypatch):
    monkeypatch.setattr(ma, "MEMOIRE_DIR", tmp_path / "menus-appris")
    ma._lire.cache_clear()

    artefacts = tmp_path / "artefacts"
    runner = _aire_de_run(tmp_path, libelle_reel="Tous les tickets")
    runner.cibler_artefacts(artefacts)
    runner.real_run("garde")

    archive = artefacts / "execution.menus-appris.jsonl"
    assert archive.exists()


def test_read_menus_appris_est_TOLERANT(tmp_path):
    fichier = tmp_path / "menus.jsonl"
    fichier.write_text(
        '{"segment_original": "Surveys", "libelle_reel": "Sondages"}\n'
        "ceci n'est pas du JSON\n"
        '{"segment_original": "All Tickets", "libelle_reel": "Tous les tickets"}\n',
        encoding="utf-8")
    lus = behave_result.read_menus_appris(fichier)
    assert [f["segment_original"] for f in lus] == ["Surveys", "All Tickets"]
    assert behave_result.read_menus_appris(tmp_path / "absent.jsonl") == []
