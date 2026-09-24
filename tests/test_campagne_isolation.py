"""Isolation des campagnes (2026-09-24) — une mesure ne touche jamais `data/` réel, et la clé de
chiffrement ne quitte jamais son emplacement d'origine que par l'ENVIRONNEMENT du processus.

Cause : le 2026-09-24, la restauration des mémoires d'une campagne a supprimé un fichier du
`data/` réel pendant qu'une suite pytest tournait (garde « données réelles » déclenchée). Revue
verdict-reviewer : l'isolation pouvait être silencieusement inactive (`--out` abrégé, `.env`
réinjectant `TESTPILOT_DB_PATH`), et la clé était copiée sur disque à côté de la base copiée.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import qualify_campaign_pilot as script

CLE = "CLE-SECRETE-UNIQUE-0123456789-abcdef"
MOT_DE_PASSE = "mot-de-passe-projet-987654"


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "prod-data"
    (src / "domain").mkdir(parents=True)
    (src / "domain" / "projet-1.json").write_text("{}", encoding="utf-8")
    (src / "testpilot.db").write_bytes(b"sqlite-chiffre-pas-la-cle")
    (src / ".secret_key").write_text(CLE, encoding="utf-8")
    return src


@pytest.fixture(autouse=True)
def _env_restaure(monkeypatch):
    # Valeurs posées d'abord : monkeypatch les restaure (ou les supprime) au teardown, donc la
    # fonction testée ne peut pas laisser une fausse clé dans l'environnement des autres tests.
    monkeypatch.setenv("TESTPILOT_SECRET_KEY", "")
    monkeypatch.setenv("TESTPILOT_DATA_DIR", "")
    monkeypatch.setenv("TESTPILOT_DB_PATH", "")


def test_GARDE_la_cle_est_lue_a_sa_source_et_jamais_ecrite_dans_un_artefact(tmp_path, source):
    racine = tmp_path / "racine"
    racine.mkdir()

    cible = script._isoler_donnees("essai", source=source, racine=racine)

    assert __import__("os").environ["TESTPILOT_SECRET_KEY"] == CLE, "transmise par l'environnement"
    assert not (cible / ".secret_key").exists()
    assert (cible / "testpilot.db").is_file() and (cible / "domain" / "projet-1.json").is_file()

    # Artefacts d'un run simulé : rapport d'erreur, result.json, stderr brut, trace.
    projet = {"password": MOT_DE_PASSE}
    erreur = script._masquer_secrets(f"boom {CLE} et {MOT_DE_PASSE}", projet)
    trial = racine / ".local-preview" / "qualification" / "essai" / "trial-1"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text('{"generation_error": "%s"}' % erreur, encoding="utf-8")
    (trial / "raw_stderr.txt").write_text(erreur, encoding="utf-8")
    (trial / "rapport.md").write_text(erreur, encoding="utf-8")
    (trial / "trace.zip").write_bytes(erreur.encode("utf-8"))

    for fichier in racine.rglob("*"):
        if fichier.is_file():
            contenu = fichier.read_bytes()
            assert CLE.encode() not in contenu, f"la clé de chiffrement fuit dans {fichier}"
            assert MOT_DE_PASSE.encode() not in contenu, f"le mot de passe fuit dans {fichier}"


def test_une_cle_deja_fournie_par_l_environnement_n_est_pas_ecrasee(monkeypatch, tmp_path, source):
    monkeypatch.setenv("TESTPILOT_SECRET_KEY", "cle-de-l-environnement")
    racine = tmp_path / "racine"
    racine.mkdir()

    script._isoler_donnees("essai", source=source, racine=racine)

    assert __import__("os").environ["TESTPILOT_SECRET_KEY"] == "cle-de-l-environnement"


def test_les_copies_au_dela_des_plus_recentes_sont_purgees(tmp_path):
    qualif = tmp_path / ".local-preview" / "qualification"
    for i in range(1, 6):
        (qualif / "a" / f"data-20260924-00000{i}").mkdir(parents=True)

    purgees = script._purger_anciennes_copies(qualif, garder=3)

    assert sorted(Path(p).name for p in purgees) == ["data-20260924-000001", "data-20260924-000002"]
    assert sorted(d.name for d in qualif.glob("*/data-*")) == [
        "data-20260924-000003", "data-20260924-000004", "data-20260924-000005"]


def test_les_copies_de_campagne_sont_exclues_de_git():
    depot = Path(__file__).resolve().parents[1]
    for chemin in (".local-preview/qualification/x/data-20260924-000001/testpilot.db",
                   ".local-preview/qualification/x/data-20260924-000001/.secret_key"):
        res = subprocess.run(["git", "check-ignore", "-q", chemin], cwd=depot)
        assert res.returncode == 0, f"{chemin} n'est pas ignoré par git"


def test_main_refuse_de_tourner_si_l_isolation_est_inactive(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["qualify", "--out", "x"])
    monkeypatch.setattr(script, "DATA_DIR_ISOLE", None)

    with pytest.raises(SystemExit, match="isolation"):
        script.main()


def test_main_refuse_une_base_hors_de_la_copie(monkeypatch, tmp_path):
    copie = tmp_path / "copie"
    copie.mkdir()
    monkeypatch.setattr(sys, "argv", ["qualify", "--out", "x"])
    monkeypatch.setattr(script, "DATA_DIR_ISOLE", copie)
    monkeypatch.setattr(script.config, "DATA_DIR", copie)
    monkeypatch.setattr(script.config, "DB_PATH", tmp_path / "reel" / "testpilot.db")

    with pytest.raises(SystemExit, match="hors de la copie"):
        script.main()


def test_une_abreviation_d_option_n_est_plus_acceptee(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["qualify", "--ou", "x"])

    with pytest.raises(SystemExit):
        script.main()
