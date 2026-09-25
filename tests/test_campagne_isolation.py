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
CLE_API = "sk-ant-api03-FAUSSE-CLE-API-0123456789"
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLE_API)


def test_GARDE_la_cle_est_lue_a_sa_source_et_jamais_ecrite_dans_un_artefact(tmp_path, source):
    racine = tmp_path / "racine"
    racine.mkdir()

    cible = script._isoler_donnees("essai", source=source, racine=racine)

    assert __import__("os").environ["TESTPILOT_SECRET_KEY"] == CLE, "transmise par l'environnement"
    assert not (cible / ".secret_key").exists()
    assert (cible / "testpilot.db").is_file() and (cible / "domain" / "projet-1.json").is_file()

    # Artefacts d'un run simulé : rapport d'erreur, result.json, stderr brut, trace.
    projet = {"password": MOT_DE_PASSE}
    erreur = script._masquer_secrets(f"boom {CLE} et {MOT_DE_PASSE} et {CLE_API}", projet)
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
            assert CLE_API.encode() not in contenu, f"ANTHROPIC_API_KEY fuit dans {fichier}"


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


def test_controle_prealable_echoue_avant_le_premier_essai(tmp_path):
    copie = tmp_path / "copie"
    copie.mkdir()

    assert script._controle_prealable(copie, "cle") == ["base absente de la copie isolee (%s) : "
        "TESTPILOT_CAMPAIGN_SOURCE_DATA pointe-t-il sur un data/ reel ?" % copie]
    assert any("ANTHROPIC_API_KEY" in p for p in script._controle_prealable(copie, ""))
    assert any("dossier de donnees isole absent" in p
               for p in script._controle_prealable(tmp_path / "nulle-part", "cle"))
    (copie / "testpilot.db").write_bytes(b"x")
    assert script._controle_prealable(copie, "cle") == []


def test_main_refuse_de_lancer_un_essai_sans_cle_api(monkeypatch, tmp_path):
    copie = tmp_path / "copie"
    copie.mkdir()
    (copie / "testpilot.db").write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["qualify", "--out", "x"])
    monkeypatch.setattr(script, "DATA_DIR_ISOLE", copie)
    monkeypatch.setattr(script.config, "DATA_DIR", copie)
    monkeypatch.setattr(script.config, "DB_PATH", copie / "testpilot.db")
    monkeypatch.setattr(script.config, "ANTHROPIC_API_KEY", "")

    with pytest.raises(SystemExit, match="controle prealable"):
        script.main()


# ── Arrêt RÉEL sur plafond de coût (le plafond n'était qu'une intention) ────────────────────

def _essai_a(cout):
    return lambda case_id, iteration: {"generation": {"cost_usd": cout}, "case": case_id,
                                       "iteration": iteration}


def test_aucun_essai_n_est_lance_au_dela_du_plafond():
    lances = []

    def lancer(case_id, iteration):
        lances.append((case_id, iteration))
        return _essai_a(0.5)(case_id, iteration)

    resultats, arret = script._boucle_essais((99, 101), (1, 2, 3), lancer, plafond=1.2)

    # 0 $ (1er) -> 0,5 $ + plus cher 0,5 = 1,0 <= 1,2 (2e) -> 1,0 + 0,5 = 1,5 > 1,2 : arrêt.
    assert lances == [(99, 1), (99, 2)] and len(resultats) == 2
    assert arret["essais_lances"] == 2 and arret["prochain"] == {"case_id": 99, "iteration": 3}
    assert "plafond" in arret["raison"]
    assert sum(script._cout_de(r) for r in resultats) <= 1.2


def test_sans_plafond_tous_les_essais_sont_lances():
    resultats, arret = script._boucle_essais((99, 101), (1, 2), _essai_a(9.0), plafond=None)

    assert len(resultats) == 4 and arret is None


def test_un_plafond_deja_atteint_n_autorise_aucun_essai():
    resultats, arret = script._boucle_essais((99,), (1, 2), _essai_a(1.0), plafond=0.0)

    assert resultats == [] and arret["essais_lances"] == 0


def test_un_essai_sans_cout_connu_compte_pour_zero_sans_planter():
    resultats, arret = script._boucle_essais((99,), (1, 2, 3), lambda c, i: {"generation": None},
                                             plafond=0.1)

    assert len(resultats) == 3 and arret is None


