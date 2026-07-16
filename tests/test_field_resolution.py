"""Décision 0007 — phases B et B+.

B : helpers UI tolérants — `resolve_field_name` accepte le nom technique OU le libellé humain,
avec un repli TRACÉ (jamais silencieux). Tests déterministes sans navigateur : un faux `page`
reproduit juste la surface Playwright utilisée (`locator(sel).count()`,
`get_by_label(text).count()`, `.first.get_attribute("name")`).

B+ : ce repli tracé remonte jusqu'à l'exécution et à l'écran, y compris sur un run VERT — Behave
n'affiche pas les logs d'un scénario réussi, or c'est exactement le cas où un champ renommé côté
application serait absorbé sans que personne ne le voie (verdict 0007 n°2).
"""

import logging
import subprocess
import sys
from pathlib import Path

from behave_runtime.steps_library._base_helpers import (
    FIELD_FALLBACK_MARKER,
    resolve_field_name,
)
from testpilot.execution import behave_result
from testpilot.execution.behave_result import extract_field_fallbacks, parse_behave_json
from testpilot.store.db import (
    _column_names,
    _migrate_4_execution_field_fallbacks,
    get_initialized_db,
)


class _FakeLocator:
    def __init__(self, count: int, name_attr=None):
        self._count = count
        self._name = name_attr

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def get_attribute(self, attr):
        return self._name if attr == "name" else None


class _FakePage:
    """Reproduit la surface minimale : quels `[name=...]` existent, et ce que résout un libellé."""

    def __init__(self, existing_names, label_map=None):
        self._names = set(existing_names)
        self._labels = label_map or {}  # libellé -> name technique (ou None si contrôle sans name)

    def locator(self, selector):
        # On ne gère que la forme `[name="X"]` / `[name='X']` utilisée par resolve_field_name.
        inner = selector.split("name=", 1)[1].strip().strip("]").strip("\"'")
        return _FakeLocator(1 if inner in self._names else 0)

    def get_by_label(self, text, exact=False):
        if text in self._labels:
            return _FakeLocator(1, name_attr=self._labels[text])
        return _FakeLocator(0)


def test_nom_technique_exact_renvoye_sans_repli(caplog):
    page = _FakePage(existing_names={"name"})
    with caplog.at_level(logging.WARNING):
        assert resolve_field_name(page, "name") == "name"
    assert FIELD_FALLBACK_MARKER not in caplog.text  # aucun repli → aucune trace


def test_libelle_resolu_vers_nom_technique_avec_trace(caplog):
    # Cas exact de l'écart 1 : le libellé « Raison de la demande » → name='name'.
    page = _FakePage(existing_names={"name"},
                     label_map={"Raison de la demande": "name"})
    with caplog.at_level(logging.WARNING):
        resolved = resolve_field_name(page, "Raison de la demande")
    assert resolved == "name"
    # Repli TRACÉ (exigence n°2 du verdict 0007) : marqueur + les deux noms.
    assert FIELD_FALLBACK_MARKER in caplog.text
    assert "Raison de la demande" in caplog.text and "name='name'" in caplog.text


def test_ni_nom_ni_libelle_renvoie_ident_sans_trace(caplog):
    # Rien ne résout : on rend l'ident tel quel (échec propre en aval), et on ne trace pas un
    # repli qui n'a pas eu lieu.
    page = _FakePage(existing_names={"autre"})
    with caplog.at_level(logging.WARNING):
        assert resolve_field_name(page, "inexistant") == "inexistant"
    assert FIELD_FALLBACK_MARKER not in caplog.text


def test_libelle_trouve_mais_controle_sans_name_ne_devine_pas(caplog):
    # Le libellé matche un contrôle SANS attribut name → on ne devine pas, on rend l'ident.
    page = _FakePage(existing_names=set(), label_map={"Un libellé": None})
    with caplog.at_level(logging.WARNING):
        assert resolve_field_name(page, "Un libellé") == "Un libellé"
    assert FIELD_FALLBACK_MARKER not in caplog.text


# ── Phase B+ : du log du run jusqu'à l'exécution ──────────────────────────────

def test_marqueur_identique_des_deux_cotes():
    """Source unique du marqueur, tenue par test faute d'import.

    Le parseur (couche API) NE PEUT PAS importer `_base_helpers` sans tirer Playwright avec lui :
    le littéral y est donc dupliqué. C'est ce test — et lui seul — qui empêche les deux valeurs
    de diverger en silence, ce qui rendrait B+ aveugle.
    """
    assert behave_result.FIELD_FALLBACK_MARKER == FIELD_FALLBACK_MARKER


def test_extraction_du_repli_depuis_le_log_behave():
    # Forme réelle : Behave réémet le log du step préfixé par LOG_<NIVEAU>:<logger>:
    log = ("LOG_WARNING:steps._base_helpers: [TP_FIELD_FALLBACK] champ 'Raison de la demande' "
           "introuvable par attribut name ; résolu via son libellé -> name='name'.\n")
    fallbacks = extract_field_fallbacks(log)
    assert len(fallbacks) == 1
    assert "Raison de la demande" in fallbacks[0] and "name='name'" in fallbacks[0]
    assert FIELD_FALLBACK_MARKER not in fallbacks[0]  # le marqueur est du transport, pas du message


