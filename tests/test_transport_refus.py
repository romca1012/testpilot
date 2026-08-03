"""Le refus mesuré traverse la frontière de PROCESSUS et devient une règle apprise (§5bis n°1).

Le refus est constaté dans le sous-processus Behave ; la règle doit vivre côté outil. Entre les
deux : un fichier sidecar, puis le store du projet.

⚠️ **Pourquoi un test qui lance un VRAI `BehaveRunner`.** Le premier jet de `0007` B+ lisait son
signal dans la sortie de Behave et se croyait couvert — son test de garde omettait
`environment.py`, donc testait un monde qui n'existe pas en production. Behave capture la sortie
dès qu'un `environment.py` est présent, ce que le runner assemble TOUJOURS. Le même piège guette
ici : ces tests exercent donc la vraie plomberie (variable d'environnement, lecture avant le
`rmtree`, apprentissage), sur une aire de run de forme réelle et sans Odoo.
"""

from __future__ import annotations

import json
from pathlib import Path

from behave_runtime.steps_library import _base_helpers
from testpilot.execution import behave_result
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation import regles_apprises as ra

RACINE = Path(__file__).resolve().parents[1]


def test_les_deux_noms_de_variable_denv_concordent():
    """Le nom est DUPLIQUÉ des deux côtés (importer `_base_helpers` tirerait Playwright dans la
    couche API). Rien dans le code ne tient cet accord — ce test, si."""
    assert _base_helpers.REGLES_REFUS_FILE_ENV == behave_result.REGLES_REFUS_FILE_ENV


