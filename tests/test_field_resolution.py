"""Décision 0007 phase B — helpers UI tolérants : `resolve_field_name` accepte le nom technique
OU le libellé humain, avec un repli TRACÉ (jamais silencieux).

Tests déterministes sans navigateur : un faux `page` reproduit juste la surface Playwright
utilisée (`locator(sel).count()`, `get_by_label(text).count()`, `.first.get_attribute("name")`).
"""

import logging

from behave_runtime.steps_library._base_helpers import (
    FIELD_FALLBACK_MARKER,
    resolve_field_name,
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