def test_extraction_dedupliquee():
    # Le même repli se répète à chaque scénario du run : une seule entrée persistée.
    ligne = "LOG_WARNING:steps._base_helpers: [TP_FIELD_FALLBACK] champ 'X' -> name='x'.\n"
    assert len(extract_field_fallbacks(ligne * 3)) == 1


def test_extraction_lit_le_log_entier_pas_la_queue_tronquee():
    """Le repli survit même si 3000+ caractères le suivent.

    `raw_stdout` ne garde que les 3000 derniers caractères ; extraire depuis ce champ perdrait
    un repli survenu tôt dans un run bavard.
    """
    log = "[TP_FIELD_FALLBACK] champ 'X' -> name='x'.\n" + ("bruit\n" * 2000)
    result = parse_behave_json("", returncode=0, combined_log=log)
    assert result.field_fallbacks == ["champ 'X' -> name='x'."]
    assert FIELD_FALLBACK_MARKER not in result.raw_stdout  # bien hors de la fenêtre tronquée


def test_extraction_meme_sans_json_exploitable():
    # JSON absent (run planté avant l'écriture) : le repli ne doit pas être perdu au passage.
    log = "[TP_FIELD_FALLBACK] champ 'X' -> name='x'.\n"
    assert parse_behave_json("", returncode=1, combined_log=log).field_fallbacks
    assert parse_behave_json("pas du json", returncode=1, combined_log=log).field_fallbacks


def test_aucun_repli_aucun_bruit():
    # Anti-faux-positif : un run normal ne remonte aucun repli (sinon la pastille serait partout).
    assert extract_field_fallbacks("") == []
    assert extract_field_fallbacks("1 scenario passed, 0 failed\nRien à signaler\n") == []


def test_le_marqueur_survit_a_behave_sur_un_scenario_VERT(tmp_path):
    """GARDE — épingle le comportement de Behave sur lequel repose TOUTE la phase B+.

    Mesuré sur behave 1.3.3 : le log d'un step part sur **stderr** et survit même quand le
    scénario est VERT — c'est ce qui permet de capter le repli sans toucher au harnais. Rien ne
    garantit ce comportement contractuellement : sans ce test, une montée de version de Behave
    rendrait B+ aveugle **en silence**, soit précisément l'angle mort qu'il existe pour fermer.
    Ici la chaîne complète est exercée : vrai `resolve_field_name` → vrai Behave → vrai parseur.
    """
    repo_root = Path(__file__).resolve().parents[1]
    (tmp_path / "steps").mkdir()
    (tmp_path / "vert.feature").write_text(
        "Feature: garde du repli\n"
        "  Scenario: un scenario vert qui declenche un repli\n"
        "    Given un champ resolu par son libelle\n",
        encoding="utf-8")
    # Le step passe (scénario VERT) tout en déclenchant un vrai repli via le vrai helper.
    (tmp_path / "steps" / "repli.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, r'{repo_root}')\n"
        "from behave import given\n"
        "from behave_runtime.steps_library._base_helpers import resolve_field_name\n"
        "\n"
        "class _L:\n"
        "    def __init__(self, count, name=None): self._c, self._n = count, name\n"
        "    def count(self): return self._c\n"
        "    @property\n"
        "    def first(self): return self\n"
        "    def get_attribute(self, attr): return self._n\n"
        "\n"
        "class _P:\n"
        "    def locator(self, sel): return _L(0)\n"
        "    def get_by_label(self, text, exact=False): return _L(1, 'name')\n"
        "\n"
        "@given('un champ resolu par son libelle')\n"
        "def step_impl(context):\n"
        "    assert resolve_field_name(_P(), 'Raison de la demande') == 'name'\n",
        encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "behave", "-f", "json", "-o", "result.json", "vert.feature"],
        cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert proc.returncode == 0, f"le scénario de garde doit être VERT :\n{proc.stdout}\n{proc.stderr}"

    json_path = tmp_path / "result.json"
    result = parse_behave_json(
        json_path.read_text(encoding="utf-8") if json_path.exists() else "",
        proc.returncode, combined_log=f"{proc.stdout}\n{proc.stderr}")

    assert result.passed == 1, "le run de garde doit compter un scénario passé"
    assert result.field_fallbacks, (
        "le repli d'un scénario VERT doit remonter jusqu'à BehaveResult — s'il ne remonte plus, "
        "Behave a changé sa façon d'exposer les logs et B+ est aveugle : ne pas neutraliser ce "
        "test, corriger la capture.")
    assert "Raison de la demande" in result.field_fallbacks[0]


# ── Migration 4 : la colonne qui porte les replis ─────────────────────────────

def test_migration_4_ramene_une_base_existante_a_la_cible(tmp_path):
    db = tmp_path / "base.db"
    conn = get_initialized_db(db)
    # Simule une base d'AVANT B+ : colonne absente, version ramenée à 3.
    conn.execute("ALTER TABLE execution DROP COLUMN field_fallbacks")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    assert "field_fallbacks" not in _column_names(conn, "execution")
    conn.close()

    conn = get_initialized_db(db)  # réouverture → migrations en attente
    assert "field_fallbacks" in _column_names(conn, "execution")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.close()


def test_migration_4_idempotente(tmp_path):
    conn = get_initialized_db(tmp_path / "base.db")
    _migrate_4_execution_field_fallbacks(conn)  # rejouée sur une base déjà à la cible
    _migrate_4_execution_field_fallbacks(conn)
    assert "field_fallbacks" in _column_names(conn, "execution")
    conn.close()