def _aire_de_run(tmp_path, *, avec_refus: bool):
    """Aire minimale mais de FORME RÉELLE : `environment.py` assemblé, comme en production."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "environment.py").write_text(
        "# Sa PRÉSENCE suffit à activer la capture de Behave.\n"
        "def before_all(context):\n    pass\n", encoding="utf-8")

    lib = tmp_path / "lib"
    lib.mkdir()
    corps = (
        "    from behave_runtime.steps_library._base_helpers import ("
        "lever_donnee_refusee, RefusMesure, DonneeRefuseeError)\n"
        "    try:\n"
        "        lever_donnee_refusee('refus de garde', [RefusMesure(\n"
        "            route='/fournisseur/creation', champ='tva_intracommunautaire',\n"
        "            type_contrainte='customError', valeur_contrainte='',\n"
        "            valeur_refusee='TestPilot', origine='navigateur',\n"
        "            preuve='uniquement des chiffres')])\n"
        "    except DonneeRefuseeError:\n"
        "        pass\n"          # le scénario reste VERT : c'est tout l'intérêt de la garde
    ) if avec_refus else "    pass\n"

    (lib / "garde_steps.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, r'{RACINE}')\n"
        "from behave import given\n"
        "\n"
        "@given('un refus est mesure')\n"
        "def step_impl(context):\n" + corps,
        encoding="utf-8")

    gen = tmp_path / "gen"
    gen.mkdir()
    (gen / "garde.feature").write_text(
        "# language: fr\n"
        "Fonctionnalité: garde du refus mesuré\n"
        "  Scénario: un scenario VERT qui mesure un refus\n"
        "    Soit un refus est mesure\n", encoding="utf-8")

    return BehaveRunner(runtime_dir=runtime, generated_dir=gen, steps_library_dir=lib,
                        real_timeout=120, project_id=7)


def test_GARDE_un_refus_mesure_dans_un_run_VERT_remonte_jusqu_au_resultat(tmp_path, monkeypatch):
    """⚠️ Échoue sur le code d'avant : `BehaveResult` n'avait pas de `refus_mesures`, et rien ne
    posait la variable d'environnement dans le sous-processus.

    Le scénario est VERT à dessein — c'est le cas où Behave avale tout, et où un signal transporté
    par le log se perdrait sans témoin.

    ⚠️ **`monkeypatch` isole `REGLES_DIR`** — sans ça, ce test avec `project_id=7` (fictif)
    apprenait une VRAIE règle dans le VRAI `data/regles-apprises/projet-7.jsonl` du poste à
    chaque exécution de la suite. Trouvé en observant le fichier grossir pendant un audit.
    """
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    runner = _aire_de_run(tmp_path, avec_refus=True)
    result = runner.real_run("garde")

    assert result.passed == 1, f"le scénario de garde doit être VERT : {result.raw_stdout}"
    assert result.refus_mesures, (
        "un refus mesuré dans un scénario vert doit remonter jusqu'à BehaveResult — s'il ne "
        "remonte plus, la règle n'est jamais apprise et rien ne le dit : corriger le transport, "
        "ne pas neutraliser ce test.")
    assert result.refus_mesures[0]["champ"] == "tva_intracommunautaire"
    assert result.refus_mesures[0]["valeur_refusee"] == "TestPilot"


def test_GARDE_le_refus_devient_une_REGLE_APPRISE_du_projet(tmp_path, monkeypatch):
    """La chaîne complète : sous-processus → sidecar → store du projet.

    ⚠️ C'est le test qui dit si le mécanisme existe vraiment. Sans lui, tout le reste peut être
    vert alors que rien n'est jamais appris.
    """
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    runner = _aire_de_run(tmp_path, avec_refus=True)
    runner.real_run("garde")

    regles = ra.charger(7)
    assert len(regles) == 1
    assert regles[0].champ == "tva_intracommunautaire"
    assert regles[0].route == "/fournisseur/creation"
    assert regles[0].valeur_refusee == "TestPilot"


def test_un_run_VERT_sans_refus_n_apprend_RIEN(tmp_path, monkeypatch):
    """Anti-faux-positif : sans refus, aucun fichier de règles ne doit apparaître."""
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    runner = _aire_de_run(tmp_path, avec_refus=False)
    result = runner.real_run("garde")

    assert result.passed == 1
    assert result.refus_mesures == []
    assert ra.charger(7) == []


def test_GARDE_un_DRY_RUN_n_apprend_JAMAIS(tmp_path, monkeypatch):
    """Un dry-run ne touche pas l'application : il ne mesure rien, il ne peut rien apprendre.

    ⚠️ Sans cette borne, la boucle de réparation — qui fait un dry-run avant chaque run réel —
    polluerait le store avec des refus qui n'ont jamais eu lieu.
    """
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    runner = _aire_de_run(tmp_path, avec_refus=True)
    runner.dry_run("garde")

    assert ra.charger(7) == []


def test_sans_project_id_le_refus_remonte_mais_n_est_pas_appris(tmp_path, monkeypatch):
    """Un annuaire appartient à un PROJET (`0005`). Sans projet, on ne sait pas à qui l'attribuer —
    et on préfère ne rien apprendre plutôt que de l'attribuer au hasard."""
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    runner = _aire_de_run(tmp_path, avec_refus=True)
    runner.project_id = None
    result = runner.real_run("garde")

    assert result.refus_mesures, "le fait reste mesuré et lisible dans le résultat"
    assert ra.charger(7) == []


def test_le_sidecar_est_ARCHIVE_avec_les_autres_artefacts(tmp_path, monkeypatch):
    """La trace brute doit rester consultable : pourquoi telle valeur est interdite depuis ce run."""
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    artefacts = tmp_path / "artefacts"
    runner = _aire_de_run(tmp_path, avec_refus=True)
    runner.cibler_artefacts(artefacts)
    runner.real_run("garde")

    archive = artefacts / "execution.refus-mesures.jsonl"
    assert archive.exists()
    assert json.loads(archive.read_text(encoding="utf-8").splitlines()[0])["champ"] \
        == "tva_intracommunautaire"


def test_read_refus_mesures_est_TOLERANT(tmp_path):
    """Une ligne abîmée est sautée, un fichier absent rend une liste vide — jamais d'exception."""
    fichier = tmp_path / "refus.jsonl"
    fichier.write_text('{"champ": "a"}\nceci n\'est pas du JSON\n{"champ": "b"}\n',
                       encoding="utf-8")
    assert [m["champ"] for m in behave_result.read_refus_mesures(fichier)] == ["a", "b"]
    assert behave_result.read_refus_mesures(tmp_path / "absent.jsonl") == []
