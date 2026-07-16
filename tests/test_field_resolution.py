"""Décision 0007 — phases B et B+.

B : helpers UI tolérants — `resolve_field_name` accepte le nom technique OU le libellé humain,
avec un repli TRACÉ (jamais silencieux). Tests déterministes sans navigateur : un faux `page`
reproduit juste la surface Playwright utilisée (`locator(sel).count()`,
`get_by_label(text).count()`, `.first.get_attribute("name")`).

B+ : ce repli tracé remonte jusqu'à l'exécution et à l'écran, y compris sur un run VERT — c'est
exactement le cas où un champ renommé côté application serait absorbé sans que personne ne le voie
(verdict 0007 n°2).

⚠️ Le transport passe par un FICHIER SIDECAR, pas par la sortie de Behave. Premier jet de B+ :
il lisait le marqueur dans `combined_log` et un test de garde lançait Behave SANS `environment.py`
— ce test passait, et B+ était pourtant AVEUGLE en run réel (`field_fallbacks` toujours vide).
Cause mesurée : Behave capture stdout/stderr/logging et ne les recrache pas sur un scénario vert
dès qu'un `environment.py` est présent, ce que `BehaveRunner._assemble` fait TOUJOURS. Le test de
garde ci-dessous assemble donc un vrai `environment.py` : il échouerait sur l'ancienne
implémentation.
"""

import logging
import os
from pathlib import Path

from behave_runtime.steps_library import _base_helpers
from behave_runtime.steps_library._base_helpers import (
    FIELD_FALLBACK_FILE_ENV,
    FIELD_FALLBACK_MARKER,
    resolve_field_name,
)
from testpilot.execution import behave_result
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.store.db import (
    _SCHEMA_VERSION,
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


# ── Phase B+ : du run jusqu'à l'exécution, via le fichier sidecar ─────────────

def test_nom_de_la_variable_denv_identique_des_deux_cotes():
    """Source unique du nom d'env, tenue par test faute d'import.

    Le runner (couche API) NE PEUT PAS importer `_base_helpers` sans tirer Playwright avec lui :
    le littéral y est donc dupliqué. C'est ce test — et lui seul — qui empêche les deux valeurs de
    diverger en silence : le helper écrirait dans un fichier que le runner ne lirait jamais, et le
    repli redeviendrait invisible sans que rien n'échoue.
    """
    assert behave_result.FIELD_FALLBACK_FILE_ENV == FIELD_FALLBACK_FILE_ENV


def test_helper_consigne_le_repli_dans_le_sidecar(tmp_path, monkeypatch):
    sidecar = tmp_path / "field_fallbacks.txt"
    monkeypatch.setenv(FIELD_FALLBACK_FILE_ENV, str(sidecar))
    page = _FakePage(existing_names={"name"}, label_map={"Raison de la demande": "name"})

    assert resolve_field_name(page, "Raison de la demande") == "name"

    contenu = sidecar.read_text(encoding="utf-8")
    assert "Raison de la demande" in contenu and "name='name'" in contenu
    # Le marqueur appartient au LOG (mode dev) ; le sidecar porte le message, pas le transport.
    assert FIELD_FALLBACK_MARKER not in contenu


def test_helper_n_ecrit_rien_sans_repli(tmp_path, monkeypatch):
    # Anti-faux-positif : un champ résolu par son nom technique ne consigne rien.
    sidecar = tmp_path / "field_fallbacks.txt"
    monkeypatch.setenv(FIELD_FALLBACK_FILE_ENV, str(sidecar))
    assert resolve_field_name(_FakePage(existing_names={"name"}), "name") == "name"
    assert not sidecar.exists()


def test_helper_sans_variable_denv_ne_casse_pas(monkeypatch, caplog):
    """Hors run behave (test unitaire, appel direct), aucun sidecar n'est désigné : on trace au
    log et on continue. Une trace ne doit jamais faire échouer ce qu'elle observe."""
    monkeypatch.delenv(FIELD_FALLBACK_FILE_ENV, raising=False)
    page = _FakePage(existing_names={"name"}, label_map={"Raison de la demande": "name"})
    with caplog.at_level(logging.WARNING):
        assert resolve_field_name(page, "Raison de la demande") == "name"
    assert FIELD_FALLBACK_MARKER in caplog.text


def test_lecture_du_sidecar_dedupliquee_et_plafonnee(tmp_path):
    sidecar = tmp_path / "f.txt"
    sidecar.write_text("champ 'X' -> name='x'.\n" * 3, encoding="utf-8")
    assert behave_result.read_field_fallbacks(sidecar) == ["champ 'X' -> name='x'."]

    sidecar.write_text("".join(f"repli {i}\n" for i in range(50)), encoding="utf-8")
    assert len(behave_result.read_field_fallbacks(sidecar, limit=20)) == 20


def test_lecture_du_sidecar_absent_vaut_aucun_repli(tmp_path):
    # Cas nominal (aucun repli) : le fichier n'est jamais créé — ce n'est pas une erreur.
    assert behave_result.read_field_fallbacks(tmp_path / "jamais_ecrit.txt") == []


def _ecrire_aire_de_run(tmp_path, *, avec_repli: bool):
    """Aire de run minimale mais de FORME RÉELLE : un environment.py est assemblé, comme le
    fait toujours BehaveRunner — c'est la condition qui active la capture de Behave."""
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "environment.py").write_text(
        "# environment.py minimal : sa PRÉSENCE suffit à activer la capture de Behave.\n"
        "def before_all(context):\n    pass\n", encoding="utf-8")

    lib = tmp_path / "lib"; lib.mkdir()
    ident = "Raison de la demande" if avec_repli else "name"
    (lib / "garde_steps.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, r'{Path(__file__).resolve().parents[1]}')\n"
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
        "    # Aucun champ ne répond par [name=...] sauf 'name' ; le libellé, lui, résout.\n"
        "    def locator(self, sel): return _L(1 if \"name='name'\" in sel or '\"name\"' in sel else 0)\n"
        "    def get_by_label(self, text, exact=False): return _L(1, 'name')\n"
        "\n"
        "@given('un champ est resolu')\n"
        "def step_impl(context):\n"
        f"    assert resolve_field_name(_P(), {ident!r}) == 'name'\n",
        encoding="utf-8")

    gen = tmp_path / "gen"; gen.mkdir()
    (gen / "garde.feature").write_text(
        "# language: fr\n"
        "Fonctionnalité: garde du repli\n"
        "  Scénario: un scenario VERT qui declenche un repli\n"
        "    Soit un champ est resolu\n", encoding="utf-8")
    return BehaveRunner(runtime_dir=runtime, generated_dir=gen, steps_library_dir=lib,
                        real_timeout=120)


