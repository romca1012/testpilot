"""Décision 0011 — un comptage sans point de comparaison ÉCHOUE, il ne passe pas en silence.

Avant : `memorize_record_count` avalait son exception (`warn`), et `check_count_*` faisait
`warn` + `return` quand le snapshot manquait → le `@then` passait sans rien vérifier. Chaîne de
faux-négatif muette aux deux bouts (§4.2 « jamais déclaratif », §4.4 « faux-négatif
inacceptable »), dans les helpers les PLUS réutilisés de la bibliothèque (0003).

Tests déterministes sans Odoo : un faux `context` reproduit juste `context.odoo.env[model]
.search_count([])`.
"""

import ast
from pathlib import Path

import pytest

from behave_runtime.steps_library._base_helpers import (
    _COUNT_SNAPSHOT_STEP,
    check_count_increased_by_one,
    check_count_not_increased,
    memorize_record_count,
)
from testpilot.generation import steps_library


class _FakeModel:
    def __init__(self, count, boom=False):
        self._count, self._boom = count, boom

    def search_count(self, _domain):
        if self._boom:
            raise RuntimeError("connexion RPC perdue")
        return self._count

    def search(self, _domain, **_kw):
        """Présent sur le vrai modèle odoorpc — `check_count_increased_by_one` s'en sert pour
        capturer l'enregistrement créé (2026-08-07)."""
        if self._boom:
            raise RuntimeError("connexion RPC perdue")
        return [4242]


class _FakeEnv:
    def __init__(self, count, boom=False):
        self._m = _FakeModel(count, boom)

    def __getitem__(self, _model):
        return self._m


class _FakeOdoo:
    def __init__(self, count, boom=False):
        self.env = _FakeEnv(count, boom)


class _Context:
    def __init__(self, count, boom=False):
        self.odoo = _FakeOdoo(count, boom)


MODEL = "helpdesk.ticket"


# ── Sans snapshot : ÉCHEC, jamais un passage muet ────────────────────────────

@pytest.mark.parametrize("verif", [check_count_not_increased, check_count_increased_by_one])
def test_comptage_sans_snapshot_echoue(verif):
    """LE cas du défaut : le @then était appelé sans que rien n'ait été mesuré avant."""
    with pytest.raises(AssertionError) as exc:
        verif(_Context(count=5), MODEL)
    # Le message doit être ACTIONNABLE : dire quel step manque, pas juste « ça a raté ».
    assert "point de comparaison" in str(exc.value)
    assert "est enregistré pour comparaison" in str(exc.value)
    assert MODEL in str(exc.value)


def test_le_step_cite_dans_le_message_existe_vraiment():
    """Un message qui nomme un step inexistant enverrait le lecteur dans le mur."""
    assert _COUNT_SNAPSHOT_STEP in {s.label for s in steps_library.catalogue()}


# ── Avec snapshot : le comportement utile est INTACT ─────────────────────────

def test_snapshot_puis_augmentation_de_1_passe():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)          # l'action a créé un enregistrement
    check_count_increased_by_one(ctx, MODEL)


def test_snapshot_puis_augmentation_inattendue_echoue():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=12)          # deux créations : le test DOIT échouer
    with pytest.raises(AssertionError, match="devrait être 11"):
        check_count_increased_by_one(ctx, MODEL)


def test_snapshot_puis_pas_daugmentation_passe():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    check_count_not_increased(ctx, MODEL)


def test_snapshot_puis_creation_indue_echoue():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)
    with pytest.raises(AssertionError, match="a augmenté"):
        check_count_not_increased(ctx, MODEL)


# ── Le POSEUR de snapshot n'avale plus son erreur ────────────────────────────

def test_snapshot_impossible_echoue_a_la_pose():
    """Avant, l'exception était avalée : aucun snapshot posé, puis le @then passait en silence.
    Échouer ICI met la cause sous les yeux, là où elle est compréhensible."""
    with pytest.raises(AssertionError) as exc:
        memorize_record_count(_Context(count=0, boom=True), MODEL)
    assert "connexion RPC perdue" in str(exc.value)      # la cause d'origine est conservée
    assert "ne prouveraient rien" in str(exc.value)      # et l'enjeu est dit


# ── Garde du MOTIF, pas seulement des cas trouvés ────────────────────────────

def test_aucun_warn_puis_return_dans_les_helpers():
    """`warnings.warn(...)` suivi d'un `return` = un échec déguisé en succès.

    C'est le motif exact de 0011 : un test qui ne peut plus rien prouver continue quand même.
    Garde le fichier entier, pas les trois fonctions corrigées.
    """
    src = Path("behave_runtime/steps_library/_base_helpers.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    coupables = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for bloc in ast.walk(fn):
            corps = getattr(bloc, "body", None)
            if not isinstance(corps, list):
                continue
            for i, stmt in enumerate(corps[:-1]):
                est_warn = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                            and getattr(stmt.value.func, "attr", "") == "warn")
                if est_warn and isinstance(corps[i + 1], ast.Return):
                    coupables.append(fn.name)
    assert not coupables, (
        f"`warn` + `return` dans {coupables} : un avertissement n'échoue pas un test. "
        f"Si la vérification ne peut pas se faire, il faut ÉCHOUER (0011), pas continuer.")
