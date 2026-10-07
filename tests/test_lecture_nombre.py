"""Lecture normalisée d'un nombre affiché + comparaison à tolérance déclarée (lot Q4, D21)."""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest

from testpilot import config

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _lecture_nombre as ln  # noqa: E402

D = Decimal


@pytest.mark.parametrize("texte, valeur, devise", [
    ("129,51", "129.51", None),
    ("1 234,50 €", "1234.50", "EUR"),
    ("1 234,50 €", "1234.50", "EUR"),
    ("1,234.50", "1234.50", None),
    ("1.234,50", "1234.50", None),
    ("$1,234,567.89", "1234567.89", "USD"),
    ("1.234.567", "1234567", None),
    ("1 234 567", "1234567", None),
    ("-12,50", "-12.50", None),
    ("−12,50 €", "-12.50", "EUR"),
    ("(12,50)", "-12.50", None),
    ("0,5", "0.5", None),
    ("0,125", "0.125", None),
    ("18 %", "18", None),
    ("5 000 FCFA", "5000", "XOF"),
    ("1’234.50", "1234.50", None),
])
def test_lectures_sans_ambiguite(texte, valeur, devise):
    lu = ln.lire_nombre(texte)

    assert lu.valeur == D(valeur) and lu.devise == devise


def test_pourcentage_est_signale():
    assert ln.lire_nombre("18 %").pourcentage is True and ln.lire_nombre("18").pourcentage is False


@pytest.mark.parametrize("texte", ["1,234", "1.234", "12,345", "999,999"])
def test_une_lecture_ambigue_est_refusee_jamais_devinee(texte):
    """Falsifiable : « 1,234 » lu au hasard comme 1.234 ou 1234 donnerait un faux verdict dans un cas sur deux."""
    with pytest.raises(ln.LectureImpossible, match="ambigu"):
        ln.lire_nombre(texte)


def test_le_separateur_decimal_connu_leve_l_ambiguite():
    assert ln.lire_nombre("1,234", separateur_decimal=",").valeur == D("1.234")
    assert ln.lire_nombre("1,234", separateur_decimal=".").valeur == D("1234")


@pytest.mark.parametrize("texte", ["", "  ", "abc", "12 abc", "1,2,3,4,5,6", "1.234,56,7", "12,34.567,8", "€"])
def test_un_texte_non_numerique_ou_incoherent_est_refuse(texte):
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


def test_exacte_par_defaut_un_centime_d_ecart_echoue():
    """Falsifiable : sans tolérance déclarée, 129,50 n'est PAS 129,51."""
    assert ln.comparer(ln.lire_nombre("129,51"), "129.51").ok is True
    c = ln.comparer(ln.lire_nombre("129,50"), "129.51")
    assert c.ok is False and "exacte, aucune tolérance" in c.message


def test_la_tolerance_declaree_figure_dans_le_message_avec_sa_source():
    c = ln.comparer(D("129.50"), "129.51", tolerance="0.01", source="arrondi de la devise")

    assert c.ok is True and "± 0.01 — arrondi de la devise" in c.message
    assert ln.comparer(D("129.48"), "129.51", tolerance="0.01", source="arrondi de la devise").ok is False


def test_une_tolerance_sans_source_est_refusee():
    with pytest.raises(ValueError, match="source"):
        ln.comparer(D("1"), "1", tolerance="0.01")
    with pytest.raises(ValueError, match="négative"):
        ln.comparer(D("1"), "1", tolerance="-1", source="x")


def test_un_float_n_introduit_pas_d_erreur_binaire():
    """0.1 + 0.2 != 0.3 en binaire ; la comparaison passe par le texte du nombre, pas par sa valeur binaire."""
    assert ln.comparer(D("0.3"), 0.3).ok is True