def test_main_sort_avec_le_code_3_quand_le_plafond_interrompt_la_campagne(monkeypatch, tmp_path):
    import contextlib

    copie = tmp_path / "copie"
    copie.mkdir()
    (copie / "testpilot.db").write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["qualify", "--out", "x", "--cases", "99", "--iterations",
                                      "1,2,3", "--max-cost-usd", "0.3", "--project-id", "1"])
    monkeypatch.setattr(script, "DATA_DIR_ISOLE", copie)
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script.config, "DATA_DIR", copie)
    monkeypatch.setattr(script.config, "DB_PATH", copie / "testpilot.db")
    monkeypatch.setattr(script.config, "ANTHROPIC_API_KEY", "cle")
    monkeypatch.setattr(script, "verifier_connexion", lambda p: {})
    monkeypatch.setattr(script.ProjectRepo, "get", lambda self, pid: {"base_url": "u"})
    fausse_conn = type("Conn", (), {"close": lambda self: None})()
    monkeypatch.setattr(script, "QualificationBudget",
                        lambda chemin: type("B", (), {"conn": fausse_conn})())
    monkeypatch.setattr(script, "_snapshot_memoires", lambda pid: {})
    monkeypatch.setattr(script, "_restaurer_memoires", lambda snap: None)
    lances = []
    monkeypatch.setattr(script, "_un_essai", lambda *a, **k: lances.append(a[:2]) or {
        "generation": {"cost_usd": 0.2}, "budget": {}})
    monkeypatch.setattr(script.sqlite3, "connect", lambda *a, **k: contextlib.nullcontext(
        type("K", (), {"row_factory": None})()))

    with pytest.raises(SystemExit) as sortie:
        script.main()

    assert sortie.value.code == 3
    assert len(lances) == 1, "0,2 $ + le plus cher observé 0,2 $ > plafond 0,3 $ : arrêt avant le 2e"
    assert (tmp_path / ".local-preview" / "qualification" / "x" / "arret_plafond.json").is_file()


# ── Mode « exploration seule » : la sonde active sur les données isolées, rien de généré ────────

def test_explorer_ecrit_ce_que_la_sonde_a_observe_et_marque_les_sauvegardes_automatiques(
        monkeypatch, tmp_path):
    class _Connecteur:
        def connect(self):
            pass

        def disconnect(self):
            pass

        def inspect_form(self, url):
            if "brouillon" in url:
                return {"fields": [{"name": "a"}], "sonde": {
                    "statut": "interrompue", "champs": {},
                    "raison": "sauvegarde automatique détectée, pas de sonde : POST /draft"}}
            return {"fields": [{"name": "numero_facture1"}], "sonde": {
                "statut": "ok", "champs": {"numero_facture1": {"sondes": {}, "exemple_stable": "1"}}}}

    monkeypatch.setattr(script, "build_connector", lambda projet: _Connecteur())

    rapport = script._explorer({}, ["https://x/f/1", "https://x/brouillon/2"], tmp_path)

    assert [r["sauvegarde_automatique_detectee"] for r in rapport] == [False, True]
    ecrit = __import__("json").loads((tmp_path / "exploration.json").read_text(encoding="utf-8"))
    assert ecrit[0]["sonde"]["champs"]["numero_facture1"]["exemple_stable"] == "1"
    assert ecrit[0]["champs_de_la_page"] == ["numero_facture1"]


# ── Crédits API épuisés (2026-09-25) : arrêt immédiat, essai non retenu ─────────────────────────────

def test_un_manque_de_credits_arrete_la_campagne_et_n_est_pas_compte_comme_un_echec_de_l_agent():
    appels = []

    def lancer(case_id, iteration):
        appels.append(case_id)
        if case_id == 3:
            return {"generation_error": "Error code: 400 - Your credit balance is too low to access the Anthropic API."}
        return {"generation": {"cost_usd": 0.1}}

    resultats, arret = script._boucle_essais((1, 2, 3, 4, 5), (1,), lancer, plafond=5.0)

    assert appels == [1, 2, 3], "aucun appel supplémentaire une fois les crédits épuisés"
    assert [r.get("generation", {}).get("cost_usd") for r in resultats] == [0.1, 0.1], "l'essai sans crédits n'est PAS retenu"
    assert "crédits" in arret["raison"] and arret["prochain"]["case_id"] == 3


def test_une_autre_erreur_de_generation_ne_coupe_pas_la_campagne():
    def lancer(case_id, iteration):
        return {"generation_error": "ValueError: réponse illisible"} if case_id == 2 else {"generation": {"cost_usd": 0.1}}

    resultats, arret = script._boucle_essais((1, 2, 3), (1,), lancer, plafond=5.0)

    assert arret is None and len(resultats) == 3