def test_GARDE_le_repli_remonte_dun_run_VERT_avec_environment_py(tmp_path):
    """GARDE — le test que le premier jet de B+ n'avait pas, et qui l'aurait démasqué.

    Il exerce le VRAI `BehaveRunner` (plomberie de la variable d'env + lecture du sidecar) sur une
    aire de run de forme réelle — `environment.py` assemblé — avec un scénario VERT, sans Odoo.

    Sur l'implémentation précédente (lecture du marqueur dans `combined_log`), ce test ÉCHOUE :
    Behave avale le log dès qu'un `environment.py` est présent. C'est précisément l'angle mort qui
    avait laissé passer un B+ aveugle en run réel, validé par un test de garde qui, lui, omettait
    `environment.py` et testait donc un monde qui n'existe pas en production.
    """
    runner = _ecrire_aire_de_run(tmp_path, avec_repli=True)
    result = runner.real_run("garde")

    assert result.passed == 1, f"le scénario de garde doit être VERT : {result.raw_stdout}"
    assert result.field_fallbacks, (
        "le repli d'un scénario VERT doit remonter jusqu'à BehaveResult — s'il ne remonte plus, "
        "le signal est perdu en silence : corriger le transport, ne pas neutraliser ce test.")
    assert "Raison de la demande" in result.field_fallbacks[0]
    assert "name='name'" in result.field_fallbacks[0]


def test_GARDE_un_run_VERT_sans_repli_ne_remonte_rien(tmp_path):
    # Anti-faux-positif du même dispositif : sans repli, aucune entrée (donc aucune pastille).
    runner = _ecrire_aire_de_run(tmp_path, avec_repli=False)
    result = runner.real_run("garde")
    assert result.passed == 1
    assert result.field_fallbacks == []


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
    # La CIBLE, pas un chiffre en dur : ce test vérifie que les migrations en attente amènent la
    # base à jour, pas qu'il existe exactement N migrations (sinon toute migration future le
    # casserait sans qu'aucune régression n'ait eu lieu).
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    conn.close()


def test_migration_4_idempotente(tmp_path):
    conn = get_initialized_db(tmp_path / "base.db")
    _migrate_4_execution_field_fallbacks(conn)  # rejouée sur une base déjà à la cible
    _migrate_4_execution_field_fallbacks(conn)
    assert "field_fallbacks" in _column_names(conn, "execution")
    conn.close()
